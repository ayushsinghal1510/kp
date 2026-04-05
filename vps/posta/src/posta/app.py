import json
import uvicorn
from contextlib import asynccontextmanager
import os
import requests
from bson.objectid import ObjectId

from .loader import load_clients

from .state import AppState

from jwcrypto.jwe import JWE
from jwcrypto.jwk import JWK

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Header, Request
from services import env_str_to_bool , env_str_to_list

from dotenv import load_dotenv

load_dotenv()

state = AppState()

@asynccontextmanager
async def lifespan(app : FastAPI) : 

    (
        config , 
        logger , 
        students_collection , 
        scenarios_collection , 
        sessions_collection
    ) = load_clients()

    app.state.config = config 
    app.state.logger = logger

    app.state.students_collection = students_collection
    app.state.scenarios_collection = scenarios_collection 
    app.state.sessions_collection = sessions_collection

    logger.info("System Startup: Models and Config Loaded.")

    yield

    logger.info("System Shutdown.")

app = FastAPI(lifespan = lifespan)

app.add_middleware(
    CORSMiddleware , 
    allow_origins = '*' , 
    allow_credentials = True , 
    allow_methods = '*' , 
    allow_headers = '*' 
)

@app.get('/')
async def read_root() : return {'Hello' : 'World'}

@app.post('/session')
def process_new_session(token : str = Header(... , alias = 'token')) : 

    jwetoken : JWE = JWE()

    jwekey : JWK = JWK(**{
            'kty' : 'oct' , 
            'k' : os.environ['JWE_SECRET']
        })

    jwetoken.deserialize(token)
    jwetoken.decrypt(jwekey)

    payload = json.loads(jwetoken.payload.decode('utf-8'))

    response = requests.get(
        'https://chat.voxio.in/agents/session' , 
        params = {
            'session_id' : payload['session_id']
        }
    )

    if response.status_code == 200 : 

        response_json = response.json()

        transcription = response_json['session-data']['state'].get('diagnosis_conversation_history')
        feedback = response_json['session-data']['state'].get('feedback')
        score = response_json['session-data']['state'].get('score')

        session_doc = {
            'transcription' : transcription , 
            'feedback' : feedback , 
            'score' : score , 
            'student_id' : payload['student_id'] , 
            'scenario_id' : payload['scenario_id'] , 
            # ! Add created and updated at here 
        }

        session_result = state.sessions_collection.insert_one(session_doc)
        new_session_id : str = str(session_result.inserted_id)
        
        student_update_path = f"session_list.{payload['scenario_id']}"
        
        state.students_collection.update_one(
            {"_id": ObjectId(payload['student_id']) if isinstance(payload['student_id'], str) else payload['student_id']},
            {"$push": {student_update_path: new_session_id}},
            upsert = True
        )

        state.scenarios_collection.update_one(
            {"_id" : ObjectId(payload['scenario_id']) if isinstance(payload['scenario_id'] , str) else payload['scenario_id']} , 
            {"$push" : {"sessions" : new_session_id}} , 
            upsert = True
        )

        return {
            'status' : 'success' , 
            'message' : 'Details updated succesfully at dashboard'
        }

    return {
        'status' : 'error' , 
        'message' : 'Not able to find session logs'
    }

def main() : 

    uvicorn.run(
        app , 
        host = '0.0.0.0' , 
        port = 8000
    )


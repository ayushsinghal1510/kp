import json
import uvicorn
from contextlib import asynccontextmanager
import os
import requests
from bson.objectid import ObjectId

from .loader import load_clients

from .routers import get_results_route

from .state import AppState

from jwcrypto.jwe import JWE
from jwcrypto.jwk import JWK

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Header, HTTPException, Request
from services import env_str_to_bool , env_str_to_list

from dotenv import load_dotenv

load_dotenv()

state = AppState()

@asynccontextmanager
async def lifespan(app : FastAPI) : 

    (
        config ,
        logger ,
        gemini_client ,
        students_collection ,
        scenarios_collection ,
        sessions_collection
    ) = load_clients()

    state.config = config
    state.logger = logger

    state.gemini_client = gemini_client

    state.students_collection = students_collection
    state.scenarios_collection = scenarios_collection 
    state.sessions_collection = sessions_collection

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
            # * Stored so /get-results can find this doc again by the chat platform's session id
            'session_id' : payload['session_id'] ,
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

# * Stacked rather than one api_route(methods = [...]) call: api_route gives both
# * verbs the same generated operation id, which FastAPI warns about at startup.
# * Two decorators register two routes over one function body, each with its own id.
@app.post('/get-results')
@app.get('/get-results')
async def get_results(request : Request) -> dict :

    # * One handler on both verbs, so a caller that guesses the wrong method
    # * lands here instead of on a 404. A GET usually carries no body, so the
    # * query string is read as a fallback.
    try : data : dict = await request.json()
    except Exception : data = dict(request.query_params)

    if not isinstance(data , dict) : raise HTTPException(
        status_code = 400 ,
        detail = 'Request body must be a JSON object.'
    )

    required : list = ['scenario_id' , 'transcription' , 'session_id' , 'user_id']
    missing : list = [field for field in required if field not in data]

    if missing :

        # * The access log shows only a bare 400, so record what the caller did send
        state.logger.warning(f'get-results rejected : missing {missing} , got keys {sorted(data)}')

        raise HTTPException(
            status_code = 400 ,
            detail = f"Missing {' , '.join(repr(field) for field in missing)} in request body or query string."
        )

    return await get_results_route(
        scenario_id = data['scenario_id'] ,
        transcription = data['transcription'] ,
        session_id = data['session_id'] ,
        user_id = data['user_id'] ,
        scenarios_collection = state.scenarios_collection ,
        sessions_collection = state.sessions_collection ,
        gemini_client = state.gemini_client ,
        config = state.config['get-results'] ,
        logger = state.logger
    )

def main() :

    uvicorn.run(
        app , 
        host = '0.0.0.0' , 
        port = 8000
    )
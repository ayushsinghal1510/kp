import os
import uvicorn

from logging import Logger
from dotenv import load_dotenv
from pymongo import MongoClient
from deepgram import DeepgramClient
from contextlib import asynccontextmanager

from fastapi import FastAPI , Request , HTTPException 

from google.genai import Client

from fastapi.middleware.cors import CORSMiddleware

from .loader import load_all_clients
from .services import env_str_to_bool , env_str_to_list
from .routers import add_scenario_route , edit_scenario_route

load_dotenv()

class AppState : 

    deepgram_client : DeepgramClient
    gemini_client : Client

    config : dict
    logger : Logger
    llm_client : dict
    mongo_client : MongoClient

state = AppState()

@asynccontextmanager
async def lifespan(app : FastAPI) : 

    deepgram_client , config , logger , gemini_client , mongo_client = load_all_clients()
    
    state.config = config
    state.logger = logger
    state.gemini_client = gemini_client
    state.deepgram_client = deepgram_client
    state.mongo_client = mongo_client
    
    logger.info("System Startup: Models and Config Loaded.")
    
    yield
    
    logger.info("System Shutdown.")

app = FastAPI(lifespan = lifespan)

app.add_middleware(
    CORSMiddleware , 
    allow_origins = env_str_to_list(os.environ['ALLOWED_ORIGINS']) , 
    allow_credentials = env_str_to_bool(os.environ['ALLOWED_CREDENTIALS']) , 
    allow_methods = env_str_to_list(os.environ['ALLOWED_METHODS']) , 
    allow_headers = env_str_to_list(os.environ['ALLOWED_HEADERS']) 
)

@app.post('/add-scenario')
async def add_scenario(request : Request) -> dict : 

    data : dict = await request.json()

    if ('scenario_prompt' not in data) : raise HTTPException(
        status_code = 400 , 
        detail = "Missing 'scenario_prompt' in request body."
    )

    response : dict = await add_scenario_route(
        query = data['scenario_prompt'] , 
        mongo_client = state.mongo_client , 
        gemini_client = state.gemini_client , 
        config = state.config['add-scenario']
    )

    return {'response' : response}

@app.post('/edit-scenario')
async def edit_scenario(request : Request) -> dict : 

    data : dict = await request.json()

    if ('api_key' not in data or 'scenario_prompt' not in data) : raise HTTPException(
        status_code = 400 , 
        detail = "Missing 'api_key' or 'scenario_prompt' in request body."
    )

    response : dict = await edit_scenario_route(
        query = data['scenario_prompt'] , 
        mongo_client = state.mongo_client , 
        gemini_client = state.gemini_client , 
        config = state.config['edit-scenario'] , 
        api_key = data['api_key']
    )

    return {'response' : response}

def main() : uvicorn.run(
    app , 
    host = '0.0.0.0' , 
    port = 8888
)
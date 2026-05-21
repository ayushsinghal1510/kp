import uvicorn
from contextlib import asynccontextmanager

from .state import AppState

from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI, Request
from services import env_str_to_bool , env_str_to_list

from dotenv import load_dotenv

load_dotenv()

state = AppState()

@asynccontextmanager
async def lifespan(app : FastAPI) : 

    print("System Startup: Models and Config Loaded.")

    yield

    print("System Shutdown.")

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

@app.post('/')
async def process_new_session(request : Request) : 

    print(await request.json())

def main() : 

    uvicorn.run(
        app , 
        host = '0.0.0.0' , 
        port = 9999
    )
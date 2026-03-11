
from contextlib import asynccontextmanager
import os
from bson.objectid import ObjectId
from pymongo.results import InsertOneResult

from .loader import load_clients

from .state import AppState
from fastapi.middleware.cors import CORSMiddleware

from fastapi import FastAPI
from services import env_str_to_bool , env_str_to_list

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
    allow_origins = env_str_to_list(os.environ['ALLOWED_ORIGINS']) , 
    allow_credentials = env_str_to_bool(os.environ['ALLOWED_CREDENTIALS']) , 
    allow_methods = env_str_to_list(os.environ['ALLOWED_METHODS']) , 
    allow_headers = env_str_to_list(os.environ['ALLOWED_HEADERS']) 
)

@app.get('/')
async def read_root() : return {'Hello' : 'World'}

@app.post('/')
def process_new_session(api_input) : 

    student_id = api_input['student_id']
    scenario_id = api_input['scenario_id']

    session_doc = {
        'transcription' : transcription , 
        'feedback' : feedback , 
        'summary' : summary , 
        'score' : score , 
        'student_id' : student_id , 
        'scenario_id' : scenario_id , 
        # ! Add created and updated at here 
    }

    session_result : InsertOneResult = state.sessions_collection.insert_one(session_doc)
    new_session_id : str = str(session_result.inserted_id)

    # --- STEP 2: UPDATE STUDENT TABLE ---
    # Goal: Append to session_list[scenario_id]. If key doesn't exist, create it.
    # We use the '$push' operator which handles list creation automatically.
    # The key is dynamic, so we use a string-based key path.
    
    student_update_path = f"session_list.{scenario_id}"
    
    state.students_collection.update_one(
        {"_id": ObjectId(student_id) if isinstance(student_id, str) else student_id},
        {"$push": {student_update_path: new_session_id}},
        upsert = True
    )

    state.scenarios_collection.update_one(
        {"_id" : ObjectId(scenario_id) if isinstance(scenario_id , str) else scenario_id} , 
        {"$push" : {"sessions" : new_session_id}} , 
        upsert = True
    )

    return new_session_id

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    example_input = {
        "transcription": "The student discussed the merits of renewable energy.",
        "student_id": "65cb1234af1234567890abcd", # Example Hex ID
        "scenario_id": "scen_99"
    }

    try:
        final_pk = process_new_session(example_input)
        print(f"Successfully processed! New Session ID: {final_pk}")
    except Exception as e:
        print(f"An error occurred: {e}")
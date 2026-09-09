from logging import Logger
import os
from typing import Any
from google.genai import Client
from pymongo import MongoClient
# from pymongo.cursor import Collection
from pymongo.synchronous.database import Database
from services import load_config , load_logger

# * Imported defensively : the deployed box may not have run `uv sync` since groq was
# * added , and a hard import would take the whole service down at boot rather than
# * leaving it running on Gemini alone.
try : from groq import Groq
except ImportError : Groq = None

def load_gemini_client() -> Client : return Client(api_key = os.environ['GEMINI_API_KEY'])

def load_groq_client(logger : Logger | None = None) -> Any | None :
    '''
    The Groq client used when Gemini fails , or None if it cannot be built.

    # * Optional rather than required , so a box with no GROQ_API_KEY keeps working
    # * exactly as it did before — Gemini , then the canned fallback result.
    '''

    if Groq is None :

        if logger : logger.warning('groq is not installed , Gemini has no fallback (run uv sync).')

        return None

    api_key = os.environ.get('GROQ_API_KEY')

    if not api_key :

        if logger : logger.warning('GROQ_API_KEY is not set , Gemini has no fallback.')

        return None

    return Groq(api_key = api_key)

def load_mongo_clients(config : dict) -> tuple[
    MongoClient ,
    Any ,
    Any ,
    Any
] :

    connection_string = os.environ['MONGO_URL']

    client : MongoClient = MongoClient(connection_string)

    db : Database = client[config['database-name']]
    students_col = db[config['students-collection-name']]
    scenarios_col = db[config['scenarios-collection-name']]
    sessions_col = db[config['sessions-collection-name']]

    return (
        client ,
        students_col ,
        scenarios_col ,
        sessions_col
    )

def load_clients() -> tuple[
    dict ,
    Logger ,
    Client ,
    Any | None ,
    Any ,
    Any ,
    Any
] :

    config : dict = load_config(config_file_path = 'config.yml')
    logger : Logger = load_logger(config = config['logger'])

    gemini_client : Client = load_gemini_client()
    groq_client = load_groq_client(logger = logger)

    (
        client ,
        students_collection ,
        scenarios_collection ,
        sessions_collection
    ) = load_mongo_clients(config = config['mongo'])

    return (
        config ,
        logger ,
        gemini_client ,
        groq_client ,
        students_collection ,
        scenarios_collection ,
        sessions_collection
    )

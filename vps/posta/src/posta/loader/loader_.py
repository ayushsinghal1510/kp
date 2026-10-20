from logging import Logger
import os
from typing import Any
from google.genai import Client
from pymongo import MongoClient
# from pymongo.cursor import Collection
from pymongo.synchronous.database import Database
from services import load_config , load_logger

def load_gemini_client() -> Client : return Client(api_key = os.environ['GEMINI_API_KEY'])

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
    Any ,
    Any ,
    Any
] :

    config : dict = load_config(config_file_path = 'config.yml')
    logger : Logger = load_logger(config = config['logger'])

    gemini_client : Client = load_gemini_client()

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
        students_collection ,
        scenarios_collection ,
        sessions_collection
    )

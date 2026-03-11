from logging import Logger
import os
from pymongo import MongoClient
from pymongo.cursor import Collection
from pymongo.synchronous.database import Database
from services import load_config , load_logger

def load_mongo_clients() -> tuple[
    MongoClient , 
    Collection , 
    Collection , 
    Collection
] : 

    connection_string = os.environ['MONGO_URL']

    client : MongoClient = MongoClient(connection_string)

    db : Database = client['school_database']
    students_col : Collection = db['students']
    scenarios_col : Collection = db['scenarios']
    sessions_col : Collection = db['sessions']

    return (
        client , 
        students_col , 
        scenarios_col , 
        sessions_col
    )

def load_clients() -> tuple[
    dict , 
    Logger , 
    Collection , 
    Collection , 
    Collection
] :  

    config : dict = load_config(config_file_path = 'config.yml')
    logger : Logger = load_logger(config = config['logger'])

    (
        client , 
        students_collection , 
        scenarios_collection , 
        sessions_collection
    ) = load_mongo_clients()

    return (
        config , 
        logger , 
        students_collection , 
        scenarios_collection , 
        sessions_collection
    )
import os
import yaml
from deepgram import DeepgramClient
from google.genai import Client 

from google.genai.types import (
    GenerateContentConfig , ThinkingConfig , 
    Part , Content
)
import os
from pymongo import MongoClient

from logging import (
    Logger , getLogger , 
    StreamHandler , Formatter , 
    DEBUG , INFO , WARNING , ERROR , CRITICAL , 
    LogRecord
)

def load_mongo_client() -> MongoClient : 

    client : MongoClient = MongoClient(os.environ['MONGO_URL'])

    return client 

def load_deepgram_client() -> DeepgramClient : 

    client : DeepgramClient = DeepgramClient(api_key = os.environ['DEEPGRAM_API_KEY'])

    return client 

def load_config() -> dict : 

    with open('config.yml') as config_file : 

        config : dict = yaml.safe_load(config_file)

    return config

def load_gemini_client() -> Client : 

    client : Client = Client(api_key = os.environ['GEMINI_API_KEY'])

    return client

class ColoredFormatter(Formatter) : 

    def __init__(
        self , 
        fmt : str , 
        config : dict , 
        datefmt : str | None = None
    ) -> None :

        super().__init__(fmt , datefmt)
        
        self.COLORS = {
            DEBUG : config['color']['debug'] ,
            INFO : config['color']['info'] , 
            WARNING : config['color']['warning'] , 
            ERROR : config['color']['error'] , 
            CRITICAL : config['color']['critical']
        }

        self.RESET = config['color']['reset']

        self.fmt = fmt

    def format(self , record : LogRecord) -> str : 

        color = self.COLORS.get(record.levelno)

        if color : log_fmt = color + self.fmt + self.RESET
        else : log_fmt = self.fmt

        formatter = Formatter(log_fmt , self.datefmt)

        return formatter.format(record)

def load_logger(config : dict) -> Logger:
    
    logger: Logger = getLogger(__name__)
    logger.setLevel(DEBUG) 

    if logger.handlers : 

        for handler in logger.handlers : logger.removeHandler(handler)

    console_handler = StreamHandler()

    log_format = config['log-format']

    formatter = ColoredFormatter(
        fmt = log_format , 
        config = config , 
        datefmt = ''
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger

def load_all_clients() -> tuple[DeepgramClient , dict , Logger , Client , MongoClient] : 

    deepgram_client : DeepgramClient = load_deepgram_client()

    config : dict = load_config()

    gemini_client : Client = load_gemini_client()
    logger : Logger = load_logger(config['logger'])
    mongo_client : MongoClient = load_mongo_client()

    return deepgram_client , config , logger , gemini_client , mongo_client
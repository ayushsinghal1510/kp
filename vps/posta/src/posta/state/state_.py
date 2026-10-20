from logging import Logger
from typing import Any

from google.genai import Client

# from posta.loader import Collection

class AppState :

    config : dict
    logger : Logger

    gemini_client : Client

    students_collection : Any
    scenarios_collection : Any
    sessions_collection : Any

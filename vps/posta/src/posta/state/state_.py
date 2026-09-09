from logging import Logger
from typing import Any

from google.genai import Client

# from posta.loader import Collection

class AppState :

    config : dict
    logger : Logger

    gemini_client : Client

    # * None when groq is uninstalled or GROQ_API_KEY is unset — see load_groq_client
    groq_client : Any | None

    students_collection : Any
    scenarios_collection : Any
    sessions_collection : Any

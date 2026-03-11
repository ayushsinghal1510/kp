from logging import Logger

from posta.loader import Collection

class AppState : 

    config : dict
    logger : Logger

    students_collection : Collection
    scenarios_collection : Collection 
    sessions_collection : Collection
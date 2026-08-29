import json
import traceback
from typing import Any
from logging import Logger

from bson.objectid import ObjectId
from bson.errors import InvalidId

from google.genai import Client
from google.genai.types import GenerateContentConfig

from fastapi import HTTPException

from ..llm import run_json_gemini
from ..services import create_generation_config , json_to_google_chat

def _to_object_id(value : str , field : str) -> ObjectId :

    try : return ObjectId(value)

    except (InvalidId , TypeError) : raise HTTPException(
        status_code = 400 ,
        detail = f"'{field}' is not a valid id : {value!r}"
    )

def _transcription_to_text(transcription : Any) -> str :
    '''
    The transcription arrives either as a plain string or as a conversation history list
    (the shape `chat.voxio.in` returns in `diagnosis_conversation_history`). Normalise both
    into one readable block for the assessor prompt.
    '''

    if transcription is None : return ''

    if isinstance(transcription , str) : return transcription.strip()

    if isinstance(transcription , list) :

        lines : list = []

        for row in transcription :

            if isinstance(row , dict) :

                role : str = str(row.get('role') or row.get('speaker') or 'unknown')
                content : str = str(row.get('content') or row.get('text') or row.get('message') or '')

                lines.append(f'{role} : {content}')

            else : lines.append(str(row))

        return '\n'.join(lines).strip()

    return str(transcription).strip()

def _coerce_score(value : Any) -> int :
    '''Clamps whatever the model returned into a 0-100 integer.'''

    try : score : int = int(float(value))
    except (TypeError , ValueError) : return 0

    return max(0 , min(100 , score))

async def get_results_route(
    scenario_id : str ,
    transcription : Any ,
    session_id : str ,
    user_id : str ,
    scenarios_collection : Any ,
    sessions_collection : Any ,
    gemini_client : Client ,
    config : dict ,
    logger : Logger
) -> dict :

    scenario_object_id : ObjectId = _to_object_id(scenario_id , 'scenario_id')

    scenario : dict | None = scenarios_collection.find_one({'_id' : scenario_object_id})

    if scenario is None : raise HTTPException(
        status_code = 404 ,
        detail = f'No scenario found with scenario_id : {scenario_id}'
    )

    scenario_prompt : str = scenario.get('scenario_prompt' , '')

    if not scenario_prompt : raise HTTPException(
        status_code = 422 ,
        detail = f'Scenario {scenario_id} has no scenario_prompt to assess against.'
    )

    transcription_text : str = _transcription_to_text(transcription)

    # * Short-circuit before spending a Gemini call on an empty consultation
    if not transcription_text :

        logger.warning(f'Empty transcription for session_id : {session_id} , scoring 0.')

        return {
            'score' : 0 ,
            'overall_feedback' : 'No consultation was recorded for this session , so there is nothing to assess.'
        }

    with open(config['prompt-path']) as system_prompt_file :
        system_prompt : str = system_prompt_file.read()

    generation_config : GenerateContentConfig = await create_generation_config(system_prompt)

    query : str = json.dumps({
        'scenario_prompt' : scenario_prompt ,
        'movements' : scenario.get('movements' , {}) ,
        'difficulty' : scenario.get('difficulty_status' , '') ,
        'questions_for_feedback' : scenario.get('questions_for_feedback' , []) ,
        'transcription' : transcription_text
    } , default = str)

    contents : list = await json_to_google_chat([{
        'role' : 'user' ,
        'content' : query
    }])

    response : dict = await run_json_gemini(
        gemini_client = gemini_client ,
        contents = contents ,
        generation_config = generation_config ,
        model = config['model'] ,
        logger = logger
    )

    result : dict = {
        'score' : _coerce_score(response.get('score')) ,
        'overall_feedback' : str(response.get('overall_feedback' , '')).strip()
    }

    logger.info(f'Assessed session_id : {session_id} , scenario_id : {scenario_id} , score : {result["score"]}')

    if config.get('persist-to-session') : _persist_to_session(
        result = result ,
        session_id = session_id ,
        user_id = user_id ,
        scenario_id = scenario_id ,
        sessions_collection = sessions_collection ,
        logger = logger
    )

    return result

def _persist_to_session(
    result : dict ,
    session_id : str ,
    user_id : str ,
    scenario_id : str ,
    sessions_collection : Any ,
    logger : Logger
) -> None :
    '''
    Best-effort write of the score back onto the session doc.

    Never raises — the caller has a valid result to return either way , so a Mongo problem
    here must not turn a successful assessment into a 500.
    '''

    try :

        update_result = sessions_collection.update_one(
            {'session_id' : session_id} ,
            {'$set' : {
                'score' : result['score'] ,
                'overall_feedback' : result['overall_feedback']
            }}
        )

        if update_result.matched_count == 0 : logger.warning(
            f'No session doc with session_id : {session_id} '
            f'(student_id : {user_id} , scenario_id : {scenario_id}) , score not persisted.'
        )

    except Exception as e : logger.error(
        f'Failed to persist score for session_id {session_id} : {e} , {traceback.format_exc()}'
    )

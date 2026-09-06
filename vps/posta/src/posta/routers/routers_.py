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

# * Fields a short scenario code may be stored under. `scenarioCode` is what posta writes ,
# * `ScenarioId` is the name the frontend / Bubble export uses.
SCENARIO_CODE_FIELDS : tuple = ('scenarioCode' , 'ScenarioId' , 'scenarioId' , 'scenario_code')

def _find_scenario(scenarios_collection : Any , scenario_id : str) -> dict | None :
    '''
    Resolves a scenario by Mongo `_id` **or** by short code.

    # * The frontend sends a short code such as '9C2F7X' rather than an ObjectId , so an id that
    # * is not a valid ObjectId is not an error — it is looked up against the code fields instead.
    '''

    try : scenario = scenarios_collection.find_one({'_id' : ObjectId(scenario_id)})

    except (InvalidId , TypeError) : scenario = None

    if scenario is not None : return scenario

    return scenarios_collection.find_one({
        '$or' : [{field : scenario_id} for field in SCENARIO_CODE_FIELDS]
    })

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

def _first_present(doc : dict , *names : str) -> Any :
    '''Returns the first of `names` present and non-empty on `doc`.'''

    for name in names :

        value = doc.get(name)

        if value : return value

    return None

def _to_question_list(value : Any) -> list :
    '''
    `aiQuestions` is stored as one newline-separated string , while `questions_for_feedback`
    is a list. Normalise either into a list of questions.
    '''

    if not value : return []

    if isinstance(value , str) : return [line.strip() for line in value.splitlines() if line.strip()]

    if isinstance(value , list) : return [str(item).strip() for item in value if str(item).strip()]

    return [str(value)]

def _extract_scenario(scenario : dict) -> dict :
    '''
    Reads a scenario doc into the rubric fields the assessor prompt needs.

    # ! Two schemas exist for this collection. The live docs are camelCase and owned by the
    # ! Node app (`scenarioPrompt` , `aiQuestions` , `difficulty` , `animationTriggers`) , while
    # ! `vps/server` writes snake_case (`scenario_prompt` , `questions_for_feedback` ,
    # ! `difficulty_status` , `movements`). Both are accepted , camelCase first.
    '''

    return {
        'scenario_prompt' : _first_present(scenario , 'scenarioPrompt' , 'scenario_prompt') or '' ,
        'movements' : _first_present(scenario , 'animationTriggers' , 'movements') or {} ,
        'difficulty' : _first_present(scenario , 'difficulty' , 'difficulty_status') or '' ,
        'questions_for_feedback' : _to_question_list(
            _first_present(scenario , 'aiQuestions' , 'questions_for_feedback')
        )
    }

def _coerce_score(value : Any) -> float :
    '''
    Clamps whatever the model returned into a 0-10 score with one decimal place.

    # * A clearly out-of-100 value is rescaled , since the model occasionally reverts to the
    # * more familiar 100-point scale despite the prompt. The threshold sits above 10 so a
    # * small overshoot such as 10.4 clamps to 10 rather than being rescaled to 1.
    '''

    try : score : float = float(value)
    except (TypeError , ValueError) : return 0.0

    if score > 11 : score = score / 10

    return round(max(0.0 , min(10.0 , score)) , 1)

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

    logger.info(f'get-results : scenario_id = {scenario_id!r} , session_id = {session_id!r} , user_id = {user_id!r}')

    scenario : dict | None = _find_scenario(scenarios_collection , scenario_id)

    if scenario is None :

        logger.warning(f'No scenario matched _id or {SCENARIO_CODE_FIELDS} for scenario_id : {scenario_id!r}')

        raise HTTPException(
            status_code = 404 ,
            detail = f'No scenario found with scenario_id : {scenario_id}'
        )

    rubric : dict = _extract_scenario(scenario)

    if not rubric['scenario_prompt'] : raise HTTPException(
        status_code = 422 ,
        detail = f'Scenario {scenario_id} has no scenarioPrompt to assess against.'
    )

    transcription_text : str = _transcription_to_text(transcription)

    # * Short-circuit before spending a Gemini call on an empty consultation
    if not transcription_text :

        logger.warning(f'Empty transcription for session_id : {session_id} , scoring 0.')

        return {
            'score' : 0.0 ,
            'overall_feedback' : 'No consultation was recorded for this session , so there is nothing to assess.'
        }

    with open(config['prompt-path']) as system_prompt_file :
        system_prompt : str = system_prompt_file.read()

    generation_config : GenerateContentConfig = await create_generation_config(system_prompt)

    query : str = json.dumps({
        **rubric ,
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

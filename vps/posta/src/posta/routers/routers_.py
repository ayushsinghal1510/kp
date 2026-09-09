import json
import re
import traceback
from typing import Any
from logging import Logger
from datetime import datetime , timezone

from bson.objectid import ObjectId
from bson.errors import InvalidId

from google.genai import Client
from google.genai.types import GenerateContentConfig

from fastapi import HTTPException

from ..llm import FALLBACK_RESULT , GROQ_MODEL , run_json_with_fallback
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
    logger : Logger ,
    groq_client : Any | None = None
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

    response : dict = await run_json_with_fallback(
        gemini_client = gemini_client ,
        contents = contents ,
        generation_config = generation_config ,
        model = config['model'] ,
        groq_client = groq_client ,
        groq_model = config.get('groq-model' , GROQ_MODEL) ,
        logger = logger
    )

    result : dict = {
        'score' : _coerce_score(response.get('score')) ,
        'overall_feedback' : str(response.get('overall_feedback' , '')).strip()
    }

    # ! Both providers failed , so `result` is the canned FALLBACK_RESULT and its 0.0 is not
    # ! a mark — it is an outage. Persisting it would put a zero on the student's record
    # ! that reads identically to a consultation they genuinely failed , and would now also
    # ! create a session doc where none existed. The caller still gets the apology text.
    is_fallback : bool = result['overall_feedback'] == FALLBACK_RESULT['overall_feedback']

    if is_fallback : logger.error(
        f'Assessment unavailable for session_id : {session_id} , scenario_id : {scenario_id} , '
        'not persisting the fallback score.'
    )

    else : logger.info(
        f'Assessed session_id : {session_id} , scenario_id : {scenario_id} , score : {result["score"]}'
    )

    if config.get('persist-to-session') and not is_fallback : _persist_to_session(
        result = result ,
        session_id = session_id ,
        user_id = user_id ,
        scenario_id = scenario_id ,
        transcription = transcription ,
        sessions_collection = sessions_collection ,
        logger = logger
    )

    return result

_SPEAKER_LINE = re.compile(r'^([^:]{1,40}?)\s*:\s*(.*)$')

def _parse_dialogue(text : str) -> list :
    '''
    Split a `Speaker: line` transcript into `{role , content}` turns.

    # * The chat platform sends the consultation as one string , e.g.
    # *     'h: Hello.\\r\\nJohn Smith: Hello.'
    # * Stored whole it renders as a single turn attributed to the student , with the
    # * patient's replies buried inside it.
    # *
    # * Roles come from the order speakers first appear : the student opens the
    # * consultation , so the first label seen is 'user' and every other label is
    # * 'assistant'. Names are not matched against the scenario , since the persona
    # * name is not reliably the label used here.
    '''

    turns : list = []
    speakers : list = []

    for raw_line in text.replace('\r\n' , '\n').replace('\r' , '\n').split('\n') :

        line : str = raw_line.strip()

        if not line : continue

        match = _SPEAKER_LINE.match(line)

        # * A line with no 'Speaker:' prefix is a continuation of the turn above ,
        # * not a new one — a wrapped paragraph must not become its own bubble.
        if match is None :

            if turns : turns[-1]['content'] += ' ' + line

            continue

        label : str = match.group(1).strip()
        said : str = match.group(2).strip()

        if not label : continue

        if label not in speakers : speakers.append(label)

        role : str = 'user' if speakers.index(label) == 0 else 'assistant'

        # * `speaker` keeps the label the transcript used , so the dashboard can print
        # * 'h:' and 'John Smith:' rather than a generic 'User:' / 'Assistant:'
        if said : turns.append({'role' : role , 'content' : said , 'speaker' : label})

    # * No speaker labels at all : keep the text rather than losing the transcript
    if not turns and text.strip() : return [{'role' : 'user' , 'content' : text.strip()}]

    return turns

def _normalise_transcription(transcription : Any) -> list :
    '''
    Shape the conversation for the dashboard's session schema : a list of
    `{role , content}` with role limited to system / user / assistant.

    # * Gemini-style 'model' becomes 'assistant' , and anything malformed is dropped
    # * rather than stored , since one unusable line must not spoil the whole transcript.
    '''

    if isinstance(transcription , str) : return _parse_dialogue(transcription)

    if not isinstance(transcription , list) : return []

    normalised : list = []

    for entry in transcription :

        if not isinstance(entry , dict) : continue

        role = 'assistant' if entry.get('role') == 'model' else entry.get('role')
        content = entry.get('content' , entry.get('text'))

        if role not in ('system' , 'user' , 'assistant') : continue
        if content is None : continue

        normalised.append({
            'role' : role ,
            'content' : str(content) ,
            'speaker' : str(entry.get('speaker' , entry.get('name' , '')))
        })

    return normalised

def _id_variants(value : Any) -> list :
    '''
    Both spellings of an id , since these collections hold a mix.

    # * `/session` writes `student_id` straight from the JWE payload , which is a string ,
    # * while docs created by the Node app carry an ObjectId. A query on one form silently
    # * misses the other , so both are offered to `$in`.
    '''

    if value is None : return []

    variants : list = [value]

    if isinstance(value , str) :
        try : variants.append(ObjectId(value))
        except (InvalidId , TypeError) : pass

    else : variants.append(str(value))

    return variants

def _find_session_doc(
    sessions_collection : Any ,
    session_id : str ,
    user_id : str ,
    scenario_id : str ,
    logger : Logger
) -> dict | None :
    '''
    Locates the session doc to write the score onto.

    `session_id` first , then the newest session for this student and scenario.

    # ! Callers routinely send an empty `session_id` — the whole reason scores were being
    # ! computed and then dropped. The student and scenario ids do arrive , and a student
    # ! can only be in one consultation at a time , so the newest of their sessions for
    # ! this scenario is the one just finished. `_id` descending is the ordering : these
    # ! docs have no createdAt , but an ObjectId leads with its timestamp.
    '''

    if session_id :

        doc = sessions_collection.find_one({'session_id' : session_id})

        if doc is not None : return doc

    student_variants : list = _id_variants(user_id)
    scenario_variants : list = _id_variants(scenario_id)

    if not student_variants or not scenario_variants : return None

    doc = sessions_collection.find_one(
        {
            'student_id' : {'$in' : student_variants} ,
            'scenario_id' : {'$in' : scenario_variants}
        } ,
        sort = [('_id' , -1)]
    )

    if doc is not None : logger.info(
        f'session_id {session_id!r} did not match ; falling back to the newest session '
        f'for student_id {user_id!r} + scenario_id {scenario_id!r} : _id = {doc["_id"]} , '
        f'session_id = {doc.get("session_id")!r}'
    )

    return doc

def _persist_to_session(
    result : dict ,
    session_id : str ,
    user_id : str ,
    scenario_id : str ,
    transcription : Any ,
    sessions_collection : Any ,
    logger : Logger
) -> None :
    '''
    Best-effort write of the score back onto the session doc.

    Never raises — the caller has a valid result to return either way , so a Mongo problem
    here must not turn a successful assessment into a 500.
    '''

    try :

        session_doc : dict | None = _find_session_doc(
            sessions_collection = sessions_collection ,
            session_id = session_id ,
            user_id = user_id ,
            scenario_id = scenario_id ,
            logger = logger
        )

        normalised_transcription : list = _normalise_transcription(transcription)

        # * `feedback` and `transcription` are what the dashboard actually reads ;
        # * `overall_feedback` is kept alongside it so nothing already reading that
        # * key breaks. Without these three the UI shows a scored session with an
        # * empty transcript and no written feedback.
        update : dict = {
            'score' : result['score'] ,
            'feedback' : result['overall_feedback'] ,
            'overall_feedback' : result['overall_feedback'] ,
            'transcription' : normalised_transcription ,
            'updatedAt' : datetime.now(timezone.utc)
        }

        if session_doc is None :

            # ! No doc to attach to , so the assessment becomes one. Without this the
            # ! transcript and score are computed , logged , returned , and then lost —
            # ! nothing reaches the dashboard at all. Written with the ids as sent so a
            # ! later /get-results for the same student and scenario finds it.
            insert_doc : dict = {
                'session_id' : session_id ,
                'student_id' : user_id ,
                'scenario_id' : scenario_id ,
                'createdAt' : datetime.now(timezone.utc) ,
                **update
            }

            insert_result = sessions_collection.insert_one(insert_doc)

            logger.warning(
                f'No session doc for session_id {session_id!r} '
                f'(student_id : {user_id} , scenario_id : {scenario_id}) , '
                f'created one : _id = {insert_result.inserted_id} , score = {result["score"]}'
            )

            return

        update_result = sessions_collection.update_one(
            {'_id' : session_doc['_id']} ,
            {'$set' : update}
        )

        logger.info(
            f'Mongo write : _id = {session_doc["_id"]} , session_id = {session_id!r} , '
            f'user_id = {user_id!r} , scenario_id = {scenario_id!r} , score = {result["score"]} , '
            f'matched = {update_result.matched_count} , modified = {update_result.modified_count} , '
            f'turns = {len(normalised_transcription)}'
        )

    except Exception as e : logger.error(
        f'Failed to persist score for session_id {session_id} : {e} , {traceback.format_exc()}'
    )

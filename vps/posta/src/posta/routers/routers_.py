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

from ..llm import FALLBACK_MARKER , GROQ_MODEL , run_json_with_fallback
from ..services import Trace , create_generation_config , json_to_google_chat

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
    groq_client : Any | None = None ,
    trace : Trace | None = None
) -> dict :

    # * Optional so an older caller still works ; a no-op stand-in keeps every call
    # * site below unconditional rather than guarded by `if trace`
    if trace is None : trace = Trace(tag = 'get-results' , logger = logger , request_id = '-')

    trace.log('identifiers' , {
        'scenario_id' : scenario_id ,
        'session_id' : session_id ,
        'user_id' : user_id ,
        'transcription-type' : type(transcription).__name__ ,
        'transcription-turns' : len(transcription) if isinstance(transcription , list) else None
    })

    scenario : dict | None = _find_scenario(scenarios_collection , scenario_id)

    if scenario is None :

        trace.warn('no scenario matched by _id or by short code' , {
            'scenario_id' : scenario_id ,
            'code-fields-tried' : list(SCENARIO_CODE_FIELDS)
        })

        raise HTTPException(
            status_code = 404 ,
            detail = f'No scenario found with scenario_id : {scenario_id}'
        )

    trace.log('resolved the scenario' , {
        '_id' : scenario.get('_id') ,
        'name' : scenario.get('scenarioName') or scenario.get('scenario_name') ,
        'fields' : sorted(scenario)
    })

    rubric : dict = _extract_scenario(scenario)

    # * The rubric the assessment is actually graded against , after both schemas have
    # * been read. Sizes rather than the prose , which the payload log already holds.
    trace.log('extracted the rubric' , {
        'scenario_prompt-chars' : len(rubric['scenario_prompt']) ,
        'difficulty' : rubric['difficulty'] ,
        'questions' : rubric['questions_for_feedback'] ,
        'movements' : rubric['movements']
    })

    if not rubric['scenario_prompt'] :

        trace.warn('scenario has no prompt to assess against' , {'scenario_id' : scenario_id})

        raise HTTPException(
            status_code = 422 ,
            detail = f'Scenario {scenario_id} has no scenarioPrompt to assess against.'
        )

    transcription_text : str = _transcription_to_text(transcription)

    trace.log('flattened the transcription' , {'chars' : len(transcription_text)})

    # * Short-circuit before spending a Gemini call on an empty consultation
    if not transcription_text :

        trace.warn('empty transcription , scoring 0 without calling a model' , {
            'session_id' : session_id
        })

        return {
            'score' : 0.0 ,
            'overall_feedback' : 'No consultation was recorded for this session , so there is nothing to assess.'
        }

    with open(config['prompt-path']) as system_prompt_file :
        system_prompt : str = system_prompt_file.read()

    trace.log('loaded the assessor prompt' , {
        'path' : config['prompt-path'] ,
        'chars' : len(system_prompt)
    })

    generation_config : GenerateContentConfig = await create_generation_config(system_prompt)

    query : str = json.dumps({
        **rubric ,
        'transcription' : transcription_text
    } , default = str)

    contents : list = await json_to_google_chat([{
        'role' : 'user' ,
        'content' : query
    }])

    # * Prompt size is the usual cause of a slow or truncated answer , and it grows
    # * with the transcript rather than with anything visible in the request
    trace.log('calling the model' , {
        'model' : config['model'] ,
        'groq-model' : config.get('groq-model' , GROQ_MODEL) ,
        'groq-configured' : groq_client is not None ,
        'query-chars' : len(query)
    })

    response : dict = await run_json_with_fallback(
        gemini_client = gemini_client ,
        contents = contents ,
        generation_config = generation_config ,
        model = config['model'] ,
        groq_client = groq_client ,
        groq_model = config.get('groq-model' , GROQ_MODEL) ,
        logger = logger
    )

    # * Raw score before coercion , because _coerce_score rescales anything over 11 :
    # * a stored 1.8 that the model actually returned as 18 is otherwise unexplainable
    trace.log('model returned' , {
        'keys' : sorted(response) ,
        'raw-score' : response.get('score') ,
        'feedback-chars' : len(str(response.get('overall_feedback' , '')))
    })

    result : dict = {
        'score' : _coerce_score(response.get('score')) ,
        'overall_feedback' : str(response.get('overall_feedback' , '')).strip()
    }

    trace.log('coerced the score' , {
        'from' : response.get('score') ,
        'to' : result['score']
    })

    # ! Both providers failed , so `result` is the mock FALLBACK_RESULT. The caller gets it
    # ! — a student staring at a blank feedback screen is the thing being avoided — but it
    # ! is not written to the database : nothing about that 5.0 came from the student's own
    # ! consultation , and with the insert path below it would mint a whole session doc out
    # ! of an API outage. Read off the marker rather than the feedback text , so an edit to
    # ! the wording cannot quietly turn mock results into persisted ones.
    is_fallback : bool = bool(response.get(FALLBACK_MARKER))

    if is_fallback : trace.warn(
        f'Assessment unavailable for session_id : {session_id} , scenario_id : {scenario_id} , '
        f'user_id : {user_id} — returning the mock score {result["score"]} to the caller and '
        'not persisting it. The transcript is unassessed ; re-run this session once the '
        'provider recovers.'
    )

    else : trace.log('assessed' , {
        'session_id' : session_id ,
        'scenario_id' : scenario_id ,
        'score' : result['score']
    })

    if not config.get('persist-to-session') :
        trace.warn('persist-to-session is off in config.yml , the score is returned but not stored')

    if config.get('persist-to-session') and not is_fallback : _persist_to_session(
        result = result ,
        session_id = session_id ,
        user_id = user_id ,
        scenario_id = scenario_id ,
        transcription = transcription ,
        sessions_collection = sessions_collection ,
        logger = logger ,
        trace = trace
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
    logger : Logger ,
    trace : Trace | None = None
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

    if trace is None : trace = Trace(tag = 'persist' , logger = logger , request_id = '-')

    if session_id :

        doc = sessions_collection.find_one({'session_id' : session_id})

        trace.log('lookup by session_id' , {
            'session_id' : session_id ,
            'found' : doc is not None ,
            '_id' : doc['_id'] if doc is not None else None
        })

        if doc is not None : return doc

    else : trace.warn('no session_id was sent , falling back to newest-session lookup')

    student_variants : list = _id_variants(user_id)
    scenario_variants : list = _id_variants(scenario_id)

    if not student_variants or not scenario_variants :

        trace.warn('cannot fall back : student or scenario id is missing' , {
            'student-variants' : student_variants ,
            'scenario-variants' : scenario_variants
        })

        return None

    trace.log('lookup by newest session for student + scenario' , {
        'student-variants' : student_variants ,
        'scenario-variants' : scenario_variants
    })

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
    logger : Logger ,
    trace : Trace | None = None
) -> None :
    '''
    Best-effort write of the score back onto the session doc.

    Never raises — the caller has a valid result to return either way , so a Mongo problem
    here must not turn a successful assessment into a 500.
    '''

    if trace is None : trace = Trace(tag = 'persist' , logger = logger , request_id = '-')

    try :

        trace.log('persisting the score' , {
            'session_id' : session_id ,
            'user_id' : user_id ,
            'scenario_id' : scenario_id ,
            'score' : result['score']
        })

        session_doc : dict | None = _find_session_doc(
            sessions_collection = sessions_collection ,
            session_id = session_id ,
            user_id = user_id ,
            scenario_id = scenario_id ,
            logger = logger ,
            trace = trace
        )

        normalised_transcription : list = _normalise_transcription(transcription)

        trace.log('normalised the transcript for storage' , {
            'turns' : len(normalised_transcription) ,
            'roles' : [turn['role'] for turn in normalised_transcription] ,
            'speakers' : sorted({turn.get('speaker' , '') for turn in normalised_transcription})
        })

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

            trace.log('no session doc matched , inserting one' , insert_doc)

            insert_result = sessions_collection.insert_one(insert_doc)

            trace.warn('created a session doc for an unmatched assessment' , {
                'session_id' : session_id ,
                'student_id' : user_id ,
                'scenario_id' : scenario_id ,
                'inserted_id' : insert_result.inserted_id ,
                'score' : result['score']
            })

            return

        trace.log('updating the session doc' , {
            'filter' : {'_id' : session_doc['_id']} ,
            '$set' : update
        })

        update_result = sessions_collection.update_one(
            {'_id' : session_doc['_id']} ,
            {'$set' : update}
        )

        # * matched = 1 , modified = 0 means the doc already held this exact score , which
        # * looks identical to a successful write from the outside
        trace.log('Mongo write' , {
            '_id' : session_doc['_id'] ,
            'session_id' : session_id ,
            'user_id' : user_id ,
            'scenario_id' : scenario_id ,
            'score' : result['score'] ,
            'matched' : update_result.matched_count ,
            'modified' : update_result.modified_count ,
            'turns' : len(normalised_transcription)
        })

    except Exception as e :

        # ! Swallowed on purpose : the caller has a valid result either way. Traced in full
        # ! so a silent 'score not showing on the dashboard' has an explanation here.
        trace.fail(e)

        logger.error(
            f'Failed to persist score for session_id {session_id} : {e} , {traceback.format_exc()}'
        )

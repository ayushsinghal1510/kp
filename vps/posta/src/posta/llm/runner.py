import ast
import json
import traceback
from logging import Logger
from typing import Any
from google.genai import Client
from google.genai.types import GenerateContentConfig

# * Returned when neither provider can be reached or will produce parseable JSON.
# * Kept as a module constant so callers can identify a fallback by its score / message.
FALLBACK_RESULT : dict = {
    'score' : 0.0 ,
    'overall_feedback' : 'Sorry we were having some issues generating your feedback. Please try again later.'
}

GROQ_MODEL : str = 'openai/gpt-oss-120b'

async def run_gemini(
    gemini_client : Client ,
    contents : list ,
    generation_config : GenerateContentConfig ,
    model : str = 'gemini-2.5-flash'
) -> str :

    response = ''

    for chunk in gemini_client.models.generate_content_stream(
        model = model ,
        contents = contents ,
        config = generation_config
    ) :
        if chunk.text : response += chunk.text

    return response

def _google_to_openai_messages(
    contents : list ,
    generation_config : GenerateContentConfig
) -> list :
    '''
    Re-shape a Gemini call into the OpenAI-style messages Groq expects.

    # * The two providers put the system prompt in different places : Gemini carries it
    # * out-of-band on the config as `system_instruction` , Groq wants it as the first
    # * message. Pulling it back out here means the fallback sends the *same* prompt and
    # * the same rubric as the primary , so a Groq assessment is comparable to a Gemini
    # * one rather than being scored against a different brief.
    '''

    messages : list = []

    system_instruction = getattr(generation_config , 'system_instruction' , None)

    if system_instruction :

        # * Accepts a bare string , a single Part , or the list of Parts posta builds
        parts = system_instruction if isinstance(system_instruction , list) else [system_instruction]

        system_prompt : str = ''.join(
            part if isinstance(part , str) else (getattr(part , 'text' , None) or '')
            for part in parts
        ).strip()

        if system_prompt : messages.append({
            'role' : 'system' ,
            'content' : system_prompt
        })

    for content in contents :

        # * Gemini's 'model' is Groq's 'assistant' ; everything else is a user turn
        role : str = 'assistant' if getattr(content , 'role' , 'user') == 'model' else 'user'

        text : str = ''.join(
            getattr(part , 'text' , None) or ''
            for part in (getattr(content , 'parts' , None) or [])
        ).strip()

        if text : messages.append({
            'role' : role ,
            'content' : text
        })

    return messages

async def run_groq(
    groq_client : Any ,
    messages : list ,
    model : str = GROQ_MODEL
) -> str :

    # * Not streamed , unlike the Gemini call : this is the recovery path , nothing is
    # * rendered token by token , and one whole response is simpler to fail on.
    completion = groq_client.chat.completions.create(
        model = model ,
        messages = messages
    )

    return completion.choices[0].message.content or ''

def _parse_json_response(response : str) -> dict :
    '''
    Strips the code fencing the model tends to add , then parses.

    `json.loads` is tried first since the prompt asks for strict JSON , with
    `ast.literal_eval` as the fallback for the single-quoted dicts Gemini sometimes emits.
    '''

    processed_response : str = response.strip()

    # * Strip a ```json ... ``` fence without mangling any backticks in the feedback text
    if processed_response.startswith('```') :

        processed_response = processed_response[3 :]

        if processed_response[: 4].lower() == 'json' : processed_response = processed_response[4 :]
        if processed_response.endswith('```') : processed_response = processed_response[: -3]

        processed_response = processed_response.strip()

    try : return json.loads(processed_response)
    except json.JSONDecodeError : return ast.literal_eval(processed_response)

def _is_quota_error(error : Exception) -> bool :
    '''
    True for a 429 / RESOURCE_EXHAUSTED from Gemini.

    # * Worth singling out because retrying it is not just useless but harmful. The free
    # * tier's cap is `GenerateRequestsPerDayPerProjectPerModel` — twenty requests per
    # * *day* — so a second attempt cannot succeed and spends one more of the twenty.
    # * Google's own `retryDelay : 2s` hint in the payload is about per-minute limits and
    # * is misleading here. On this error we stop asking Gemini and go to Groq at once.
    '''

    status_code = getattr(error , 'code' , None) or getattr(error , 'status_code' , None)

    if status_code == 429 : return True

    message : str = str(error)

    return '429' in message or 'RESOURCE_EXHAUSTED' in message

async def run_json_with_fallback(
    gemini_client : Client ,
    contents : list ,
    generation_config : GenerateContentConfig ,
    model : str = 'gemini-2.5-flash' ,
    groq_client : Any | None = None ,
    groq_model : str = GROQ_MODEL ,
    logger : Logger | None = None
) -> dict :
    '''
    Assess with Gemini , and on failure assess with Groq rather than giving up.

    Returns the parsed JSON dict from whichever provider answered , or `FALLBACK_RESULT`
    if neither did.

    # * Why a second *provider* and not more retries : the failure that actually happens
    # * in production is a daily quota exhaustion , and every retry of that is guaranteed
    # * to fail. Before this , two attempts against the same exhausted key were followed
    # * by FALLBACK_RESULT — which carries `score : 0.0` and is persisted onto the session
    # * like a real assessment , so a billing problem was recorded as a student failing
    # * their consultation.
    '''

    attempts : int = 2

    for attempt in range(1 , attempts + 1) :

        try :

            response : str = await run_gemini(
                gemini_client ,
                contents ,
                generation_config ,
                model
            )

            return _parse_json_response(response)

        except Exception as e :

            if logger : logger.error(
                f'Gemini attempt {attempt}/{attempts} failed : {e} , {traceback.format_exc()}'
            )

            if _is_quota_error(e) :

                if logger : logger.warning(
                    'Gemini quota is exhausted , not retrying it — going straight to Groq.'
                )

                break

    if groq_client is None :

        if logger : logger.error(
            'Gemini failed and no Groq client is configured (set GROQ_API_KEY) , '
            'returning fallback result.'
        )

        return dict(FALLBACK_RESULT)

    try :

        messages : list = _google_to_openai_messages(contents , generation_config)

        groq_response : str = await run_groq(
            groq_client = groq_client ,
            messages = messages ,
            model = groq_model
        )

        result : dict = _parse_json_response(groq_response)

        if logger : logger.info(f'Gemini failed , assessed with Groq ({groq_model}) instead.')

        return result

    except Exception as e :

        if logger : logger.error(
            f'Groq fallback ({groq_model}) also failed : {e} , {traceback.format_exc()}'
        )

    if logger : logger.error('Both Gemini and Groq failed , returning fallback result.')

    return dict(FALLBACK_RESULT)

# * Kept so an older caller keeps working. The name is now a lie about what it does ,
# * hence the wrapper rather than an alias — new code should call run_json_with_fallback.
async def run_json_gemini(
    gemini_client : Client ,
    contents : list ,
    generation_config : GenerateContentConfig ,
    model : str = 'gemini-2.5-flash' ,
    groq_client : Any | None = None ,
    groq_model : str = GROQ_MODEL ,
    logger : Logger | None = None
) -> dict : return await run_json_with_fallback(
    gemini_client = gemini_client ,
    contents = contents ,
    generation_config = generation_config ,
    model = model ,
    groq_client = groq_client ,
    groq_model = groq_model ,
    logger = logger
)

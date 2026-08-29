import ast
import json
import traceback
from logging import Logger
from google.genai import Client
from google.genai.types import GenerateContentConfig

# * Returned when the model cannot be reached or will not produce parseable JSON.
# * Kept as a module constant so callers can identify a fallback by its score / message.
FALLBACK_RESULT : dict = {
    'score' : 0 ,
    'overall_feedback' : 'Sorry we were having some issues generating your feedback. Please try again later.'
}

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

async def run_json_gemini(
    gemini_client : Client ,
    contents : list ,
    generation_config : GenerateContentConfig ,
    model : str = 'gemini-2.5-flash' ,
    logger : Logger | None = None
) -> dict :

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

    if logger : logger.error('Gemini exhausted all attempts , returning fallback result.')

    return dict(FALLBACK_RESULT)

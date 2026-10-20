from google.genai.types import GenerateContentConfig , Part , Content

async def json_to_google_chat(chat : list) -> list :
    '''
    Converts a typical Chat history to Google kind of chat history

    Arguments
    - chat : chat history
    should be like this

    [
        {
            'role' : 'user' ,
            'content' : <user_query>
        } ,
        {
            'role' : 'assistant' ,
            'content' : <assistant_response>
        }
        .continues with user -> assistant
    ]
    '''

    contents = []

    for row in chat :

        role : str = row['role']

        if role == 'user' : contents.append(
            Content(
                role = 'user' ,
                parts = [Part.from_text(text = str(row['content']))]
            )
        )

        else : contents.append(
            Content(
                role = 'model' ,
                parts = [Part.from_text(text = str(row['content']))]
            )
        )

    return contents

async def create_generation_config(system_prompt : str) -> GenerateContentConfig :

    generation_config : GenerateContentConfig = GenerateContentConfig(
        response_mime_type = 'text/plain' ,
        system_instruction = [Part.from_text(text = system_prompt)]
    )

    return generation_config

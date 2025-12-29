from google.genai import Client
from google.genai.types import GenerateContentConfig
from pymongo import MongoClient
from ..services import create_generation_config , json_to_google_chat
from ..llm import run_json_gemini


async def add_scenario_route(
    query : str , 
    mongo_client : MongoClient , 
    gemini_client : Client , 
    config : dict 
) -> dict : 

    with open(config['prompt-path']) as system_prompt_file : 
        system_prompt : str = system_prompt_file.read()

    generation_config : GenerateContentConfig = await create_generation_config(system_prompt)

    messages = [{
        'role' : 'user' , 
        'content' : query
    }]

    contents : list = await json_to_google_chat(messages)

    response : dict = await run_json_gemini(
        gemini_client = gemini_client , 
        contents = contents , 
        generation_config = generation_config , 
        model = config['model']
    )

    try : 

        db = mongo_client[config['database-name']]
        collection = db[config['collection-name']]
        
        api_key = 'rew'
        
        # * Prepare document to insert
        scenario_doc = {
            'scenario_name' : response.get('scenario_name' , '') , 
            'scenario_prompt' : response.get('scenario_prompt' , '') , 
            'questions_for_feedback' : response.get('questions_for_feedback' , []) , 
            'difficulty_status' : response.get('difficulty_status' , '') , 
            'api_key' : api_key
        }
        
        # * Insert the document
        result = collection.insert_one(scenario_doc)
        
        # * Add the inserted ID and API key to response
        response['_id'] = str(result.inserted_id)
        response['api_key'] = api_key
        response['status'] = 'success'
        response['message'] = 'Scenario added successfully'
        
        print(f"✓ Scenario added with ID: {result.inserted_id}")
        
    except Exception as e : 

        print(f"✗ Error adding scenario to database: {e}")
        response['status'] = 'error'
        response['message'] = f'Failed to add scenario: {str(e)}'

    return response

    # * Add flow to db and to the api voxio

async def edit_scenario_route(
    query : str , 
    mongo_client : MongoClient , 
    gemini_client : Client , 
    config : dict , 
    api_key : str
) : 

    with open(config['prompt-path']) as system_prompt_file : 
        system_prompt : str = system_prompt_file.read()

    generation_config : GenerateContentConfig = await create_generation_config(system_prompt)

    messages = [{
        'role' : 'user' , 
        'content' : query
    }]

    contents : list = await json_to_google_chat(messages)

    response : dict = await run_json_gemini(
        gemini_client = gemini_client , 
        contents = contents , 
        generation_config = generation_config , 
        model = config['model']
    )

    try : 

        db = mongo_client[config['database-name']]
        collection = db[config['collection-name']]
        
        # * Find the document by API key
        existing_doc = collection.find_one({'api_key': api_key})
        
        if existing_doc is None : 

            response['status'] = 'error'
            response['message'] = f'No scenario found with api_key: {api_key}'
            print(f"✗ No scenario found with api_key: {api_key}")

            return response
        
        # * Prepare update data (only update fields that are present in response)
        update_data = {}
        
        if 'scenario_name' in response : 
            update_data['scenario_name'] = response['scenario_name']

        if 'scenario_prompt' in response : 
            update_data['scenario_prompt'] = response['scenario_prompt']

        if 'questions_for_feedback' in response : 
            update_data['questions_for_feedback'] = response['questions_for_feedback']

        if 'difficulty_status' in response : 
            update_data['difficulty_status'] = response['difficulty_status']
        
        # * Update the document
        result = collection.update_one(
            {'api_key' : api_key} , 
            {'$set' : update_data}
        )
        
        if result.modified_count > 0 : 
            response['status'] = 'success'
            response['message'] = 'Scenario updated successfully'
            response['modified_count'] = result.modified_count
            print(f"✓ Scenario updated for api_key: {api_key}")

        else:

            response['status'] = 'success'
            response['message'] = 'No changes made (data was identical)'
            response['modified_count'] = 0
        
        response['_id'] = str(existing_doc['_id'])
        response['api_key'] = api_key
        
    except Exception as e : 

        print(f"✗ Error updating scenario in database: {e}")
        response['status'] = 'error'
        response['message'] = f'Failed to update scenario: {str(e)}'

    # * Edit flow to db and to the api voxio

    return response
import ast
from google.genai import Client
from google.genai.types import GenerateContentConfig

async def run_gemini(
    gemini_client : Client , 
    contents : list , 
    generation_config : GenerateContentConfig , 
    model : str = 'gemini-1.5-flash'
) -> str : 

    response = ''

    for chunk in gemini_client.models.generate_content_stream(
        model = model , 
        contents = contents , 
        config = generation_config
    ) : 
        if chunk.text : response += chunk.text
        
    return response

async def run_json_gemini(
    gemini_client : Client ,  
    contents : list , 
    generation_config : GenerateContentConfig , 
    model : str = 'gemini-1.5-flash'
) -> dict : 
    
    try : 

        response : str = await run_gemini(
            gemini_client , 
            contents , 
            generation_config , 
            model
        )
        
        try : 
            
            processed_response : str = response.replace('json' , '').replace('`' , '').strip()

            json_response : dict = ast.literal_eval(processed_response)

            return json_response

        except : 

            rerun_response : str = await run_gemini(
                gemini_client , 
                contents , 
                generation_config , 
                model
            )
            
            print(rerun_response)
            
            try : 
                
                    rerun_processed_response : str = rerun_response.replace('json' , '').replace('`' , '').strip()

                    rerun_json_response : dict = ast.literal_eval(rerun_processed_response)

                    return rerun_json_response

            except : return {
                'scenario_name' : 'Error from Server' , 
                'scenario_prompt' : 'Sorry we were having some issues with the server. Please try again later.' ,
                'question_for_feedback' : [] , 
                'difficulty_level' : 'easy'
            }

    except : return {
        'scenario_name' : 'Error from AI' , 
        'scenario_prompt' : 'Sorry we were having some issues with the AI. Please try again later.' ,
        'question_for_feedback' : [] , 
        'difficulty_level' : 'easy'
    }
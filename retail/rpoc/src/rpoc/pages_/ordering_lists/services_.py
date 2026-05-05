import json
import base64

import polars as pl

from groq import Groq
from typing import Any 
from polars import DataFrame
from datetime import datetime

def process_order_image(
    uploaded_file : Any , 
    client : Groq
) -> dict : 

    base64_image : str = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')

    prompt : str = 'Extract details from this Purchase Order into JSON format. Keys: supplier , purchase_order_date , orders (list of {product_name , quantity , packing_size}).'
    
    time_str : str = datetime.now().strftime('%H%M%S')

    completion : Any = client.chat.completions.create(
        model = 'meta-llama/llama-4-scout-17b-16e-instruct' , 
        messages = [
            {
                'role' : 'user' , 
                'content' : [
                    {
                        'type' : 'text' , 
                        'text' : prompt
                    } , 
                    {
                        'type' : 'image_url' , 
                        'image_url' : {
                            'url' : f'data:image/jpeg;base64,{base64_image}'
                        }
                    }
                ]
            }
        ] , 
        response_format = {
            'type' : 'json_object'
        }
    )

    data : dict = json.loads(completion.choices[0].message.content)

    return {
        'filename' : uploaded_file.name , 
        'name' : f'Order_{time_str}' , 
        'supplier' : data.get('supplier') , 
        'purchase_order_date' : data.get('purchase_order_date') , 
        'orders' : data.get(
            'orders' , 
            []
        ) , 
        'status' : 'pending' , 
        'timestamp' : datetime.now().isoformat()
    }
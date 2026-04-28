import base64
from datetime import datetime
from io import BytesIO
import json 
from groq import Groq
import streamlit as st
import polars as pl
import docx2txt

import json
import polars as pl
import docx2txt
import streamlit as st
from io import BytesIO
from typing import Any

def process_document_with_llm(
    uploaded_file : Any , 
    prompt : str , 
    model_client : Any
) -> list[dict] : 

    file_bytes : bytes = uploaded_file.getvalue()
    mime_type : str = uploaded_file.type

    if 'spreadsheetml.sheet' in mime_type or 'ms-excel' in mime_type : 
        df : pl.DataFrame = pl.read_excel(BytesIO(file_bytes))
        content : list = [f"{prompt}\n\nData:\n{df.write_csv()}"]

    elif 'officedocument.wordprocessingml.document' in mime_type : 
        text : str = docx2txt.process(BytesIO(file_bytes))
        content : list = [f"{prompt}\n\nDocument Text:\n{text}"]

    elif mime_type in [
        'application/pdf' , 
        'image/jpeg' , 
        'image/png' , 
        'image/webp'
    ] : 
        content : list = [
            prompt , 
            {
                'mime_type' : mime_type , 
                'data' : file_bytes
            }
        ]

    elif 'text/plain' in mime_type : 
        content : list = [f"{prompt}\n\n{file_bytes.decode('utf-8')}"]

    else : 
        raise ValueError(f"Unsupported file type: {mime_type}")

    response : Any = model_client.generate_content(
        content , 
        generation_config = {'response_mime_type' : 'application/json'}
    )

    processed_items : list[dict] = []

    try : 

        data : dict = json.loads(response.text)
        supplier : str = data.get(
            'supplier' , 
            'Unknown'
        )
        raw_products : list[dict] = data.get(
            'products' , 
            []
        )

        deduplicated_products : dict = {}

        for prod in raw_products : 
            prod_name : str = prod.get(
                'Product Name' , 
                'Unknown'
            )
            prod_price : float = float(prod.get('Pack Price' , 0.0) or 0.0)
            
            if prod_name in deduplicated_products : 
                existing_price : float = float(deduplicated_products[prod_name].get('Pack Price' , 0.0) or 0.0)
                
                if existing_price == 0.0 and prod_price > 0.0 : 
                    deduplicated_products[prod_name]['Pack Price'] = prod_price
                    
                existing_barcode : str = deduplicated_products[prod_name].get('Barcode' , '')
                new_barcode : str = prod.get('Barcode' , '')
                
                if not existing_barcode and new_barcode : 
                    deduplicated_products[prod_name]['Barcode'] = new_barcode
                    
            else : 
                deduplicated_products[prod_name] = prod

        for product in deduplicated_products.values() : 

            try : 

                pack_price_val : float = product.pop(
                    'Pack Price' , 
                    1.0
                )

                product_dict : dict = {
                    'Barcode' : product.pop(
                        'Barcode' , 
                        ''
                    ) , 
                    'Product Name' : product.pop(
                        'Product Name' , 
                        'Unknown'
                    ) , 
                    'Packing Size' : product.pop(
                        'Packing Size' , 
                        1
                    ) , 
                    'Pack Price' : pack_price_val , 
                    'Previous Price' : pack_price_val , 
                    'Pack Price Currency' : product.pop(
                        'Pack Price Currency' , 
                        'SGD'
                    ) , 
                    'GST' : 0.09 , 
                    'Supplier' : supplier , 
                    'TMG Selling Price' : product.pop(
                        'TMG Selling Price' , 
                        0
                    ) , 
                    'TMG Promotion Price' : product.pop(
                        'TMG Promotion Price' , 
                        0
                    ) , 
                    'Redundant' : json.dumps(
                        product.get(
                            'Redundant' , 
                            []
                        )
                    )
                }

                processed_items.append(product_dict)

            except Exception as e : 
                st.error('')

    except Exception as e : 
        st.error(f"Failed to parse LLM response: {e}")

    return processed_items
def process_order_image(
    uploaded_file , 
    client : Groq
) -> dict : 

    base64_image : str = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')

    prompt = 'Extract details from this Purchase Order into JSON format. Keys: supplier, purchase_order_date, orders (list of {product_name, quantity, packing_size}).'

    completion = client.chat.completions.create(
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
        response_format = {'type' : 'json_object'}
    )

    data = json.loads(completion.choices[0].message.content)

    return {
        'filename' : uploaded_file.name , 
        'name' : f'Order_{datetime.now().strftime('%H%M%S')}' , 
        'supplier' : data.get('supplier') , 
        'purchase_order_date' : data.get('purchase_order_date') , 
        'orders' : data.get('orders' , []) , 
        'status' : 'pending' , 
        'timestamp' : datetime.now().isoformat()
    }
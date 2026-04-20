import base64
from datetime import datetime
from io import BytesIO
import json 
from groq import Groq
import streamlit as st
import polars as pl
import docx2txt

def process_document_with_llm(
    uploaded_file , 
    prompt : str , 
    model_client
) -> list[dict] :

    file_bytes : bytes = uploaded_file.getvalue()
    mime_type : str = uploaded_file.type

    # * --- CATEGORY 1: EXCEL (Needs conversion to Text) ---
    if "spreadsheetml.sheet" in mime_type or "ms-excel" in mime_type:
        df = pl.read_excel(BytesIO(file_bytes))
        content = [f"{prompt}\n\nData:\n{df.write_csv()}"]

    # * --- CATEGORY 2: WORD (Needs conversion to Text) ---
    elif "officedocument.wordprocessingml.document" in mime_type:
        text = docx2txt.process(BytesIO(file_bytes))
        content = [f"{prompt}\n\nDocument Text:\n{text}"]

    # * --- CATEGORY 3: NATIVE SUPPORT (PDF & Images) ---
    elif mime_type in ["application/pdf", "image/jpeg", "image/png", "image/webp"]:
        content = [
            prompt,
            {"mime_type": mime_type, "data": file_bytes}
        ]

    # * --- CATEGORY 4: PLAIN TEXT ---
    elif "text/plain" in mime_type:
        content = [f"{prompt}\n\n{file_bytes.decode('utf-8')}"]

    else:
        raise ValueError(f"Unsupported file type: {mime_type}")

    # Call Gemini
    response = model_client.generate_content(
        content , 
        generation_config = {'response_mime_type' : 'application/json'}
    )

    processed_items : list[dict[str , str | list[dict[str , str | float | int]]]] = []

    try : 

        data = json.loads(response.text)
        supplier = data.get('supplier' , 'Unknown')
        raw_products = data.get('products' , [])

        for product in raw_products : 

            try : 

                product_dict : dict = {
                    'Product Name' : product.pop('Product Name' , 'Unknown') , 
                    'Packing Size' : product.pop('Packing Size' , 1) , 
                    'Pack Price' : product.pop('Pack Price' , 1) , 
                    'Pack Price Currency' : product.pop('Pack Price Currency' , 'SGD') , 
                    'GST' : product.pop('GST' , 0.09) , 
                    'Supplier' : supplier , 
                    'TMG Selling Price' : product.pop('TMG Selling Price' , 0) , 
                    'TMG Promotion Price' : product.pop('TMG Promotion Price' , 0) , 
                    'Redundant' : json.dumps(product.get('Redundant' , []))
                }

                processed_items.append(product_dict)

            except Exception as e : 
                st.error('')

    except Exception as e:
        st.error(f'Failed to parse LLM response: {e}')

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
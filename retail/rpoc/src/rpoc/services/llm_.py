import base64
import json
import re
from datetime import datetime
from io import BytesIO
from typing import Any

from groq import Groq
import streamlit as st
import polars as pl
import docx2txt

def process_document_with_llm(
    uploaded_file : Any , 
    prompt : str , 
    model_client : Any
) -> list[dict] : 

    file_bytes : bytes = uploaded_file.getvalue()
    mime_type : str = uploaded_file.type
    content : list = []

    if 'spreadsheetml.sheet' in mime_type or 'ms-excel' in mime_type : 
        df : pl.DataFrame = pl.read_excel(BytesIO(file_bytes))
        content = [f'{prompt}\n\nData:\n{df.write_csv()}']

    elif 'officedocument.wordprocessingml.document' in mime_type : 
        text : str = docx2txt.process(BytesIO(file_bytes))
        content = [f'{prompt}\n\nDocument Text:\n{text}']

    elif mime_type in [
        'application/pdf' , 
        'image/jpeg' , 
        'image/png' , 
        'image/webp'
    ] : 
        content = [
            prompt , 
            {
                'mime_type' : mime_type , 
                'data' : file_bytes
            }
        ]

    elif 'text/plain' in mime_type : 
        content = [f'{prompt}\n\n{file_bytes.decode("utf-8")}']

    else : 
        raise ValueError(f'Unsupported file type : {mime_type}')

    max_retries : int = 3
    data : dict = {}
    raw_response_text : str = ''

    for attempt in range(max_retries) : 

        try : 

            response : Any = model_client.generate_content(
                content , 
                generation_config = {
                    'response_mime_type' : 'application/json' , 
                    'max_output_tokens' : 81920
                }
            )

            raw_response_text = response.text
            data = json.loads(raw_response_text)
            
            break 

        except Exception as e : 

            st.warning(f'JSON parsing failed on attempt {attempt + 1}/{max_retries} : {e}')
            
            with st.expander('View Raw LLM Output (Dev Mode)') : 
                st.code(
                    raw_response_text , 
                    language = 'json'
                )
            
            if attempt == max_retries - 1 : 
                st.error('Max retries reached. Failed to parse valid JSON from LLM.')
                return []

    processed_items : list[dict] = []

    try : 

        raw_supplier : str = data.get(
            'supplier' , 
            'Unknown'
        )
        raw_products : list[dict] = data.get(
            'products' , 
            []
        )

        supplier : str = re.sub(
            r'[^a-z0-9\(\)\[\] ]' , 
            '' , 
            raw_supplier.lower()
        ).strip()

        deduplicated_products : dict = {}

        for prod in raw_products : 
            original_name : str = prod.get(
                'Product Name' , 
                'Unknown'
            )

            sanitized_name : str = re.sub(
                r'[^a-z0-9\(\)\[\] ]' , 
                '' , 
                original_name.lower()
            ).strip()
            
            prod['Product Name'] = sanitized_name
            
            raw_pack_price : float = float(prod.get('Pack Price' , 0.0) or 0.0)
            purchased_qty : float = float(prod.get('Purchased Quantity' , 1.0) or 1.0)
            free_qty : float = float(prod.get('Free Quantity' , 0.0) or 0.0)
            
            if free_qty > 0.0 : 
                total_cost : float = raw_pack_price * purchased_qty
                total_qty : float = purchased_qty + free_qty
                prod_price : float = total_cost / total_qty
            else : 
                prod_price : float = raw_pack_price
            
            prod['Pack Price'] = prod_price

            if sanitized_name in deduplicated_products : 
                existing_price : float = float(deduplicated_products[sanitized_name].get('Pack Price' , 0.0) or 0.0)
                
                if existing_price == 0.0 and prod_price > 0.0 : 
                    deduplicated_products[sanitized_name]['Pack Price'] = prod_price
                    
                existing_barcode : str = deduplicated_products[sanitized_name].get('Barcode' , '')
                new_barcode : str = prod.get('Barcode' , '')
                
                if not existing_barcode and new_barcode : 
                    deduplicated_products[sanitized_name]['Barcode'] = new_barcode
                    
            else : 
                deduplicated_products[sanitized_name] = prod

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
                    'GST' : product.pop(
                        'GST' , 
                        0.09
                    ) , 
                    'Supplier' : supplier , 
                    'Redundant' : json.dumps(
                        product.get(
                            'Redundant' , 
                            []
                        )
                    )
                }

                processed_items.append(product_dict)

            except Exception as e : 
                st.error(f'Error processing product dictionary : {e}')

    except Exception as e : 
        st.error(f'Failed to map parsed data : {e}')

    return processed_items

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
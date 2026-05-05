import re
import json
import docx2txt

import pandas as pd
import streamlit as st

from io import BytesIO
from typing import Any

def _extract_content_from_file(
    uploaded_file : Any , 
    prompt : str
) -> list[Any] : 

    file_bytes : bytes = uploaded_file.getvalue()
    mime_type : str = uploaded_file.type
    content : list[Any] = []

    if 'spreadsheetml.sheet' in mime_type or 'ms-excel' in mime_type : 

        all_sheets : dict[str , Any] = pd.read_excel(
            BytesIO(file_bytes) , 
            sheet_name = None
        )

        excel_text : str = ''

        for sheet_name , df in all_sheets.items() : 

            clean_df : pd.DataFrame = df.dropna(how = 'all').dropna(
                axis = 1 , 
                how = 'all'
            )

            excel_text += f'--- Sheet : {sheet_name} ---\n'

            excel_text += clean_df.to_csv(
                index = False , 
                sep = '\t'
            ) + '\n\n'

        tabular_prompt : str = f'{prompt}\n\nCRITICAL: The data below is TAB-SEPARATED. Pay strict attention to the column headers. Do NOT confuse the Total Cost column with the Unit Price column.\n\nData:\n{excel_text}'

        content = [tabular_prompt]

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

    return content


def _call_llm_with_retries(
    content : list[Any] , 
    model_client : Any , 
    max_retries : int = 3
) -> dict[str , Any] : 

    data : dict[str , Any] = {}
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

            return data

        except Exception as e : 
            st.warning(f'JSON parsing failed on attempt {attempt + 1}/{max_retries} : {e}')
            
            with st.expander('View Raw LLM Output (Dev Mode)') : 
                st.code(
                    raw_response_text , 
                    language = 'json'
                )

            if attempt == max_retries - 1 : 
                st.error('Max retries reached. Failed to parse valid JSON from LLM.')

    return {}

def _process_and_deduplicate_products(
    data : dict[str , Any]
) -> list[dict[str , Any]] : 

    processed_items : list[dict[str , Any]] = []

    raw_supplier : str = data.get('supplier' , 'Unknown')
    raw_products : list[dict[str , Any]] = data.get('products' , [])

    supplier : str = re.sub(
        r'[^a-z0-9\(\)\[\] ]' , 
        '' , 
        raw_supplier.lower()
    ).strip()

    deduplicated_products : dict[str , dict[str , Any]] = {}

    for prod in raw_products : 

        original_name : str = prod.get('Product Name' , 'Unknown')

        sanitized_name : str = re.sub(
            r'[^a-z0-9\(\)\[\] ]' , 
            '' , 
            original_name.lower()
        ).strip()

        prod['Product Name'] = sanitized_name

        raw_pack_price : float = float(prod.get('Pack Price' , 0.0) or 0.0)

        prod['Pack Price'] = raw_pack_price

        if sanitized_name in deduplicated_products : 

            existing_price : float = float(deduplicated_products[sanitized_name].get('Pack Price' , 0.0) or 0.0)

            if existing_price == 0.0 and raw_pack_price > 0.0 : 
                deduplicated_products[sanitized_name]['Pack Price'] = raw_pack_price

            existing_barcode : str = deduplicated_products[sanitized_name].get('Barcode' , '')

            new_barcode : str = prod.get('Barcode' , '')

            if not existing_barcode and new_barcode : 
                deduplicated_products[sanitized_name]['Barcode'] = new_barcode

        else : 
            deduplicated_products[sanitized_name] = prod

    for product in deduplicated_products.values() : 

        try : 

            pack_price_val : float = float(product.pop('Pack Price' , 0.0) or 0.0)
            selling_price_val : float = float(product.pop('Selling Price' , 0.0) or 0.0)
            promotion_price_val : float = float(product.pop('Promotion Price' , 0.0) or 0.0)

            product_dict : dict[str , Any] = {
                'Barcode' : product.pop('Barcode' , '') , 
                'Product Name' : product.pop('Product Name' , 'Unknown') , 
                'Packing Size' : int(product.pop('Packing Size' , 1) or 1) , 
                'Pack Price' : pack_price_val , 
                'Selling Price' : selling_price_val , 
                'Promotion Price' : promotion_price_val , 
                'Supplier' : supplier , 
                'Redundant' : json.dumps(product.get('Redundant' , []))
            }

            processed_items.append(product_dict)

        except Exception as inner_e : 
            st.error(f'Error processing product dictionary : {inner_e}')

    return processed_items

def process_document_with_llm(
    uploaded_file : Any , 
    prompt : str , 
    model_client : Any
) -> list[dict[str , Any]] : 

    try : 

        content : list[Any] = _extract_content_from_file(
            uploaded_file , 
            prompt
        )

        parsed_data : dict[str , Any] = _call_llm_with_retries(
            content , 
            model_client
        )

        if not parsed_data : 
            return []

        processed_items : list[dict[str , Any]] = _process_and_deduplicate_products(parsed_data)

        return processed_items

    except Exception as e : 

        st.error(f'Document processing pipeline failed : {e}')

        return []
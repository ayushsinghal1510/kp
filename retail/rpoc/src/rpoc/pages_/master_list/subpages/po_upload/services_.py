import re
import json
import docx2txt

import pandas as pd
import streamlit as st

from io import BytesIO
from typing import Any

from google.genai import types

from rpoc.services.packing_ import parse_packing_size


def _extract_content_from_file(
    uploaded_file : Any , 
    prompt : str
) -> list[Any] : 

    file_name : str = uploaded_file.name.lower()

    valid_extensions : tuple[str , ...] = (
        '.doc' , 
        '.docx' , 
        '.xls' , 
        '.xlsx' , 
        '.png' , 
        '.jpeg' , 
        '.jpg' , 
        '.txt' , 
        '.pdf'
    )

    if not file_name.endswith(valid_extensions) : 
        raise ValueError(f'Unsupported file extension : {file_name}')

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

            clean_df : pd.DataFrame = df.dropna(
                how = 'all'
            ).dropna(
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

    elif 'wordprocessingml.document' in mime_type or 'msword' in mime_type : 
        
        try : 
            text : str = docx2txt.process(BytesIO(file_bytes))
        except Exception : 
            text = file_bytes.decode(
                'utf-8' , 
                errors = 'ignore'
            )

        content = [f'{prompt}\n\nDocument Text:\n{text}']

    elif mime_type in [
        'application/pdf' , 
        'image/jpeg' , 
        'image/png'
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

    formatted_parts : list[Any] = []

    for item in content : 

        if isinstance(
            item , 
            str
        ) : 

            formatted_parts.append(
                types.Part.from_text(
                    text = item
                )
            )

        elif isinstance(
            item , 
            dict
        ) : 

            formatted_parts.append(
                types.Part.from_bytes(
                    data = item.get('data' , b'') , 
                    mime_type = item.get('mime_type' , '')
                )
            )

    formatted_contents : list[Any] = [
        types.Content(
            role = 'user' , 
            parts = formatted_parts
        )
    ]

    for attempt in range(max_retries) : 

        try : 

            tools : list[Any] = [
                types.Tool(
                    googleSearch = types.GoogleSearch()
                )
            ]

            generation_config : Any = types.GenerateContentConfig(
                tools = tools
            )

            response : Any = model_client.models.generate_content(
                model = 'gemini-3.1-flash-lite' , 
                contents = formatted_contents , 
                config = generation_config
            )

            raw_response_text = response.text

            cleaned_text : str = re.sub(
                r'^```json\s*|```\s*$' , 
                '' , 
                raw_response_text.strip() , 
                flags = re.MULTILINE | re.IGNORECASE
            )

            data = json.loads(cleaned_text)

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

    raw_supplier : str = data.get(
        'supplier' , 
        'Unknown'
    )
    
    exchange_rate : float = float(
        data.get('exchange_rate' , 1.0) or 1.0
    )
    
    raw_products : list[dict[str , Any]] = data.get(
        'products' , 
        []
    )

    # Collapses multiple spaces/newlines, but keeps asterisks and original text
    supplier_display : str = re.sub(
        r'\s+' , 
        ' ' , 
        raw_supplier
    ).strip()
    
    supplier_search_key : str = supplier_display.lower()

    deduplicated_products : dict[str , dict[str , Any]] = {}

    for prod in raw_products : 

        raw_product_name : str | None = prod.get('Product Name')
        raw_product_description : str | None = prod.get('Product Description')

        original_name : str = raw_product_name or raw_product_description or 'Unknown'

        # Only standardizes white-spaces while safely safeguarding special characters
        sanitized_name_display : str = re.sub(
            r'\s+' , 
            ' ' , 
            original_name
        ).strip()
        
        sanitized_search_key : str = sanitized_name_display.lower()

        prod['Product Name'] = sanitized_name_display

        raw_pack_price : float = float(prod.get('Pack Price' , 0.0) or 0.0)

        prod['Pack Price'] = raw_pack_price

        if sanitized_search_key in deduplicated_products : 

            existing_price : float = float(
                deduplicated_products[sanitized_search_key].get('Pack Price' , 0.0) or 0.0
            )

            if existing_price == 0.0 and raw_pack_price > 0.0 : 
                deduplicated_products[sanitized_search_key]['Pack Price'] = raw_pack_price

            existing_barcode : str = deduplicated_products[sanitized_search_key].get(
                'Barcode' , 
                ''
            )

            new_barcode : str = prod.get(
                'Barcode' , 
                ''
            )

            if not existing_barcode and new_barcode : 
                deduplicated_products[sanitized_search_key]['Barcode'] = new_barcode

        else : 
            deduplicated_products[sanitized_search_key] = prod

    for product in deduplicated_products.values() : 

        try : 

            pack_price_val : float = float(product.pop('Pack Price' , 0.0) or 0.0)

            if exchange_rate > 0.0 and exchange_rate != 1.0 : 
                pack_price_val = pack_price_val / exchange_rate

            selling_price_val : float = float(product.pop('Selling Price' , 0.0) or 0.0)
            promotion_price_val : float = float(product.pop('Promotion Price' , 0.0) or 0.0)

            # The model emits a canonical packing-size STRING; the number is
            # computed deterministically here, never by the model.
            packing_string : str = str(
                product.get('Packing Size String' , '') or ''
            ).strip()

            # Backward-compat: fall back to a bare number if that is all we got.
            if not packing_string :
                packing_string = str(product.get('Packing Size' , '') or '').strip()

            packing_size , packing_calc = parse_packing_size(packing_string)

            product_dict : dict[str , Any] = {
                'Barcode' : product.pop('Barcode' , '') ,
                'Product Name' : product.pop('Product Name' , 'Unknown') ,
                'Packing Size String' : packing_string ,
                'Packing Size' : packing_size ,
                'Packing Calc' : packing_calc ,
                'Pack Price' : pack_price_val ,
                'Selling Price' : selling_price_val ,
                'Promotion Price' : promotion_price_val ,
                'Supplier' : supplier_display ,
                'Redundant' : json.dumps(
                    product.get('Redundant' , [])
                )
            }

            processed_items.append(product_dict)

        except Exception as inner_e : 
            st.error(f'Error processing product dictionary : {inner_e}')

    st.write(f'Products added with exchange rate : {exchange_rate}')
    
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

        processed_items : list[dict[str , Any]] = _process_and_deduplicate_products(
            parsed_data
        )

        return processed_items

    except Exception as e : 

        st.error(f'Document processing pipeline failed : {e}')

        return []
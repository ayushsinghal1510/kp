import json
import pandas as pd
import polars as pl
import streamlit as st

from typing import Any
from pandas import DataFrame

def extract_supplier_name(
    raw_df : DataFrame , 
) -> str : 

    try : 

        supplier_cell : str = str(raw_df.iloc[2 , 1])

        if supplier_cell.lower() == 'nan' : 
            supplier_cell = str(raw_df.iloc[3 , 1])

        raw_supplier : str = supplier_cell.split(
            ':' , 
            1
        )[1].strip() if ':' in supplier_cell else supplier_cell.strip()

        return raw_supplier if raw_supplier and raw_supplier.lower() != 'nan' else 'unknown'

    except Exception : 
        return 'unknown'


def extract_exchange_rate(
    raw_df : DataFrame , 
) -> float : 

    try : 

        if raw_df.shape[0] > 1 and raw_df.shape[1] > 16 : 
            
            cell : Any = raw_df.iloc[1 , 16]
            
            if pd.notna(cell) and str(cell).strip() : 
                
                return float(cell)

    except Exception : 
        pass

    return 1.0


def process_excel_with_llm(
    uploaded_file : Any , 
) -> pl.DataFrame : 

    raw_sheets : dict[str , pd.DataFrame] = pd.read_excel(
        uploaded_file , 
        header = None , 
        sheet_name = None
    )

    price_sheets : dict[str , pd.DataFrame] = pd.read_excel(
        uploaded_file , 
        header = 5 , 
        sheet_name = None
    )

    all_extracted_items : list[dict[str , Any]] = []

    for sheet_name , raw_df in raw_sheets.items() : 

        supplier_name : str = extract_supplier_name(
            raw_df
        )
        
        exchange_rate : float = extract_exchange_rate(
            raw_df
        )

        price_data : pd.DataFrame = price_sheets[sheet_name]

        unnamed_cols : list[str] = [
            c for c in price_data.columns
            if 'Unnamed' in str(c)
        ]

        price_data.drop(
            columns = unnamed_cols , 
            inplace = True , 
            errors = 'ignore'
        )

        price_data.dropna(
            how = 'all' , 
            inplace = True
        )

        csv_string : str = price_data.to_csv(
            index = False
        )

        system_instruction : str = '''
            You are an expert data extraction agent.
            Process the given CSV data into a JSON array of objects. 
            Strictly use these exact keys:
            - "Product Name" : string (exact name from the data)
            - "Packing Size" : integer (get from data, or infer from product name, else 1)
            - "Pack Price" : float (if not present, calculate it using Unit Price * Packing Size, or Total Cost / Qty)
            - "Selling Price" : float (if not present, default to 0.0)
            - "Promotion Price" : float (if not present, default to 0.0)

            Respond ONLY with a valid JSON object containing a single key "items" mapped to the array of dictionaries.
        '''

        response : Any = st.session_state.groq_client.chat.completions.create(
            model = 'llama-3.3-70b-versatile' , 
            messages = [
                {
                    'role' : 'system' , 
                    'content' : system_instruction
                } , 
                {
                    'role' : 'user' , 
                    'content' : f'Extract from this CSV:\n{csv_string}'
                }
            ] , 
            response_format = {
                'type' : 'json_object'
            } , 
            temperature = 0.0
        )

        response_content : str = response.choices[0].message.content

        try : 

            parsed_output : dict[str , Any] = json.loads(response_content)
            
            items : list[dict[str , Any]] = parsed_output.get(
                'items' , 
                []
            )

            for item in items : 

                item['Supplier'] = supplier_name
                item['Pack Price Currency'] = 'SGD'
                
                raw_pack_price : float = float(item.get('Pack Price' , 0.0) or 0.0)
                
                if exchange_rate > 0.0 and exchange_rate != 1.0 : 
                    raw_pack_price = raw_pack_price / exchange_rate
                    
                item['Pack Price'] = raw_pack_price

                all_extracted_items.append(item)

        except Exception as error : 
            st.error(f'Error parsing LLM response for sheet {sheet_name} : {error}')

    if all_extracted_items : 
        return pl.DataFrame(all_extracted_items)

    return pl.DataFrame()


def _get_promo_price_expr() -> pl.Expr : 

    is_null_expr : pl.Expr = pl.col('Promotion Price').is_null()
    is_zero_expr : pl.Expr = pl.col('Promotion Price') == 0.0
    is_nan_expr : pl.Expr = pl.col('Promotion Price').cast(pl.String).str.to_lowercase() == 'nan'

    return pl.when(
        is_null_expr | is_zero_expr | is_nan_expr
    ).then(
        pl.col('Selling Price')
    ).otherwise(
        pl.col('Promotion Price')
    ).alias('Promotion Price')
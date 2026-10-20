import re
import json
import math

import pandas as pd
import polars as pl
import streamlit as st

from re import Match
from typing import Any
from pandas import DataFrame
from google.genai import types

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

        if raw_df.shape[0] > 1 :

            for col_idx in range(raw_df.shape[1]) :

                cell_val : Any = raw_df.iloc[1 , col_idx]

                if pd.isna(cell_val) :
                    continue

                cell_str : str = str(cell_val).strip().lower()

                if 'rate' in cell_str :

                    match : Match | None = re.search(
                        r'rate.*?(\d+\.\d+|\d+)' ,
                        cell_str
                    )

                    if match :

                        try :
                            return float(match.group(1))
                        except ValueError :
                            pass

                    if col_idx + 1 < raw_df.shape[1] :

                        next_cell : Any = raw_df.iloc[1 , col_idx + 1]

                        if pd.notna(next_cell) :

                            try :
                                return float(str(next_cell).strip())
                            except ValueError :
                                pass

    except Exception :
        pass

    return 1.0


def _parse_number(value : Any) -> float :

    if value is None :
        return 0.0

    if isinstance(value , float) and math.isnan(value) :
        return 0.0

    match : Match | None = re.search(
        r'(\d+(?:\.\d+)?)' ,
        str(value).replace(',' , '')
    )

    return float(match.group(1)) if match else 0.0


def _identify_columns_with_llm(
    sample_csv : str ,
) -> dict[str , str | None] :

    standard_fields : list[str] = [
        'Product Name' ,
        'Packing Size' ,
        'Pack Price' ,
        'Unit Price' ,
        'Selling Price' ,
        'Promotion Price'
    ]

    system_instruction : str = '''
        You are a column-mapping agent for supplier price sheets.
        You are given the first rows of a sheet as CSV (the first line is the header).
        Identify which header maps to each standard field listed below.

        Standard fields :
        - "Product Name"    : the product / item description column
        - "Packing Size"    : carton / pack quantity column (integer)
        - "Pack Price"      : the carton / pack price column (if present)
        - "Unit Price"      : the per-unit price column (if present)
        - "Selling Price"   : the selling price column (if present)
        - "Promotion Price" : the promotion price column (if present)

        Respond ONLY with a JSON object mapping each standard field to the EXACT
        header string copied verbatim from the data, or null if that field has no
        matching column. Do not include markdown formatting or explanations.
    '''

    formatted_contents : list[Any] = [
        types.Content(
            role = 'user' ,
            parts = [
                types.Part.from_text(
                    text = system_instruction
                ) ,
                types.Part.from_text(
                    text = f'Identify the columns from this CSV sample :\n{sample_csv}'
                )
            ]
        )
    ]

    column_map : dict[str , str | None] = {
        field : None for field in standard_fields
    }

    try :

        response : Any = st.session_state.gemini_client.models.generate_content(
            model = 'gemini-2.5-flash' ,
            contents = formatted_contents ,
            config = types.GenerateContentConfig()
        )

        cleaned_text : str = re.sub(
            r'^```json\s*|```\s*$' ,
            '' ,
            response.text.strip() ,
            flags = re.MULTILINE | re.IGNORECASE
        )

        parsed_map : dict[str , Any] = json.loads(cleaned_text)

        for field in standard_fields :

            value : Any = parsed_map.get(field)

            column_map[field] = str(value) if value else None

    except Exception as error :

        st.error(f'Error identifying columns : {error}')

    return column_map


def _parse_excel_columns(
    price_data : pd.DataFrame ,
    column_map : dict[str , str | None] ,
    supplier_name : str ,
    exchange_rate : float
) -> list[dict[str , Any]] :

    name_col : str | None = column_map.get('Product Name')

    if name_col is None or name_col not in price_data.columns :
        return []

    packing_col : str | None = column_map.get('Packing Size')
    pack_price_col : str | None = column_map.get('Pack Price')
    unit_price_col : str | None = column_map.get('Unit Price')
    selling_col : str | None = column_map.get('Selling Price')
    promo_col : str | None = column_map.get('Promotion Price')

    has_packing : bool = bool(packing_col) and packing_col in price_data.columns
    has_pack_price : bool = bool(pack_price_col) and pack_price_col in price_data.columns
    has_unit_price : bool = bool(unit_price_col) and unit_price_col in price_data.columns
    has_selling : bool = bool(selling_col) and selling_col in price_data.columns
    has_promo : bool = bool(promo_col) and promo_col in price_data.columns

    extracted_items : list[dict[str , Any]] = []

    for _ , row in price_data.iterrows() :

        product_name : str = str(row[name_col]).strip()

        if not product_name or product_name.lower() == 'nan' :
            continue

        packing_size : int = int(
            _parse_number(row[packing_col])
        ) if has_packing else 0

        if packing_size <= 0 :
            packing_size = 1

        # * Excel is the source of truth for Product Name + Packing Size ONLY.
        # * All pricing (Pack Price / FOC / exchange rate) comes from the invoice,
        # * so prices are deliberately left at 0 here and NEVER imported from Excel.
        extracted_items.append(
            {
                'Product Name' : product_name ,
                'Packing Size' : packing_size ,
                'Pack Price' : 0.0 ,
                'Selling Price' : 0.0 ,
                'Promotion Price' : 0.0 ,
                'Supplier' : supplier_name ,
                'Pack Price Currency' : 'SGD'
            }
        )

    return extracted_items


def process_excel_with_llm(
    uploaded_file : Any ,
) -> tuple[pl.DataFrame , float] :

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

    exchange_rate : float = 1.0

    for sheet_name , raw_df in raw_sheets.items() :

        supplier_name : str = extract_supplier_name(
            raw_df
        )

        exchange_rate = extract_exchange_rate(
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

        # * Send only the starting 10 rows so the LLM identifies the exact column
        # * names; the full sheet is then parsed manually from that mapping.
        sample_csv : str = price_data.head(10).to_csv(
            index = False
        )

        column_map : dict[str , str | None] = _identify_columns_with_llm(
            sample_csv
        )

        extracted_items : list[dict[str , Any]] = _parse_excel_columns(
            price_data ,
            column_map ,
            supplier_name ,
            exchange_rate
        )

        all_extracted_items.extend(extracted_items)

    if all_extracted_items :
        return pl.DataFrame(all_extracted_items) , exchange_rate

    return pl.DataFrame() , exchange_rate

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

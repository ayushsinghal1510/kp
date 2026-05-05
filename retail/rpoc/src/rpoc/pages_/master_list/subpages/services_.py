import re
import math
import polars as pl

from re import Match
from typing import Any

def safe_extract_price(val : Any) -> float | None : 

    if val is None : 
        return None

    if isinstance(val , float) and math.isnan(val) : 
        return None

    if isinstance(val , (int , float)) : 
        return float(val)

    val_str : str = str(val).strip()

    price_match : Match | None = re.search(
        r'\$\s*(\d+\.\d+|\d+)' , 
        val_str
    )

    if price_match : 
        return float(price_match.group(1))

    try : 
        return float(val_str)

    except ValueError : 
        return None

def sanitize_dataframe_for_polars(
    df : pl.DataFrame , 
    root_cols : list[str]
) -> pl.DataFrame : 

    missing_cols : list[pl.Expr] = [
        pl.lit(None).alias(col) 
        for col in root_cols 
        if col not in df.columns
    ]

    if missing_cols : 
        df = df.with_columns(missing_cols)

    string_columns : list[str] = [
        'Barcode' , 
        'Product Name' , 
        'Pack Price Currency' , 
        'Supplier' , 
        'Other' , 
        'Filename' , 
        'Redundant' , 
        'Previous'
    ]

    numeric_columns : list[str] = [
        'Packing Size' , 
        'Previous Price' , 
        'Pack Price' , 
        'Selling Price' , 
        'Promotion Price'
    ]

    str_exprs : list[pl.Expr] = []

    for col in string_columns : 

        if col in df.columns : 

            expr = pl.when(
                pl.col(col).cast(pl.String) == 'nan'
            ).then(
                None
            ).otherwise(
                pl.col(col).cast(pl.String)
            ).alias(col)

            str_exprs.append(expr)

    if str_exprs : 
        df = df.with_columns(str_exprs)

    num_exprs : list[pl.Expr] = []

    for col in numeric_columns : 

        if col in df.columns : 

            expr : pl.Expr = pl.col(col).map_elements(
                safe_extract_price , 
                return_dtype = pl.Float64
            ).alias(col)

            num_exprs.append(expr)

    if num_exprs : 
        df = df.with_columns(num_exprs)

    return df.select(root_cols)

def normalize_string(
    text : Any
) -> str | None : 

    if text is None : 
        return None

    if isinstance(
        text , 
        float
    ) and math.isnan(text) : 
        return None

    val_str : str = str(text)
    
    if val_str.lower() == 'nan' or not val_str.strip() : 
        return None

    normalized : str = re.sub(
        r'[^a-z0-9\(\)\[\] ]' , 
        '' , 
        val_str.lower()
    ).strip()

    return normalized if normalized else None

import os

from pathlib import Path
from typing import Any

def save_uploaded_file(
    uploaded_file : Any , 
    target_folder : str = 'assets/files'
) -> None : 

    folder_path : Path = Path(target_folder)
    
    folder_path.mkdir(
        parents = True , 
        exist_ok = True
    )
    
    file_path : Path = folder_path / uploaded_file.name
    
    with open(
        file_path , 
        'wb'
    ) as f : 
        f.write(uploaded_file.getbuffer())

    print(f'Saved to {file_path}')
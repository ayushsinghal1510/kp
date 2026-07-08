import re
import json
import datetime

import pandas as pd 
import numpy as np

from polars import DataFrame
import polars as pl

def _convert_types(obj) : 

    if isinstance(
        obj , 
        (
            np.int64 , np.int32 , 
            np.float64 , np.float32
        )
    ) : 
        return obj.item()

    if isinstance(obj , (datetime , pd.Timestamp)) : 
        return obj.isoformat()

    return obj


def load_json(path : str) -> dict | list : 

    with open(path) as file : 
        return json.load(file)

def save_json(path : str , data : dict | list) -> None : 

    with open(path, 'w') as json_file : 
        json.dump(
            data , 
            json_file , 
            indent = 4 , 
            default = _convert_types
        )

def safe_num(value , default = 0) : 

    if value is None : 
        return default

    try : 
        f = float(value)

        if np.isnan(f) or np.isinf(f) : 
            return default

        return f

    except (TypeError , ValueError) : 
        return default

def safe_str(value , default = '') : 

    if value is None : 
        return default

    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)) : 
        return default

    return str(value)


def get_packing_size(product_name : str , master_df : DataFrame) : 

    if (
        master_df.is_empty() or 
        'Product Name' not in master_df.columns
    ) : 
        return 0.0

    col = 'Packing Size'

    match = master_df.filter(
        pl.col('Product Name').str.strip_chars().str.to_lowercase() == product_name.strip().lower()
    )

    if not match.is_empty() and col in match.columns : 

        try : 

            val = match.item(0 , col)

            return float(val) if val is not None else 0.0

        except Exception : 
            return 0.0

    return 0.0

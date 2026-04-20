import datetime
import json
import sys
import os

import polars as pl
import pandas as pd 
import numpy as np
from polars import DataFrame
import streamlit as st 

import polars as pl

from groq import Groq
import yaml

import google.generativeai as genai

from io import StringIO


import polars as pl
from io import StringIO
import sys

def execute_code(code_str : str) -> tuple[bool , str | None , str | None] : 

    output : StringIO = StringIO()
    sys.stdout = output

    context = {
        'pl' : pl , 
        'pd' : pd , 
        'np' : np , 
        'st' : st , 
        'df' : st.session_state.df 
    }

    try : 

        exec(code_str , context , context)

        st.session_state.df = context['df']

        st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])

        return True , output.getvalue() , None

    except Exception as e : 
        return False , None , str(e)

    finally : 
        sys.stdout = sys.__stdout__

def convert_types(obj) : 

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

def save_json(path : str , data : dict | list) -> None : 

    with open(path, 'w') as json_file : 
        json.dump(
            data , 
            json_file , 
            indent = 4 , 
            default = convert_types
        )

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

def calculate_purchase_metrics(
    product_name : str , 
    qty_ctn : int , 
    packing_size : int , 
    ctn_price : float , 
    gst_rate : float 
) -> dict : 

    # * Everything gets changed to sgd

    qty_ctn = float(qty_ctn)
    packing_size = float(packing_size)
    ctn_price = float(ctn_price)

    total_qty = qty_ctn * packing_size
    unit_p_raw = ctn_price / packing_size if packing_size > 0 else 0
    total_raw = qty_ctn * ctn_price
    
    # Logic for 9% or 9.16% columns
    # gst_mult = 1 + (gst_rate / 100)

    # Default markup for profit calculations
    # markup = 0.25 
    # sell_p_pc = unit_p_raw * (1 + markup)
    # total_sell = sell_p_pc * total_qty
    # total_profit = total_sell - (total_raw * gst_mult)

    try:
        gst_rate = float(gst_rate)
    except (ValueError, TypeError):
        gst_rate = 0.0

    gst_mult = 1 + gst_rate

    return {
        "Product Name" : product_name , 
        "Qty" : qty_ctn , 
        "Packing Size" : packing_size , 
        "Total Ordered Qty" : total_qty , 
        "Ctn Price WOGST" : round(ctn_price , 2) , 
        "Unit Price WOGST" : round(unit_p_raw , 4) , 
        "Total WOGST" : round(total_raw , 2) , 
        'GST' : gst_rate * 100 , 
        "Ctn Price WGST": round(ctn_price * gst_mult, 2),  
        "Unit Cost WGST": round(unit_p_raw * gst_mult, 4), 
        "Total Cost WGST": round(total_raw * gst_mult, 2)
        # "TMG Selling Price per piece": round(sell_p_pc, 4),
        # "TMG Promotion Price": round(sell_p_pc, 4),
        # "Total Selling": round(total_sell, 2),
        # "UNIT PROFIT ($)": round(sell_p_pc - (unit_p_raw * gst_mult), 4),
        # "TOTAL PROFIT ($)": round(total_profit, 2),
        # "Profit Margin - %": round((total_profit / total_sell) * 100, 2) if total_sell > 0 else 0
    }

def load_json(path : str) -> dict | list : 

    with open(path) as file : 
        return json.load(file)

def get_next_po_number(po_file_path) -> str : 

    counter_data = load_json(po_file_path)

    if (
        not counter_data or 
        not isinstance(counter_data , dict)
    ) : 
        counter_data = {"counter" : 0}

    counter_data["counter"] += 1

    save_json(po_file_path , counter_data)

    return f"PO-{counter_data['counter']:05d}"


def consolidate_selected_orders(
    selected_indices , 
    ordering_lists , 
    master_df
) : 
    
    # 1. Safely cast columns to floats and handle missing values
    master_df = master_df.with_columns(
        [
            pl.col('Product Name').str.to_lowercase().str.strip_chars().alias('s_name') , 
            pl.col('Pack Price').cast(pl.Float64, strict=False).fill_null(0.0) ,
            pl.col('Packing Size').cast(pl.Float64, strict=False).fill_null(1.0)
        ]
    )

    # 2. Prevent division by zero just in case someone entered a 0 for packing size
    master_df = master_df.with_columns(
        pl.when(pl.col('Packing Size') == 0).then(1.0).otherwise(pl.col('Packing Size')).alias('Packing Size')
    )

    # 3. Now perform the division safely
    master_df = master_df.with_columns(
        pl.col('Pack Price').alias('Ctn Price')
    )

    invoices = {}

    for idx in selected_indices : 

        for item in ordering_lists[idx]['orders'] : 

            product_name = str(item['product_name']).strip()
            quantity = float(item.get('quantity' , 0) or 0)
            packing_size = float(item.get('packing_size' , 0) or 0)

            match = master_df.filter(
                pl.col('s_name') == product_name.lower()
            )

            if match.height > 0 : 

                best = match.sort('Ctn Price').row(0 , named = True)

                supplier = best['Supplier']
                price = float(best['Ctn Price'])
                
                if supplier not in invoices : 
                    invoices[supplier] = {}

                if product_name not in invoices[supplier] : 
                    invoices[supplier][product_name] = {
                        "quantity" : quantity , 
                        "packing_size" : packing_size , 
                        "price" : price , 
                        'gst' : best['GST']
                    }

                else:
                    invoices[supplier][product_name]["quantity"] += quantity

    return invoices

def safe_num(v, default=0):
    """Return a safe numeric value for xlsxwriter — no NaN or inf."""
    if v is None:
        return default
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default

def safe_str(v, default=''):
    """Return a safe string, converting NaN/None to empty string."""
    if v is None:
        return default
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return default
    return str(v)

def _get_gst_info(df_items):
    """Return (rate_float, col_key_in_items, label_str) for the active GST column."""
    c916 = 'Unit Cost (9.16%) (SGD - PC)'
    if c916 in df_items.columns and (df_items[c916].fillna(0) != 0).any():
        return 9.16, c916, '9.16%'
    return 9.0, 'Unit Cost (9%) (SGD - PC)', '9%'

def load_session_state() : 

    if 'groq_client' not in st.session_state : 
        st.session_state.groq_client = Groq(api_key = os.environ['GROQ_API_KEY'])

    if 'gemini_client' not in st.session_state : 
        st.session_state.gemini_client = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

    if 'config' not in st.session_state : 

        with open('config.yml') as config_file : 
            st.session_state.config = yaml.safe_load(config_file)

    if 'master_list_config' not in st.session_state : 
        st.session_state.master_list_config = st.session_state.config['master-list']

    if 'chatbot_config' not in st.session_state : 
        st.session_state.chatbot_config = st.session_state.config['chatbot']

    if 'ordering_lists_config' not in st.session_state : 
        st.session_state.ordering_lists_config = st.session_state.config['ordering-lists']


    if 'prompts' not in st.session_state : 
        st.session_state.prompts = {}

        with open(st.session_state.config['main']['prompts']['review']) as prompt_file : 
            st.session_state.prompts['review'] = prompt_file.read()

        with open(st.session_state.config['main']['prompts']['ingestion']) as prompt_file : 
            st.session_state.prompts['ingestion'] = prompt_file.read()

        with open(st.session_state.config['main']['prompts']['coder']) as prompt_file : 
            st.session_state.prompts['coder'] = prompt_file.read()

        with open(st.session_state.config['main']['prompts']['chain-rules']) as prompt_file : 
            st.session_state.prompts['chain-rules'] = prompt_file.read()

    if 'df' not in st.session_state : 
        st.session_state.df = pl.read_csv(st.session_state.config['main']['path']['csv'])

    if 'history' not in st.session_state : 
        st.session_state.history = []

    if 'ordering_lists' not in st.session_state : 
        st.session_state.ordering_lists = load_json(st.session_state.config['main']['path']['ordering-lists'])

    if 'purchases' not in st.session_state : 
        st.session_state.purchases = load_json(st.session_state.config['main']['path']['purchases'])


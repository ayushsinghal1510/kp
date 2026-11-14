import os
import yaml

import polars as pl
import streamlit as st

from groq import Groq

from .services_ import load_json

from google import genai
from openai import OpenAI



def load_session_state() : 

    if 'groq_client' not in st.session_state : 
        st.session_state.groq_client = Groq(api_key = os.environ['GROQ_API_KEY'])

    if 'gemini_client' not in st.session_state : 
        st.session_state.gemini_client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    if 'openrouter_client' not in st.session_state :
        st.session_state.openrouter_client = OpenAI(
            base_url = 'https://openrouter.ai/api/v1' ,
            api_key = os.environ['OPENROUTER_API_KEY']
        )

    if 'config' not in st.session_state : 

        with open('config.yml' , encoding = 'utf-8') as config_file :
            st.session_state.config = yaml.safe_load(config_file)

    if 'master_list_config' not in st.session_state : 
        st.session_state.master_list_config = st.session_state.config['master-list']

    if 'chatbot_config' not in st.session_state : 
        st.session_state.chatbot_config = st.session_state.config['chatbot']

    if 'ordering_lists_config' not in st.session_state : 
        st.session_state.ordering_lists_config = st.session_state.config['ordering-lists']


    required_prompts : list[str] = [
        'review' ,
        'ingestion' ,
        'coder' ,
        'chain-rules'
    ]

    # * Reload if missing , only partially populated (e.g. a previous run crashed
    # * midway) , or any prompt file was edited since it was loaded — so prompt
    # * changes apply without restarting the app. Build into a local dict and
    # * assign atomically so a failure never leaves a half-filled prompts dict.
    prompt_mtimes : dict[str , float] = {
        key : os.path.getmtime(st.session_state.config['main']['prompts'][key])
        for key in required_prompts
    }

    if (
        'prompts' not in st.session_state or
        any(key not in st.session_state.prompts for key in required_prompts) or
        st.session_state.get('prompt_mtimes') != prompt_mtimes
    ) :

        loaded_prompts : dict[str , str] = {}

        for key in required_prompts :

            with open(st.session_state.config['main']['prompts'][key] , encoding = 'utf-8') as prompt_file :
                loaded_prompts[key] = prompt_file.read()

        st.session_state.prompts = loaded_prompts
        st.session_state.prompt_mtimes = prompt_mtimes

    if 'df' not in st.session_state : 
        st.session_state.df = pl.read_csv(st.session_state.config['main']['path']['csv'])

    if 'history' not in st.session_state : 
        st.session_state.history = []

    if 'ordering_lists' not in st.session_state : 
        st.session_state.ordering_lists = load_json(st.session_state.config['main']['path']['ordering-lists'])

    if 'purchases' not in st.session_state : 
        st.session_state.purchases = load_json(st.session_state.config['main']['path']['purchases'])

    st.session_state.root_csv_columns = [
        'Barcode' , 
        'Product Name' , 
        'Packing Size' , 
        'Previous Price' , 
        'Discount' , 
        'Pack Price' , 
        'Supplier' , 
        'Selling Price' , 
        'Promotion Price' , 
        'Other' , 
        'Filename'
    ]

    if 'pending_po_data' not in st.session_state : 
        st.session_state.pending_po_data = []

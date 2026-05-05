import os
import yaml

import polars as pl
import streamlit as st

from groq import Groq

import google.generativeai as genai

from .services_ import load_json


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

    st.session_state.root_csv_columns = [
        'Barcode' , 
        'Product Name' , 
        'Packing Size' , 
        'Previous Price' , 
        'Pack Price' , 
        'Supplier' , 
        'Selling Price' , 
        'Promotion Price' , 
        'Other' , 
        'Filename'
    ]

    if 'pending_po_data' not in st.session_state : 
        st.session_state.pending_po_data = []

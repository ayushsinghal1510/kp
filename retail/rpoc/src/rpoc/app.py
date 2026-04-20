import os
import yaml

import streamlit as st

from dotenv import load_dotenv

from rpoc.services import load_session_state


import google.generativeai as genai

load_dotenv()
load_session_state()

st.set_page_config(layout="wide")

genai.configure(api_key = os.environ['GEMINI_API_KEY'])

pages = {
    "Master List" : [
        st.Page("pages_/master_list.py", title="Master List", icon="📋"),
    ],
    "Chatbot" : [
        st.Page("pages_/chatbot_.py", title="Chatbot", icon="🧠"),
    ],
    "Operations": [

        st.Page("pages_/ordering_lists_.py", title="Ordering Lists", icon="📝"),
        st.Page("pages_/orders_.py", title="Order Management", icon="📦"),
    ],
    "Finance": [
        st.Page("pages_/purchase_.py", title="Financial Purchases", icon="🛒"),
    ]
}

pg = st.navigation(pages)
pg.run()


# if 'purchases'      not in st.session_state: st.session_state.purchases      = load_json(PURCHASES_PATH)
# if 'checkpoints'    not in st.session_state: st.session_state.checkpoints    = load_json(CHECKPOINT_PATH)

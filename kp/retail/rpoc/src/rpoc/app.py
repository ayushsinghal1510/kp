
import streamlit as st

from dotenv import load_dotenv

from rpoc.services import load_session_state

load_dotenv()
load_session_state()

st.set_page_config(layout="wide")

pages = {
    "Master List" : [
        st.Page("pages_/master_list/mlpage.py", title="Master List", icon="📋"),
    ],
    "Chatbot" : [
        st.Page("pages_/chatbot/chpage.py", title="Chatbot", icon="🧠"),
    ],
    "Operations": [

        st.Page("pages_/ordering_lists/olpage.py", title="Ordering Lists", icon="📝"),
        st.Page("pages_/orders/opage.py", title="Order Management", icon="📦"),
    ],
    "Finance": [
        st.Page("pages_/purchase/ppage.py", title="Financial Purchases", icon="🛒"),
    ]
}

pg = st.navigation(pages)
pg.run()


# if 'purchases'      not in st.session_state: st.session_state.purchases      = load_json(PURCHASES_PATH)
# if 'checkpoints'    not in st.session_state: st.session_state.checkpoints    = load_json(CHECKPOINT_PATH)

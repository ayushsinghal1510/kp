from datetime import datetime
import streamlit as st

from rpoc.pages_.orders.render_ol import render_orders_list
from rpoc.pages_.orders.compile_ol import process_compilation_and_po

def initialize_state() -> None : 

    if 'compile_mode' not in st.session_state : 
        st.session_state.compile_mode = False

    if 'selected_for_po' not in st.session_state : 
        st.session_state.selected_for_po = []

    if 'supplier_selections' not in st.session_state : 
        st.session_state.supplier_selections = {}

def render_date_filters() -> tuple : 

    c1 , c2 = st.columns(2)

    start = c1.date_input('Start Date' , value = datetime.now())
    end = c2.date_input('End Date' , value = datetime.now())

    return start , end

initialize_state()

start , end = render_date_filters()

selected : list = render_orders_list(
    start , 
    end
)

if st.button('Compile Orders' , type = 'primary') and selected : 

    st.session_state.compile_mode = True
    st.session_state.selected_for_po = selected
    st.rerun()

if st.session_state.compile_mode : 
    process_compilation_and_po()
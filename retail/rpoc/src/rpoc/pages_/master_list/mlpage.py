import streamlit as st

from typing import Any

from rpoc.pages_.master_list.subpages import (
    handle_excel_upload_section , 
    handle_po_upload_section , 
    handle_po_approval_section , 
    handle_master_list_display
)

st.header(st.session_state.master_list_config['header'])

top_cols : list[Any] = st.columns(2)
col_excel : Any = top_cols[0]
col_po : Any = top_cols[1]

handle_excel_upload_section(col_excel)
handle_po_upload_section(col_po)

if st.session_state.get('pending_po_data') : 
    handle_po_approval_section()

handle_master_list_display()


import streamlit as st

from datetime import datetime

from datetime import date
from typing import Any

from .services_ import view_order_dialog , edit_order_dialog 
from ....services import save_json

def render_orders_list(start : date , end : date) -> list : 

    visible : list = [
        (index , ol) for index , ol in enumerate(
            st.session_state.ordering_lists
        )
        if start <= datetime.fromisoformat(
            ol['timestamp']
        ).date() <= end
    ]
    selected : list = []

    all_product_names_tab4 : list = (
        sorted(
            st.session_state.df['Product Name'].drop_nans().unique().to_list()
        )
        if 'Product Name' in st.session_state.df.columns else []
    )

    index : int
    order : dict
    for index , order in visible : 

        col_s : Any
        col_info : Any
        col_v : Any
        col_e : Any
        col_d : Any
        col_s , col_info , col_v , col_e , col_d = st.columns([0.5 , 3 , 0.7 , 0.7 , 0.7])

        comp : bool = order.get('status') == 'completed'

        if comp : 
            col_s.write('✅')

        elif col_s.checkbox('' , key = f's_{index}') : 
            selected.append(index)

        status_color : str = 'green' if comp else 'orange'
        status_text : str = order.get('status' , 'pending').upper()
        
        col_info.markdown(f"**{order['name']}** | {order['supplier']} | :{status_color}[{status_text}]")

        if col_v.button('View' , key = f'v_{index}') : 
            view_order_dialog(order , index)

        if not comp : 

            if col_e.button('Edit' , key = f'e_{index}') : 

                edit_order_dialog(
                    order , 
                    index , 
                    all_product_names_tab4
                )

        if col_d.button('🗑️' , key = f'del_{index}') : 
            
            st.session_state.ordering_lists.pop(index)
            
            save_json(
                st.session_state.config['main']['path']['ordering-lists'] , 
                st.session_state.ordering_lists
            )

            st.rerun()

    return selected
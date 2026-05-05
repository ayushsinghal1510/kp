import streamlit as st
import pandas as pd

from .services import (
    apply_master_list_pricing , 
    calculate_financial_metrics , 
    render_financial_summary , 
    render_export_options
)

def display_purchase_reports() -> None : 

    if 'purchases' not in st.session_state or not st.session_state.purchases : 
        st.info('No data.')

    else : 

        purchase : dict
        for purchase in st.session_state.purchases : 

            po_num : str = purchase.get('po_number' , 'N/A')

            with st.expander(
                f"Supplier : {purchase['Supplier']} | Date : {purchase['date']} | PO# : {po_num}" , 
                expanded = True
            ) : 

                products : pd.DataFrame = pd.DataFrame(purchase['products'])

                products = apply_master_list_pricing(products)
                products = calculate_financial_metrics(products)

                st.dataframe(products , hide_index = True)

                st.markdown('---')

                render_financial_summary(products)
                render_export_options(
                    purchase , 
                    products , 
                    po_num
                )
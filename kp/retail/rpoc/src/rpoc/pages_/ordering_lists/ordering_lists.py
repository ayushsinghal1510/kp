from datetime import datetime
import streamlit as st
import pandas as pd
import time
from typing import Any

from .services_ import process_order_image

from ...services import save_json , get_packing_size

def handle_ordering_lists() -> None : 

    ups : list[Any] | None = st.file_uploader(
        **st.session_state.ordering_lists_config['file-uploader']
    )

    if st.button('Process Images') and ups : 

        with st.spinner('AI Reading...') : 

            file : Any
            for file in ups : 

                st.session_state.ordering_lists.append(
                    process_order_image(
                        file , 
                        st.session_state.groq_client
                    )
                )

            save_json(
                st.session_state.config['main']['path']['ordering-lists'] , 
                st.session_state.ordering_lists
            )

            st.success(f'Successfully created {len(ups)} ordering list(s) from images!')
            
            time.sleep(1.5)

            st.rerun()

    all_product_names : list[str] = (
        sorted(st.session_state.df['Product Name'].drop_nans().unique().to_list())
        if 'Product Name' in st.session_state.df.columns else []
    )

    manual_list_name : str = st.text_input(
        **st.session_state.ordering_lists_config['manual-list-name']
    )
    
    selected_products : list[str] = st.multiselect(
        options = all_product_names , 
        **st.session_state.ordering_lists_config['selected-products']
    )

    if selected_products : 

        p : str
        preview : list[dict[str , Any]] = [
            {
                'Product Name' : p , 
                'Packing Size (auto)' : get_packing_size(
                    p , 
                    st.session_state.df
                )
            }
            for p in selected_products
        ]

        st.dataframe(
            pd.DataFrame(preview) , 
            hide_index = True , 
            use_container_width = True
        )

    if (
        st.button('Create Manual Ordering List') and 
        manual_list_name and 
        selected_products
    ) : 

        manual_orders : list[dict[str , Any]] = [
            {
                'product_name' : p , 
                'quantity' : 0 , 
                'packing_size' : get_packing_size(
                    p , 
                    st.session_state.df
                )
            }
            for p in selected_products
        ]

        st.session_state.ordering_lists.append(
            {
                'filename' : 'manual' , 
                'name' : manual_list_name , 
                'supplier' : 'Manual' , 
                'purchase_order_date' : datetime.now().strftime('%Y-%m-%d') , 
                'orders' : manual_orders , 
                'status' : 'pending' , 
                'timestamp' : datetime.now().isoformat()
            }
        )
        
        save_json(
            st.session_state.config['main']['path']['ordering-lists'] , 
            st.session_state.ordering_lists
        )

        st.success(f'Created "{manual_list_name}" with {len(selected_products)} products.')

        time.sleep(3)

        st.rerun()
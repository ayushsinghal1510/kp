import pandas as pd
import streamlit as st

from typing import Any

from ....services import get_packing_size , save_json

@st.dialog('Order Details')
def view_order_dialog(ol : dict , _ : int) -> None : 

    st.write(f"**Name :** {ol['name']}")
    st.write(f"**Supplier :** {ol['supplier']}")

    st.table(pd.DataFrame(ol['orders']))

@st.dialog('Edit Order' , width = 'large')
def edit_order_dialog(
    o : dict , i : int , 
    all_product_names : list
) -> None : 

    st.session_state.ordering_lists[i]['name'] = st.text_input(
        'Order Name' , 
        o['name'] , 
        key = f'edit_name_{i}'
    )

    st.session_state.ordering_lists[i]['supplier'] = st.text_input(
        'Supplier' , 
        o.get(
            'supplier' , 
            ''
        ) , 
        key = f'edit_sup_{i}'
    )

    st.markdown('#### Edit Existing Products')
    updated_orders : list = []

    j : int
    item : dict
    for j , item in enumerate(list(o['orders'])) : 

        st.markdown(
            f'**Product {j + 1}**'
        )

        ec1 : Any
        ec2 : Any
        ec3 : Any
        ec4 : Any
        ec1 , ec2 , ec3 , ec4 = st.columns([2 , 1 , 1 , 0.5])

        cur_prod : str = item.get('product_name' , '')

        ec1.text(f'📦 {cur_prod}')

        auto_pk : float = get_packing_size(cur_prod , st.session_state.df)
        
        raw_pk : Any = item.get('packing_size')

        saved_pk : float = float(raw_pk) if raw_pk is not None else 0.0
        pk_val : float = saved_pk if saved_pk != 0.0 else auto_pk

        raw_qty : Any = item.get('quantity')
        saved_qty : int = int(raw_qty) if raw_qty is not None else 1

        new_qty : int = ec2.number_input(
            'Qty (CTN)' , 
            value = saved_qty , 
            min_value = 0 , 
            step = 1 , 
            key = f'edit_qty_{i}_{j}'
        )
        
        ec3.markdown(f'**Packing Size :** {pk_val}')
        new_pk : float = pk_val

        keep : bool = ec4.checkbox(
            'Keep' , 
            value = True , 
            key = f'edit_keep_{i}_{j}'
        )

        if keep : 

            updated_orders.append(
                {
                    'product_name' : cur_prod , 
                    'quantity' : new_qty , 
                    'packing_size' : new_pk
                }
            )

    st.markdown('---')
    st.markdown('#### ➕ Add New Products')

    already_in_order : set = set(item.get('product_name' , '') for item in o['orders'])

    p : str
    available_to_add : list = [p for p in all_product_names if p not in already_in_order]

    if available_to_add : 

        new_products_to_add : list = st.multiselect(
            'Select products to add (already-in-order products are excluded)' , 
            options = available_to_add , 
            key = f'new_prod_multiselect_{i}'
        )

        new_prod : str
        for new_prod in new_products_to_add : 

            auto_pk_add : float = get_packing_size(new_prod , st.session_state.df)

            na1 : Any
            na2 : Any
            na1 , na2 = st.columns([2 , 1])
            
            na1.text(f'📦 {new_prod}  (Packing Size : {auto_pk_add})')
            
            new_qty_add : int = na2.number_input(
                f'Qty (CTN) for {new_prod}' , 
                value = 1 , 
                min_value = 0 , 
                step = 1 , 
                key = f'new_qty_add_{i}_{new_prod}'
            )
            
            updated_orders.append(
                {
                    'product_name' : new_prod , 
                    'quantity' : new_qty_add , 
                    'packing_size' : auto_pk_add
                }
            )
            
    else : 
        st.info('All available products are already in this order.')

    if st.button('Save Changes' , key = f'save_edit_{i}') : 

        st.session_state.ordering_lists[i]['orders'] = updated_orders

        save_json(
            st.session_state.config['main']['path']['ordering-lists'] , 
            st.session_state.ordering_lists
        )

        st.success('Saved!')

        st.rerun()
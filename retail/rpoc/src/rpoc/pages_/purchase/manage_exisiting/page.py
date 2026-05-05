import streamlit as st

from pandas import DataFrame

from ....services import save_json

def manage_existing_purchases() -> None : 

    st.markdown('---')
    st.markdown('### 📜 Manage Existing Purchases')

    if st.session_state.purchases : 

        p_idx : int
        purchase_record : dict

        for p_idx , purchase_record in enumerate(list(st.session_state.purchases)) : 

            sup_name : str = purchase_record.get('Supplier' , 'Unknown')
            po_num : str = purchase_record.get('po_number' , 'N/A')

            with st.expander(f'🛒 {sup_name} (PO : {po_num})') : 

                products_list : list = purchase_record.get('products' , [])

                if products_list : 

                    st.dataframe(
                        DataFrame(products_list) , 
                        use_container_width = True
                    )

                st.markdown('**Danger Zone**')

                if st.button(
                    '🗑️ Delete Entire Purchase' , 
                    key = f'del_pur_{p_idx}' , 
                    type = 'primary'
                ) : 

                    st.session_state.purchases.pop(p_idx)

                    save_json(
                        st.session_state.config['main']['path']['purchases'] , 
                        st.session_state.purchases
                    )

                    st.success('Purchase deleted completely!')

                    st.rerun()

    else : 
        st.info('No existing purchases found.')

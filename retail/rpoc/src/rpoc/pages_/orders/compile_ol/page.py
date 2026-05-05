import streamlit as st
import polars as pl

from ....services import load_json , get_packing_size
from .services import generate_purchase_orders

def process_compilation_and_po() -> None : 

    st.markdown('---')
    st.markdown('### 🛠️ Compile Orders & Select Suppliers')
    
    vendor_file : str = st.session_state.config.get(
        'main' , {}
    ).get(
        'path' , {}
    ).get(
        'previous-vendors' , 'previous_vendors.json'
    )
    
    previous_vendors : dict = load_json(vendor_file)

    product_requirements : dict = {}

    idx : int
    for idx in st.session_state.selected_for_po : 

        order_data : dict = st.session_state.ordering_lists[idx]

        item : dict

        for item in order_data.get('orders' , []) : 
            
            p_name = item.get('product_name' , '')
            qty : float = float(item.get('quantity' , 0.0) or 0.0)

            if p_name : 

                product_requirements[p_name] = product_requirements.get(p_name , 0.0) + qty

    df_catalog : pl.DataFrame = st.session_state.df
    
    p_name : str
    total_qty : float
    for p_name , total_qty in product_requirements.items() : 

        with st.expander(f'📦 {p_name} (Total Qty : {total_qty})') : 

            p_df : pl.DataFrame = df_catalog.filter(pl.col('Product Name') == p_name)

            if p_df.is_empty() : 

                st.warning(f'No supplier data found for {p_name}')
                continue

            supplier_options : list = p_df.drop_nulls(subset = ['Supplier'])['Supplier'].unique().to_list()

            if not supplier_options : 

                st.warning(f'No valid suppliers found for {p_name}')
                continue

            display_data : list = []

            sup : str
            for sup in supplier_options : 

                sup_row_df : pl.DataFrame = p_df.filter(pl.col('Supplier') == sup)
                sup_row : dict = sup_row_df.row(0 , named = True)

                pack_price : float = float(sup_row.get('Pack Price' , 0.0) or 0.0)
                packing_size : float = float(sup_row.get('Packing Size' , 1.0) or 1.0)

                if packing_size == 0.0 : 
                    packing_size = 1.0

                gst_val : float = float(sup_row.get('GST' , 0.09) or 0.09)
                gst_mult : float = 1.0 + gst_val

                unit_price : float = pack_price / packing_size
                total_price : float = pack_price * total_qty

                display_data.append(
                    {
                        'Supplier' : sup , 
                        'Unit Price' : unit_price , 
                        'Packing Price' : pack_price , 
                        'Total Price' : total_price , 
                        'Unit Price WGST' : unit_price * gst_mult , 
                        'Packing Price WGST' : pack_price * gst_mult , 
                        'Total Price WGST' : total_price * gst_mult
                    }
                )

            df_sup_pl : pl.DataFrame = pl.DataFrame(display_data).sort(
                'Total Price' , 
                descending = False
            )

            lowest_vendor : str = df_sup_pl['Supplier'][0]
            highest_vendor : str = df_sup_pl['Supplier'][-1]
            prev_vendor : str = previous_vendors.get(p_name , 'None')

            st.markdown(f'**Lowest Price Vendor :** {lowest_vendor}')
            st.markdown(f'**Highest Price Vendor :** {highest_vendor}')
            st.markdown(f'**Previously Chosen Vendor :** {prev_vendor}')

            st.dataframe(df_sup_pl.to_pandas())
            
            chosen_sup = st.selectbox(
                f'Select Supplier for {p_name}' , 
                options = df_sup_pl['Supplier'].to_list() , 
                index = 0 , 
                key = f'sel_sup_{p_name}'
            )

            selected_row : dict = df_sup_pl.filter(pl.col('Supplier') == chosen_sup).row(0 , named = True)

            sup_full_row : dict = p_df.filter(pl.col('Supplier') == chosen_sup).row(0 , named = True)

            st.session_state.supplier_selections[p_name] = {
                'supplier' : chosen_sup , 
                'qty' : total_qty , 
                'price' : selected_row['Packing Price'] , 
                'gst' : float(sup_full_row.get('GST' , 0.0) or 0.0) , 
                'packing_size' : get_packing_size(p_name , df_catalog)
            }

    if st.button(
        'Create Purchase Order' , 
        type = 'primary'
    ) : 
        generate_purchase_orders(
            vendor_file , 
            previous_vendors
        )

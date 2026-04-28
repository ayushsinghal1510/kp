from datetime import datetime
import json
import os
import streamlit as st
import pandas as pd
import polars as pl

from rpoc.services import (
    get_packing_size , 
    save_json , 
    get_next_po_number , 
    calculate_purchase_metrics
)

def load_previous_vendors(
    file_path : str
) -> dict : 
    if os.path.exists(file_path) : 
        with open(
            file_path , 
            'r'
        ) as f : 
            return json.load(f)
    return {}

def save_previous_vendors(
    file_path : str , 
    data : dict
) -> None : 
    with open(
        file_path , 
        'w'
    ) as f : 
        json.dump(
            data , 
            f , 
            indent = 4
        )

if 'compile_mode' not in st.session_state : 
    st.session_state.compile_mode : bool = False

if 'selected_for_po' not in st.session_state : 
    st.session_state.selected_for_po : list = []

if 'supplier_selections' not in st.session_state : 
    st.session_state.supplier_selections : dict = {}

c1 , c2 = st.columns(2)

start : datetime.date = c1.date_input(
    'Start Date' , 
    value = datetime.now()
)
end : datetime.date = c2.date_input(
    'End Date' , 
    value = datetime.now()
)

visible : list = [
    (index , ol) for index , ol in enumerate(st.session_state.ordering_lists)
    if start <= datetime.fromisoformat(ol['timestamp']).date() <= end
]
selected : list = []

all_product_names_tab4 : list = (
    sorted(st.session_state.df['Product Name'].drop_nans().unique().to_list())
    if 'Product Name' in st.session_state.df.columns else []
)

for index , order in visible : 

    col_s , col_info , col_v , col_e , col_d = st.columns([0.5 , 3 , 0.7 , 0.7 , 0.7])

    comp : bool = order.get('status') == 'completed'

    if comp : 
        col_s.write('✅')

    elif col_s.checkbox(
        '' , 
        key = f's_{index}'
    ) : 
        selected.append(index)

    status_color : str = 'green' if comp else 'orange'
    status_text : str = order.get('status' , 'pending').upper()
    
    col_info.markdown(
        f"**{order['name']}** | {order['supplier']} | "
        f":{status_color}[{status_text}]"
    )

    if col_v.button(
        'View' , 
        key = f'v_{index}'
    ) : 

        @st.dialog('Order Details')
        def view_dialog(
            ol : dict , 
            _ : int
        ) : 

            st.write(f"**Name:** {ol['name']}")
            st.write(f"**Supplier:** {ol['supplier']}")

            st.table(pd.DataFrame(ol['orders']))

        view_dialog(
            order , 
            index
        )

    if col_e.button(
        'Edit' , 
        key = f'e_{index}'
    ) : 

        @st.dialog(
            'Edit Order' , 
            width = 'large'
        )
        def edit_dialog(
            o : dict , 
            i : int
        ) : 

            st.session_state.ordering_lists[i]['name'] = st.text_input(
                'Order Name' , 
                o['name'] , 
                key = f'edit_name_{i}'
            )

            st.session_state.ordering_lists[i]['supplier'] = st.text_input(
                'Supplier' , 
                o.get('supplier' , '') , 
                key = f'edit_sup_{i}'
            )

            st.markdown('#### Edit Existing Products')
            updated_orders : list = []

            for j , item in enumerate(list(o['orders'])) : 

                st.markdown(f'**Product {j+1}**')

                ec1 , ec2 , ec3 , ec4 = st.columns([2 , 1 , 1 , 0.5])

                cur_prod : str = item.get('product_name' , '')

                ec1.text(f'📦 {cur_prod}')

                auto_pk : float = get_packing_size(
                    cur_prod , 
                    st.session_state.df
                )
                saved_pk : float = float(item.get('packing_size' , 0) or 0)
                pk_val : float = saved_pk if saved_pk != 0 else auto_pk

                new_qty : float = ec2.number_input(
                    'Qty (CTN)' , 
                    value = float(item.get('quantity' , 0) or 0) , 
                    min_value = 0.0 , 
                    key = f'edit_qty_{i}_{j}'
                )
                
                new_pk : float = ec3.number_input(
                    'Packing Size' , 
                    value = pk_val , 
                    min_value = 0.0 , 
                    key = f'edit_pk_{i}_{j}'
                )

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
            available_to_add : list = [p for p in all_product_names_tab4 if p not in already_in_order]

            if available_to_add : 
                new_products_to_add : list = st.multiselect(
                    'Select products to add (already-in-order products are excluded)' , 
                    options = available_to_add , 
                    key = f'new_prod_multiselect_{i}'
                )

                for new_prod in new_products_to_add : 
                    auto_pk_add : float = get_packing_size(
                        new_prod , 
                        st.session_state.df
                    )
                    na1 , na2 = st.columns([2 , 1])
                    na1.text(f'📦 {new_prod}  (Packing Size: {auto_pk_add})')
                    
                    new_qty_add : float = na2.number_input(
                        f'Qty (CTN) for {new_prod}' , 
                        value = 0.0 , 
                        min_value = 0.0 , 
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

            if st.button(
                'Save Changes' , 
                key = f'save_edit_{i}'
            ) : 
                st.session_state.ordering_lists[i]['orders'] = updated_orders
                
                save_json(
                    st.session_state.config['main']['path']['ordering-lists'] , 
                    st.session_state.ordering_lists
                )
                
                st.success('Saved!')
                st.rerun()

        edit_dialog(
            order , 
            index
        )

    if col_d.button(
        '🗑️' , 
        key = f'del_{index}'
    ) : 
        st.session_state.ordering_lists.pop(index)
        
        save_json(
            st.session_state.config['main']['path']['ordering-lists'] , 
            st.session_state.ordering_lists
        )
        
        st.rerun()


if st.button(
    'Compile Orders' , 
    type = 'primary'
) and selected : 
    st.session_state.compile_mode = True
    st.session_state.selected_for_po = selected
    st.rerun()


if st.session_state.compile_mode : 
    st.markdown('---')
    st.markdown('### 🛠️ Compile Orders & Select Suppliers')
    
    vendor_file : str = st.session_state.config.get(
        'main' , 
        {}
    ).get(
        'path' , 
        {}
    ).get(
        'previous-vendors' , 
        'previous_vendors.json'
    )
    
    previous_vendors : dict = load_previous_vendors(vendor_file)
    
    product_requirements : dict = {}

    for idx in st.session_state.selected_for_po : 
        order_data : dict = st.session_state.ordering_lists[idx]

        for item in order_data.get('orders' , []) : 
            p_name : str = item.get('product_name' , '')
            qty : float = float(item.get('quantity' , 0.0) or 0.0)

            if p_name : 
                product_requirements[p_name] = product_requirements.get(
                    p_name , 
                    0.0
                ) + qty
                
    df_catalog : pl.DataFrame = st.session_state.df
    
    for p_name , total_qty in product_requirements.items() : 
        with st.expander(f'📦 {p_name} (Total Qty : {total_qty})') : 
            
            p_df : pl.DataFrame = df_catalog.filter(
                pl.col('Product Name') == p_name
            )
            
            if p_df.is_empty() : 
                st.warning(f'No supplier data found for {p_name}')
                continue
                
            supplier_options : list = p_df.drop_nulls(
                subset = ['Supplier']
            )['Supplier'].unique().to_list()
            
            if not supplier_options : 
                st.warning(f'No valid suppliers found for {p_name}')
                continue
                
            display_data : list = []

            for sup in supplier_options : 
                
                sup_row_df : pl.DataFrame = p_df.filter(
                    pl.col('Supplier') == sup
                )
                sup_row : dict = sup_row_df.row(
                    0 , 
                    named = True
                )
                
                pack_price : float = float(sup_row.get('Pack Price' , 0.0) or 0.0)
                packing_size : float = float(sup_row.get('Packing Size' , 1.0) or 1.0)
                
                if packing_size == 0.0 : 
                    packing_size = 1.0
                    
                gst_val : float = float(sup_row.get('GST' , 0.0) or 0.0)
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
            prev_vendor : str = previous_vendors.get(
                p_name , 
                'None'
            )
            
            st.markdown(f'**Lowest Price Vendor:** {lowest_vendor}')
            st.markdown(f'**Highest Price Vendor:** {highest_vendor}')
            st.markdown(f'**Previously Chosen Vendor:** {prev_vendor}')
            
            st.dataframe(df_sup_pl.to_pandas())
            
            chosen_sup : str = st.selectbox(
                f'Select Supplier for {p_name}' , 
                options = df_sup_pl['Supplier'].to_list() , 
                index = 0 , 
                key = f'sel_sup_{p_name}'
            )
            
            selected_row : dict = df_sup_pl.filter(
                pl.col('Supplier') == chosen_sup
            ).row(
                0 , 
                named = True
            )
            
            sup_full_row : dict = p_df.filter(
                pl.col('Supplier') == chosen_sup
            ).row(
                0 , 
                named = True
            )
            
            st.session_state.supplier_selections[p_name] = {
                'supplier' : chosen_sup , 
                'qty' : total_qty , 
                'price' : selected_row['Packing Price'] , 
                'gst' : float(sup_full_row.get('GST' , 0.0) or 0.0) , 
                'packing_size' : get_packing_size(
                    p_name , 
                    df_catalog
                )
            }

    if st.button(
        'Create Purchase Order' , 
        type = 'primary'
    ) : 
        agg : dict = {}

        for p_name , details in st.session_state.supplier_selections.items() : 
            sup : str = details['supplier']

            if sup not in agg : 
                agg[sup] : dict = {}
                
            agg[sup][p_name] = {
                'quantity' : details['qty'] , 
                'packing_size' : details['packing_size'] , 
                'price' : details['price'] , 
                'gst' : details['gst']
            }
            
            previous_vendors[p_name] = sup
            
        save_previous_vendors(
            vendor_file , 
            previous_vendors
        )
        
        for index in st.session_state.selected_for_po : 
            st.session_state.ordering_lists[index]['status'] = 'completed'

        new_purchases : list = []

        for supplier , products in agg.items() : 

            po_num : str = get_next_po_number(st.session_state.config['main']['path']['po-file'])

            new_purchases.append(
                {
                    'Supplier' : supplier , 
                    'date' : datetime.now().strftime('%d %m %Y') , 
                    'po_number' : po_num , 
                    'products' : [
                        calculate_purchase_metrics(
                            product , 
                            product_details['quantity'] , 
                            product_details['packing_size'] , 
                            product_details['price'] , 
                            product_details['gst']
                        ) for product , product_details in products.items()
                    ]
                }
            )

        existing_supplier : dict = {pur['Supplier'] : pur for pur in st.session_state.purchases}

        for new_purchase in new_purchases : 

            supplier_name : str = new_purchase['Supplier']

            if supplier_name in existing_supplier : 

                existing_items : dict = {
                    item['Product Name'] : item 
                    for item in existing_supplier[supplier_name]['products']
                }

                for new_products in new_purchase['products'] : 
                    pname : str = new_products['Product Name']

                    if pname in existing_items : 

                        combined_qty : float = existing_items[pname]['Qty'] + new_products['Qty']

                        existing_items[pname] = calculate_purchase_metrics(
                            pname , 
                            combined_qty , 
                            new_products['Packing Size'] , 
                            new_products['Ctn Price WOGST'] , 
                            new_products['GST']
                        )

                    else : 
                        existing_items[pname] = new_products

                existing_supplier[supplier_name]['products'] = list(existing_items.values())

            else : 
                existing_supplier[supplier_name] = new_purchase

        st.session_state.purchases = list(existing_supplier.values())

        save_json(
            st.session_state.config['main']['path']['purchases'] , 
            st.session_state.purchases
        )
        save_json(
            st.session_state.config['main']['path']['ordering-lists'] , 
            st.session_state.ordering_lists
        )
        
        st.session_state.compile_mode = False
        st.session_state.selected_for_po = []
        st.session_state.supplier_selections = {}

        st.success('Purchase Orders generated successfully!')
        st.rerun()
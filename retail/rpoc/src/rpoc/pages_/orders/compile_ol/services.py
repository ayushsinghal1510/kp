import streamlit as st

from datetime import datetime

from ....services import save_json , load_json

def generate_purchase_orders(
    vendor_file : str , 
    previous_vendors : dict
) -> None : 

    agg : dict = {}

    p_name : str
    details : dict

    for p_name , details in st.session_state.supplier_selections.items() : 

        sup : str = details['supplier']

        if sup not in agg : 
            agg[sup] = {}

        agg[sup][p_name] = {
            'quantity' : details['qty'] , 
            'packing_size' : details['packing_size'] , 
            'price' : details['price'] , 
            'gst' : details['gst']
        }

        previous_vendors[p_name] = sup

    save_json(vendor_file , previous_vendors)

    index : int

    for index in st.session_state.selected_for_po : 
        st.session_state.ordering_lists[index]['status'] = 'completed'

    new_purchases : list = []

    supplier : str
    products : dict

    for supplier , products in agg.items() : 

        po_num : str = get_next_po_number(st.session_state.config['main']['path']['po-file'])

        new_purchases.append(
            {
                'Supplier' : supplier , 
                'date' : datetime.now().strftime(
                    '%d %m %Y'
                ) , 
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

    new_purchase : dict
    for new_purchase in new_purchases : 

        supplier_name : str = new_purchase['Supplier']

        if supplier_name in existing_supplier : 

            existing_items : dict = {
                item['Product Name'] : item 
                for item in existing_supplier[supplier_name]['products']
            }

            new_products : dict

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

def get_next_po_number(po_file_path) -> str : 

    counter_data = load_json(po_file_path)

    if (
        not counter_data or 
        not isinstance(counter_data , dict)
    ) : 
        counter_data = {"counter" : 0}

    counter_data["counter"] += 1

    save_json(po_file_path , counter_data)

    return f"PO-{counter_data['counter']:05d}"

def calculate_purchase_metrics(
    product_name : str , 
    qty_ctn : int , 
    packing_size : int , 
    ctn_price : float , 
    gst_rate : float 
) -> dict : 

    # * Everything gets changed to sgd

    qty_ctn = float(qty_ctn)
    packing_size = float(packing_size)
    ctn_price = float(ctn_price)

    total_qty = qty_ctn * packing_size
    unit_p_raw = ctn_price / packing_size if packing_size > 0 else 0
    total_raw = qty_ctn * ctn_price

    try:
        gst_rate = float(gst_rate)
    except (ValueError, TypeError):
        gst_rate = 0.0

    gst_mult = 1 + gst_rate

    return {
        "Product Name" : product_name , 
        "Qty" : qty_ctn , 
        "Packing Size" : packing_size , 
        "Total Ordered Qty" : total_qty , 
        "Ctn Price WOGST" : round(ctn_price , 2) , 
        "Unit Price WOGST" : round(unit_p_raw , 4) , 
        "Total WOGST" : round(total_raw , 2) , 
        'GST' : gst_rate * 100 , 
        "Ctn Price WGST": round(ctn_price * gst_mult, 2),  
        "Unit Cost WGST": round(unit_p_raw * gst_mult, 4), 
        "Total Cost WGST": round(total_raw * gst_mult, 2)
    }

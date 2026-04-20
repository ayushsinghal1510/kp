from datetime import datetime
import json
import streamlit as st
import pandas as pd

from rpoc.services import (
    get_packing_size , 
    save_json , 
    consolidate_selected_orders , 
    get_next_po_number , 
    calculate_purchase_metrics
)


c1 , c2 = st.columns(2)

start = c1.date_input("Start Date" , value = datetime.now())
end   = c2.date_input("End Date" , value = datetime.now())

visible  = [
    (index , ol) for index , ol in enumerate(st.session_state.ordering_lists)
    if start <= datetime.fromisoformat(ol['timestamp']).date() <= end
]
selected = []

all_product_names_tab4 = (
    sorted(st.session_state.df['Product Name'].drop_nans().unique().to_list())
    if 'Product Name' in st.session_state.df.columns else []
)

for index , order in visible : 

    col_s , col_info , col_v , col_e , col_d = st.columns([0.5 , 3 , 0.7 , 0.7 , 0.7])

    comp = order.get("status") == "completed"

    if comp : 
        col_s.write("✅")

    elif col_s.checkbox("" , key = f"s_{index}") : 
        selected.append(index)

    col_info.markdown(
        f"**{order['name']}** | {order['supplier']} | "
        f":{'green' if comp else 'orange'}[{order.get('status' , 'pending').upper()}]"
    )

    if col_v.button("View" , key = f"v_{index}") : 

        @st.dialog("Order Details")
        def view_dialog(ol, _) : 

            st.write(f"**Name:** {ol['name']}")
            st.write(f"**Supplier:** {ol['supplier']}")

            st.table(pd.DataFrame(ol['orders']))

        view_dialog(order , index)

    if col_e.button("Edit" , key = f"e_{index}") : 

        @st.dialog("Edit Order" , width = "large")
        def edit_dialog(o, i) : 

            st.session_state.ordering_lists[i]['name'] = st.text_input(
                "Order Name" , 
                o['name'] , 
                key = f"edit_name_{i}"
            )

            st.session_state.ordering_lists[i]['supplier'] = st.text_input(
                "Supplier" , 
                o.get('supplier' , '') , 
                key = f"edit_sup_{i}"
            )

            st.markdown("#### Edit Existing Products")
            updated_orders = []

            for j , item in enumerate(list(o['orders'])) : 

                st.markdown(f"**Product {j+1}**")

                ec1 , ec2 , ec3 , ec4 = st.columns([2 , 1 , 1 , 0.5])

                cur_prod = item.get('product_name' , '')

                ec1.text(f"📦 {cur_prod}")

                auto_pk = get_packing_size(cur_prod , st.session_state.df)
                saved_pk = float(item.get('packing_size' , 0) or 0)
                pk_val = saved_pk if saved_pk != 0 else auto_pk

                new_qty = ec2.number_input(
                    "Qty (CTN)" , 
                    value = float(item.get('quantity' , 0) or 0) , 
                    min_value = 0.0 , 
                    key = f"edit_qty_{i}_{j}"
                )
                new_pk = ec3.number_input(
                    "Packing Size" , 
                    value = pk_val , 
                    min_value = 0.0 , 
                    key = f"edit_pk_{i}_{j}"
                )

                keep = ec4.checkbox(
                    "Keep" , 
                    value = True , 
                    key = f"edit_keep_{i}_{j}"
                )

                if keep : 
                    updated_orders.append(
                        {
                            "product_name" : cur_prod , 
                            "quantity" : new_qty , 
                            "packing_size" : new_pk
                        }
                    )

            st.markdown("---")
            st.markdown("#### ➕ Add New Products")

            # Exclude products already in the order from the available options
            already_in_order = set(item.get('product_name', '') for item in o['orders'])
            available_to_add = [p for p in all_product_names_tab4 if p not in already_in_order]

            if available_to_add:
                new_products_to_add = st.multiselect(
                    "Select products to add (already-in-order products are excluded)",
                    options=available_to_add,
                    key=f"new_prod_multiselect_{i}"
                )

                for new_prod in new_products_to_add:
                    auto_pk_add = get_packing_size(new_prod, st.session_state.df)
                    na1, na2 = st.columns([2, 1])
                    na1.text(f"📦 {new_prod}  (Packing Size: {auto_pk_add})")
                    new_qty_add = na2.number_input(
                        f"Qty (CTN) for {new_prod}",
                        value=0.0, min_value=0.0,
                        key=f"new_qty_add_{i}_{new_prod}"
                    )
                    updated_orders.append({
                        "product_name": new_prod,
                        "quantity": new_qty_add,
                        "packing_size": auto_pk_add
                    })
            else:
                st.info("All available products are already in this order.")

            if st.button("Save Changes", key=f"save_edit_{i}"):
                st.session_state.ordering_lists[i]['orders'] = updated_orders
                save_json(st.session_state.config['main']['path']['ordering-lists'], st.session_state.ordering_lists)
                st.success("Saved!")
                st.rerun()

        edit_dialog(order, index)

    if col_d.button("🗑️", key=f"del_{index}"):
        st.session_state.ordering_lists.pop(index)
        save_json(st.session_state.config['main']['path']['ordering-lists'], st.session_state.ordering_lists)
        st.rerun()

if st.button("Consolidate & Generate Purchases" , type = "primary") and selected : 

    agg = consolidate_selected_orders(selected, st.session_state.ordering_lists, st.session_state.df)
    for index in selected:
        st.session_state.ordering_lists[index]['status'] = 'completed'

    new_purchases = []

    print(agg)
    for supplier , products in agg.items() : 

        po_num = get_next_po_number(st.session_state.config['main']['path']['po-file'])


        new_purchases.append(
            {
                "Supplier" : supplier , 
                "date" : datetime.now().strftime("%d %m %Y") , 
                "po_number" : po_num , 
                "products" : [
                    calculate_purchase_metrics(
                        product , 
                        product_details['quantity'] , 
                        product_details['packing_size'] , 
                        product_details['price'] , 
                        product_details['gst']
                    ) for product , product_details in products.items()
                ]
        })

    existing_supplier = {pur['Supplier'] : pur for pur in st.session_state.purchases}

    for new_purchase in new_purchases : 

        supplier = new_purchase['Supplier']

        if supplier in existing_supplier : 

            existing_items = {
                item['Product Name'] : item 
                for item in existing_supplier[supplier]['products']
            }

            for new_products in new_purchase['products'] : 
                pname = new_products['Product Name']

                if pname in existing_items : 

                    combined_qty = existing_items[pname]['Qty'] + new_products['Qty']

                    existing_items[pname] = calculate_purchase_metrics(
                        pname , 
                        combined_qty , 
                        new_products['Packing Size'] , 
                        new_products['Ctn Price WOGST'] , 
                        new_products['GST']
                    )

                else : 
                    existing_items[pname] = new_products

            existing_supplier[supplier]['products'] = list(existing_items.values())

        else : 
            existing_supplier[supplier] = new_purchase

    st.session_state.purchases = list(existing_supplier.values())

    save_json(st.session_state.config['main']['path']['purchases'], st.session_state.purchases)
    save_json(st.session_state.config['main']['path']['ordering-lists'], st.session_state.ordering_lists)

    st.rerun()
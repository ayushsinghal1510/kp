import streamlit as st
import pandas as pd
import numpy as np
from fpdf import FPDF

# Assuming build_tmg_excel is defined elsewhere. 
# Ensure you update its definition in rpoc.services to remove the 'include_profit' argument as well!
from rpoc.services import build_tmg_excel , build_tmg_pdf


if 'purchases' not in st.session_state or not st.session_state.purchases: 
    st.info('No data.')
else: 
    for purchase in st.session_state.purchases: 

        po_num = purchase.get('po_number', 'N/A')

        with st.expander(f"Supplier: {purchase['Supplier']} | Date: {purchase['date']} | PO#: {po_num}", expanded=True): 

            products = pd.DataFrame(purchase['products'])

            # ─── NEW: MASTER LIST LOOKUP ──────────────────────────────────────
            # Ensure price columns exist in the incoming invoice dataframe
            products['TMG Selling Price'] = pd.to_numeric(products.get('TMG Selling Price', 0.0), errors='coerce')
            products['TMG Promotion Price'] = pd.to_numeric(products.get('TMG Promotion Price', 0.0), errors='coerce')

            # Check if we have a Master List to pull from
            if 'df' in st.session_state and not st.session_state.df.is_empty():
                # Convert Polars master list to Pandas for the lookup
                master_df = st.session_state.df.to_pandas()
                
                if 'Product Name' in master_df.columns and 'TMG Selling Price' in master_df.columns:
                    # Extract just the unique prices from the master list
                    lookup = master_df[['Product Name', 'TMG Selling Price', 'TMG Promotion Price']].drop_duplicates(subset=['Product Name'], keep='last')
                    
                    # Merge it with our invoice products
                    products = products.merge(lookup, on='Product Name', how='left', suffixes=('', '_master'))
                    
                    # If invoice price is 0, grab the master list price instead
                    products['TMG Selling Price'] = products['TMG Selling Price'].replace(0.0, np.nan).fillna(products['TMG Selling Price_master']).fillna(0.0)
                    products['TMG Promotion Price'] = products['TMG Promotion Price'].replace(0.0, np.nan).fillna(products['TMG Promotion Price_master']).fillna(0.0)
            # ──────────────────────────────────────────────────────────────────

            # ─── 1. ON-THE-FLY CALCULATIONS ───────────────────────────────────
            products['Total Ordered Qty'] = pd.to_numeric(products.get('Total Ordered Qty', 0.0), errors='coerce')
            products['Total Cost WGST'] = pd.to_numeric(products.get('Total Cost WGST', 0.0), errors='coerce')

            # Calculate Totals
            products['Total Selling Base'] = products['TMG Selling Price'] * products['Total Ordered Qty']
            products['Total Selling Promotion'] = products['TMG Promotion Price'] * products['Total Ordered Qty']
            
            # Calculate Absolute Profits
            products['Profit'] = products['Total Selling Base'] - products['Total Cost WGST']
            products['Profit after discount'] = products['Total Selling Promotion'] - products['Total Cost WGST']

            # Calculate Margins (Handles division by zero and 100% loss scenarios)
            products['Profit Margin (Percentage)'] = np.where(
                products['Total Selling Base'] > 0, 
                (products['Profit'] / products['Total Selling Base']) * 100, 
                np.where(products['Total Cost WGST'] > 0, -100.0, 0.0)
            )
            
            products['Profit Margin after discount (Percentage)'] = np.where(
                products['Total Selling Promotion'] > 0, 
                (products['Profit after discount'] / products['Total Selling Promotion']) * 100, 
                np.where(products['Total Cost WGST'] > 0, -100.0, 0.0)
            )

            # Show the main table
            st.dataframe(products, hide_index=True)
            st.markdown("---")

            # ─── 2. SUMMARY MATH ──────────────────────────────────────────────
            gst_rate = products['GST'].iloc[0] if 'GST' in products.columns and not products.empty else 0
            gst_label = f"{int(gst_rate)}%" if gst_rate == int(gst_rate) else f"{gst_rate}%"

            raw_sum = products["Total WOGST"].sum() if "Total WOGST" in products.columns else 0
            wgst_sum = products["Total Cost WGST"].sum()
            gst_amt = wgst_sum - raw_sum  

            sell_base_sum = products["Total Selling Base"].sum()
            sell_promo_sum = products["Total Selling Promotion"].sum()
            
            base_profit_sum = products["Profit"].sum()
            promo_profit_sum = products["Profit after discount"].sum()

            base_margin_overall = (base_profit_sum / sell_base_sum * 100) if sell_base_sum > 0 else 0.0
            promo_margin_overall = (promo_profit_sum / sell_promo_sum * 100) if sell_promo_sum > 0 else 0.0

            # ─── 3. FOUR COLUMN SUMMARY DISPLAY ───────────────────────────────
            c1, c2, c3, c4 = st.columns(4)

            with c1: 
                st.write("**Cost (W/O GST)**")
                st.write(f"Sub Total: ${raw_sum:,.2f}")
                st.write(f"Total: ${raw_sum:,.2f}")

            with c2: 
                st.write(f"**Cost ({gst_label} GST)**")
                st.write(f"Total Cost: ${raw_sum:,.2f}")
                st.write(f"GST: ${gst_amt:,.2f}")
                st.write(f"**TOTAL: ${wgst_sum:,.2f}**")

            with c3:
                st.write("**Base Profit**")
                st.write(f"Total Selling: ${sell_base_sum:,.2f}")
                st.write(f"Total Profit: ${base_profit_sum:,.2f}")
                st.write(f"**Margin: {base_margin_overall:.2f}%**")

            with c4:
                st.write("**Discount Profit**")
                st.write(f"Promo Selling: ${sell_promo_sum:,.2f}")
                st.write(f"Total Profit: ${promo_profit_sum:,.2f}")
                st.write(f"**Margin: {promo_margin_overall:.2f}%**")

            st.markdown("---")
            st.markdown("#### 📥 Download Options")

            # ─── 4. DOWNLOAD TOGGLES & BUTTONS ────────────────────────────────
            dc1, dc2, dc3, dc4 = st.columns(4)
            inc_wogst  = dc1.checkbox("Include W/O GST", value=True, key=f"wogst_{po_num}")
            inc_wgst   = dc2.checkbox("Include W/ GST",  value=True, key=f"wgst_{po_num}")
            inc_base   = dc3.checkbox("Include Base Profit", value=True, key=f"base_{po_num}")
            inc_promo  = dc4.checkbox("Include Discount Profit", value=True, key=f"promo_{po_num}")

            st.markdown("**📊 Export Data:**")
            ex1, ex2 = st.columns(2)

            with ex1:
                st.download_button(
                    "📊 Download Custom Excel",
                    data=build_tmg_excel(purchase['Supplier'], purchase['date'], po_num, products,
                                    inc_wogst, inc_wgst, inc_base, inc_promo),
                    file_name=f"PO_{po_num}_Custom.xlsx",
                    key=f"ex_custom_{po_num}",
                    use_container_width=True
                )
            with ex2:
                st.download_button(
                    "📄 Download Custom PDF",
                    data=build_tmg_pdf(purchase['Supplier'], purchase['date'], po_num, products,
                                    inc_wogst, inc_wgst, inc_base, inc_promo),
                    file_name=f"PO_{po_num}_Custom.pdf",
                    key=f"pdf_custom_{po_num}",
                    use_container_width=True
                )
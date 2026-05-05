import pandas as pd
import streamlit as st
import numpy as np

from pandas import DataFrame

from ....services import build_tmg_excel , build_tmg_pdf

def apply_master_list_pricing(products : DataFrame) -> DataFrame : 

    products['Selling Price'] = pd.to_numeric(
        products.get('Selling Price' , 0.0) , 
        errors = 'coerce'
    )

    products['Promotion Price'] = pd.to_numeric(
        products.get('Promotion Price' , 0.0) , 
        errors = 'coerce'
    )

    if 'df' in st.session_state and not st.session_state.df.is_empty() : 

        master_df : pd.DataFrame = st.session_state.df.to_pandas()

        if 'Product Name' in master_df.columns and 'Selling Price' in master_df.columns : 
            
            lookup : pd.DataFrame = master_df[[
                'Product Name' , 
                'Selling Price' , 
                'Promotion Price'
            ]].drop_duplicates(
                subset = ['Product Name'] , 
                keep = 'last'
            )

            products = products.merge(
                lookup , 
                on = 'Product Name' , 
                how = 'left' , 
                suffixes = ('' , '_master')
            )

            products['Selling Price'] = products['Selling Price'].replace(
                0.0 , np.nan
            ).fillna(products['Selling Price_master']
            ).fillna(0.0)
            
            products['Promotion Price'] = products['Promotion Price'].replace(
                0.0 , np.nan
            ).fillna(products['Promotion Price_master']
            ).fillna(0.0)

    return products

def calculate_financial_metrics(products : DataFrame) -> DataFrame : 

    products['Total Ordered Qty'] = pd.to_numeric(
        products.get('Total Ordered Qty' , 0.0) , 
        errors = 'coerce'
    )

    products['Total Cost WGST'] = pd.to_numeric(
        products.get('Total Cost WGST' , 0.0) , 
        errors = 'coerce'
    )

    products['Total Selling Base'] = products['Selling Price'] * products['Total Ordered Qty']
    products['Total Selling Promotion'] = products['Promotion Price'] * products['Total Ordered Qty']

    products['Profit'] = products['Total Selling Base'] - products['Total Cost WGST']
    products['Profit after discount'] = products['Total Selling Promotion'] - products['Total Cost WGST']

    products['Profit Margin (Percentage)'] = np.where(
        products['Total Selling Base'] > 0 , 
        (products['Profit'] / products['Total Selling Base']) * 100 , 
        np.where(products['Total Cost WGST'] > 0 , -100.0 , 0.0)
    )
    
    products['Profit Margin after discount (Percentage)'] = np.where(
        products['Total Selling Promotion'] > 0 , 
        (products['Profit after discount'] / products['Total Selling Promotion']) * 100 , 
        np.where(products['Total Cost WGST'] > 0 , -100.0 , 0.0)
    )

    return products

def render_financial_summary(products : DataFrame) -> None : 

    gst_rate : float = products['GST'].iloc[0] if 'GST' in products.columns and not products.empty else 0.0
    gst_label : str = f'{int(gst_rate)}%' if gst_rate == int(gst_rate) else f'{gst_rate}%'

    raw_sum : float = products['Total WOGST'].sum() if 'Total WOGST' in products.columns else 0.0
    wgst_sum : float = products['Total Cost WGST'].sum()
    gst_amt : float = wgst_sum - raw_sum  

    sell_base_sum : float = products['Total Selling Base'].sum()
    sell_promo_sum : float = products['Total Selling Promotion'].sum()
    
    base_profit_sum : float = products['Profit'].sum()
    promo_profit_sum : float = products['Profit after discount'].sum()

    base_margin_overall : float = (base_profit_sum / sell_base_sum * 100) if sell_base_sum > 0 else 0.0
    promo_margin_overall : float = (promo_profit_sum / sell_promo_sum * 100) if sell_promo_sum > 0 else 0.0

    c1 , c2 , c3 , c4 = st.columns(4)

    with c1 : 

        st.write('**Cost (W/O GST)**')
        st.write(f'Sub Total : ${raw_sum:,.2f}')
        st.write(f'Total : ${raw_sum:,.2f}')

    with c2 : 

        st.write(f'**Cost ({gst_label} GST)**')
        st.write(f'Total Cost : ${raw_sum:,.2f}')
        st.write(f'GST : ${gst_amt:,.2f}')
        st.write(f'**TOTAL : ${wgst_sum:,.2f}**')

    with c3 : 

        st.write('**Base Profit**')
        st.write(f'Total Selling : ${sell_base_sum:,.2f}')
        st.write(f'Total Profit : ${base_profit_sum:,.2f}')
        st.write(f'**Margin : {base_margin_overall:.2f}%**')

    with c4 : 
        
        st.write('**Discount Profit**')
        st.write(f'Promo Selling : ${sell_promo_sum:,.2f}')
        st.write(f'Total Profit : ${promo_profit_sum:,.2f}')
        st.write(f'**Margin : {promo_margin_overall:.2f}%**')

def render_export_options(
    purchase : dict , 
    products : DataFrame , 
    po_num : str
) -> None : 

    st.markdown('---')
    st.markdown('#### 📥 Download Options')

    dc1 , dc2 , dc3 , dc4 = st.columns(4)

    inc_wogst : bool = dc1.checkbox(
        'Include W/O GST' , 
        value = True , 
        key = f'wogst_{po_num}'
    )
    inc_wgst : bool = dc2.checkbox(
        'Include W/ GST' ,  
        value = True , 
        key = f'wgst_{po_num}'
    )
    inc_base : bool = dc3.checkbox(
        'Include Base Profit' , 
        value = True , 
        key = f'base_{po_num}'
    )
    inc_promo : bool = dc4.checkbox(
        'Include Discount Profit' , 
        value = True , 
        key = f'promo_{po_num}'
    )

    st.markdown('**📊 Export Data :**')

    ex1 , ex2 = st.columns(2)

    with ex1 : 

        st.download_button(
            '📊 Download Custom Excel' , 
            data = build_tmg_excel(
                purchase['Supplier'] , 
                purchase['date'] , 
                po_num , 
                products , 
                inc_wogst , 
                inc_wgst , 
                inc_base , 
                inc_promo
            ) , 
            file_name = f'PO_{po_num}_Custom.xlsx' , 
            key = f'ex_custom_{po_num}' , 
            use_container_width = True
        )
        
    with ex2 : 

        st.download_button(
            '📄 Download Custom PDF' , 
            data = build_tmg_pdf(
                purchase['Supplier'] , 
                purchase['date'] , 
                po_num , 
                products , 
                inc_wogst , 
                inc_wgst , 
                inc_base , 
                inc_promo
            ) , 
            file_name = f'PO_{po_num}_Custom.pdf' , 
            key = f'pdf_custom_{po_num}' , 
            use_container_width = True
        )

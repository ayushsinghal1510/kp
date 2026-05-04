import os
import time
import streamlit as st
import polars as pl
import pandas as pd
import numpy as np
import re
from typing import Any

from rpoc.services import (
    process_document_with_llm , 
    get_display_df
)

def sanitize_text_col(
    df : pl.DataFrame , 
    col : str
) -> pl.DataFrame : 
    return df.with_columns(
        pl.col(col)
        .map_elements(
            lambda x : re.sub(
                r'[^a-z0-9\(\)\[\] ]' , 
                '' , 
                x.lower()
            ).strip() if isinstance(x , str) else x , 
            return_dtype = pl.Utf8
        )
        .alias(col)
    )

def safe_extract_price(
    val : Any
) -> float | None : 

    if pd.isna(val) : 
        return None

    if isinstance(val , (int , float)) : 
        return float(val)

    val_str : str = str(val).strip()

    price_match : re.Match | None = re.search(
        r'\$\s*(\d+\.\d+|\d+)' , 
        val_str
    )

    if price_match : 
        return float(price_match.group(1))

    try : 
        return float(val_str)
    except ValueError : 
        return None

def sanitize_dataframe_for_polars(
    df : pd.DataFrame , 
    root_cols : list[str]
) -> pd.DataFrame : 

    for col in root_cols : 
        if col not in df.columns : 
            df[col] = None

    string_columns : list[str] = [
        'Barcode' , 
        'Product Name' , 
        'Pack Price Currency' , 
        'Supplier' , 
        'Other' , 
        'Filename' , 
        'Redundant' , 
        'Previous'
    ]

    numeric_columns : list[str] = [
        'Packing Size' , 
        'Previous Price' , 
        'Pack Price' , 
        'GST' , 
        'TMG Selling Price' , 
        'TMG Promotion Price'
    ]

    for col in string_columns : 
        if col in df.columns : 
            df[col] = df[col].astype(str).replace(
                'nan' , 
                None
            )

    for col in numeric_columns : 
        if col in df.columns : 
            df[col] = df[col].apply(safe_extract_price)

    return df[root_cols]

def normalize_string(
    text : Any
) -> str | None : 

    if pd.isna(text) : 
        return None

    val_str : str = str(text)
    
    if val_str.lower() == 'nan' or not val_str.strip() : 
        return None

    normalized : str = re.sub(
        r'[^a-z0-9\(\)\[\] ]' , 
        '' , 
        val_str.lower()
    ).strip()

    return normalized if normalized else None

def process_uploaded_excel(
    uploaded_file : Any
) -> tuple[pd.DataFrame , str] : 

    raw : pd.DataFrame = pd.read_excel(
        uploaded_file , 
        header = None
    )
    
    try : 
        supplier_cell : str = str(raw.iloc[2 , 1])
        if supplier_cell == 'nan' : 
            supplier_cell = str(raw.iloc[3 , 1])
            
        raw_supplier : str = supplier_cell.split(
            ':' , 
            1
        )[1].strip() if ':' in supplier_cell else supplier_cell.strip()
        
        if not raw_supplier or raw_supplier.lower() == 'nan' : 
            raw_supplier = 'unknown'
            
    except Exception : 
        raw_supplier = 'unknown'

    supplier : str = normalize_string(raw_supplier) or 'unknown'

    price_data : pd.DataFrame = pd.read_excel(
        uploaded_file , 
        header = 5
    )
    
    unnamed_cols : list[str] = [
        c for c in price_data.columns 
        if str(c).startswith('Unnamed:')
    ]
    
    price_data.drop(
        columns = unnamed_cols , 
        inplace = True , 
        errors = 'ignore'
    )
    
    price_data.dropna(
        how = 'all' , 
        inplace = True
    )

    def safe_get(
        df : pd.DataFrame , 
        col : str
    ) -> pd.Series | float : 
        return df[col] if col in df.columns else np.nan

    out : pd.DataFrame = pd.DataFrame()
    
    raw_product_names : pd.Series = safe_get(
        price_data , 
        'Product Name'
    )
    
    out['Product Name'] = raw_product_names.apply(normalize_string)
    
    out['Packing Size'] = safe_get(
        price_data , 
        'Packing Size\n(PC)'
    )
    out['Pack Price'] = safe_get(
        price_data , 
        'Ctn Price\n(SGD)\n(W/O GST)'
    )
    out['TMG Selling Price'] = safe_get(
        price_data , 
        'TMG Selling Price'
    )
    out['TMG Promotion Price'] = safe_get(
        price_data , 
        'TMG\nPromotion\nPrice'
    )
    out['Supplier'] = supplier
    
    out['Pack Price Currency'] = 'SGD'

    out.dropna(
        subset = ['Product Name'] , 
        inplace = True
    )
    out.reset_index(
        drop = True , 
        inplace = True
    )
    
    return out , supplier


# --- CONFIGURATION ---
ROOT_CSV_COLUMNS : list[str] = [
    'Barcode' , 
    'Product Name' , 
    'Packing Size' , 
    'Previous Price' , 
    'Pack Price' , 
    'Pack Price Currency' , 
    'GST' , 
    'Supplier' , 
    'TMG Selling Price' , 
    'TMG Promotion Price' , 
    'Other' , 
    'Filename' , 
    'Redundant' , 
    'Previous'
]

if 'pending_po_data' not in st.session_state : 
    st.session_state.pending_po_data = []

st.header(st.session_state.master_list_config['header'])

col_excel , col_po = st.columns(2)

with col_excel : 

    st.subheader('Upload TMG Aggregated Price')
    
    excel_files : list | None = st.file_uploader(
        'Upload Excel Pricing (Direct DB)' , 
        type = [
            'xlsx' , 
            'xls'
        ] , 
        accept_multiple_files = True , 
        key = 'master_excel_upload'
    )

    if st.button('Process & Import Excel') and excel_files : 
        
        existing_df : pd.DataFrame = st.session_state.df.to_pandas()

        for file in excel_files : 
            
            try : 
                
                new_rows , supplier_name = process_uploaded_excel(file)
                
                if existing_df.empty : 
                    
                    if 'Pack Price' in new_rows.columns : 
                        new_rows['Previous Price'] = new_rows['Pack Price']
                        
                    if 'TMG Promotion Price' in new_rows.columns : 
                        new_rows['TMG Promotion Price'] = new_rows['TMG Promotion Price'].fillna(new_rows['TMG Selling Price'])
                    else : 
                        new_rows['TMG Promotion Price'] = new_rows['TMG Selling Price']
                        
                    existing_df = new_rows
                    
                else : 
                    
                    existing_df['_key'] = existing_df['Product Name'].str.lower().str.strip() + '|' + existing_df['Supplier'].fillna('').str.lower().str.strip()
                    new_rows['_key'] = new_rows['Product Name'].str.lower().str.strip() + '|' + new_rows['Supplier'].fillna('').str.lower().str.strip()

                    for _ , nr in new_rows.iterrows() : 
                        key : str = nr['_key']
                        mask : pd.Series = existing_df['_key'] == key

                        if mask.any() : 
                            
                            if 'Pack Price' in existing_df.columns : 
                                old_price : float = existing_df.loc[mask , 'Pack Price'].values[0]
                                existing_df.loc[mask , 'Previous Price'] = old_price
                            
                            update_cols : list[str] = [
                                'Pack Price' , 
                                'TMG Selling Price' , 
                                'TMG Promotion Price' , 
                                'Pack Price Currency'
                            ]
                            
                            for col in update_cols : 
                                if col in nr.index and not pd.isna(nr[col]) : 
                                    existing_df.loc[mask , col] = nr[col]
                                    
                            current_promo : Any = existing_df.loc[mask , 'TMG Promotion Price'].values[0]
                            current_selling : Any = existing_df.loc[mask , 'TMG Selling Price'].values[0]
                            
                            if pd.isna(current_promo) or current_promo == 0.0 or str(current_promo).lower() == 'nan' : 
                                existing_df.loc[mask , 'TMG Promotion Price'] = current_selling
                                
                        else : 
                            
                            nr_dict : dict = nr.to_dict()
                            
                            if 'Pack Price' in nr_dict : 
                                nr_dict['Previous Price'] = nr_dict['Pack Price']
                                
                            promo_val : Any = nr_dict.get('TMG Promotion Price' , np.nan)
                            if pd.isna(promo_val) or promo_val == 0.0 or str(promo_val).lower() == 'nan' : 
                                nr_dict['TMG Promotion Price'] = nr_dict.get('TMG Selling Price' , np.nan)
                                
                            existing_df = pd.concat(
                                [
                                    existing_df , 
                                    pd.DataFrame([nr_dict])
                                ] , 
                                ignore_index = True
                            )

                    existing_df.drop(
                        columns = ['_key'] , 
                        inplace = True , 
                        errors = 'ignore'
                    )
                    
                st.success(f'Imported Excel: {file.name}')
                
            except Exception as e : 
                st.error(f'Error on {file.name} : {e}')

        existing_df = sanitize_dataframe_for_polars(
            existing_df , 
            ROOT_CSV_COLUMNS
        )
                
        st.session_state.df = pl.from_pandas(existing_df)
        st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])
        st.rerun()

with col_po : 

    st.subheader('Upload Purchase Order')
    
    po_files : list | None = st.file_uploader(
        'Upload Purchase Order (LLM)' , 
        accept_multiple_files = True , 
        key = 'po_upload'
    )

    if st.button('Extract PO with LLM') and po_files : 
        
        all_new_data : list[dict] = []
        
        for file in po_files : 
            
            extracted_data : list[dict] = process_document_with_llm(
                file , 
                st.session_state.prompts['ingestion'] , 
                st.session_state.gemini_client
            )
            
            for row in extracted_data : 
                row['Filename'] = file.name
                
            all_new_data.extend(extracted_data)
            
        st.session_state.pending_po_data = all_new_data

if st.session_state.pending_po_data : 

    st.markdown('---')
    st.subheader('Review & Approve PO Products')
    
    pending_df : pd.DataFrame = pd.DataFrame(st.session_state.pending_po_data)
    
    if 'Packing Size' not in pending_df.columns : 
        pending_df['Packing Size'] = 1

    pending_df['Packing Size'] = pending_df['Packing Size'].replace(
        0 , 
        1
    ).fillna(1)
    
    if 'Pack Price' not in pending_df.columns : 
        pending_df['Pack Price'] = 0.0

    pending_df.rename(
        columns = {
            'Packing Size' : 'Incoming Packing Size' , 
            'Pack Price' : 'Incoming Packing Price'
        } , 
        inplace = True
    )

    master_df_pd : pd.DataFrame = st.session_state.df.to_pandas()
    
    if not master_df_pd.empty : 
        
        master_subset : pd.DataFrame = master_df_pd[[
            'Product Name' , 
            'Supplier' , 
            'Packing Size' , 
            'Pack Price'
        ]].copy()
        
        master_subset.rename(
            columns = {
                'Packing Size' : 'Current Packing Size' , 
                'Pack Price' : 'Current Packing Price'
            } , 
            inplace = True
        )

        pending_df['Product Name'] = pending_df['Product Name'].apply(normalize_string)
        pending_df['Supplier'] = pending_df['Supplier'].apply(normalize_string)
        
        master_subset['Product Name'] = master_subset['Product Name'].apply(normalize_string)
        master_subset['Supplier'] = master_subset['Supplier'].apply(normalize_string)
        
        merged_df : pd.DataFrame = pending_df.merge(
            master_subset , 
            on = [
                'Product Name' , 
                'Supplier'
            ] , 
            how = 'left'
        )

    else : 
        
        merged_df : pd.DataFrame = pending_df.copy()
        merged_df['Current Packing Size'] = np.nan
        merged_df['Current Packing Price'] = np.nan

    merged_df['Current Packing Size'] = merged_df['Current Packing Size'].fillna(0)
    merged_df['Current Packing Price'] = merged_df['Current Packing Price'].fillna(0.0)

    merged_df['Incoming Unit Price'] = merged_df['Incoming Packing Price'] / merged_df['Incoming Packing Size']
    
    merged_df['Current Unit Price'] = np.where(
        merged_df['Current Packing Size'] > 0 , 
        merged_df['Current Packing Price'] / merged_df['Current Packing Size'] , 
        0.0
    )
    
    select_all : bool = st.checkbox('Select All Products')
    
    merged_df.insert(
        0 , 
        'Approve' , 
        select_all
    )
    
    display_cols : list[str] = [
        'Approve' , 
        'Product Name' , 
        'Supplier' , 
        'Current Packing Size' , 
        'Incoming Packing Size' , 
        'Current Packing Price' , 
        'Incoming Packing Price' , 
        'Current Unit Price' , 
        'Incoming Unit Price'
    ]
    
    for c in display_cols : 
        if c not in merged_df.columns : 
            merged_df[c] = None

    edited_pending_df : pd.DataFrame = st.data_editor(
        merged_df[display_cols] , 
        use_container_width = True , 
        num_rows = 'dynamic'
    )
    
    if st.button('Confirm Approved Rows') : 
        
        approved_df : pd.DataFrame = edited_pending_df[edited_pending_df['Approve'] == True].copy()
        
        if not approved_df.empty : 
            
            approved_df.drop(
                columns = [
                    'Approve' , 
                    'Current Packing Size' , 
                    'Current Packing Price' , 
                    'Current Unit Price' , 
                    'Incoming Unit Price'
                ] , 
                inplace = True , 
                errors = 'ignore'
            )
            
            approved_df.rename(
                columns = {
                    'Incoming Packing Size' : 'Packing Size' , 
                    'Incoming Packing Price' : 'Pack Price'
                } , 
                inplace = True
            )
            
            master_pl_df : pl.DataFrame = st.session_state.df

            approved_df = sanitize_dataframe_for_polars(
                approved_df , 
                ROOT_CSV_COLUMNS
            )
            
            new_pl_df : pl.DataFrame = pl.from_pandas(approved_df)
            
            standard_cols : list[str] = [
                c for c in ROOT_CSV_COLUMNS 
                if c not in [
                    'Previous Price' , 
                    'TMG Promotion Price' , 
                    'Pack Price Currency' , 
                    'Product Name' , 
                    'Supplier'
                ]
            ]
            
            coalesce_exprs : list[pl.Expr] = [
                pl.coalesce(
                    pl.col(f'{c}_new') , 
                    pl.col(c)
                ).alias(c)
                for c in standard_cols
            ]
            
            special_exprs : list[pl.Expr] = [
                pl.when(pl.col('Pack Price_new').is_not_null())
                .then(pl.col('Pack Price'))
                .otherwise(pl.col('Previous Price')).alias('Previous Price') , 
                
                pl.when(
                    pl.col('TMG Promotion Price_new').cast(
                        pl.Float64 , 
                        strict = False
                    ).fill_null(0.0) == 0.0
                )
                .then(
                    pl.coalesce(
                        pl.col('TMG Selling Price_new') , 
                        pl.col('TMG Selling Price')
                    )
                )
                .otherwise(
                    pl.coalesce(
                        pl.col('TMG Promotion Price_new') , 
                        pl.col('TMG Promotion Price')
                    )
                ).alias('TMG Promotion Price') , 
                
                pl.lit('SGD').alias('Pack Price Currency')
            ]
            
            updated_df : pl.DataFrame = master_pl_df.join(
                new_pl_df , 
                on = [
                    'Product Name' , 
                    'Supplier'
                ] , 
                how = 'left' , 
                suffix = '_new'
            ).with_columns(
                special_exprs + coalesce_exprs
            ).select(ROOT_CSV_COLUMNS)
            
            new_rows : pl.DataFrame = new_pl_df.join(
                master_pl_df , 
                on = [
                    'Product Name' , 
                    'Supplier'
                ] , 
                how = 'anti'
            ).with_columns(
                [
                    pl.col('Pack Price').alias('Previous Price') , 
                    
                    pl.when(
                        pl.col('TMG Promotion Price').cast(
                            pl.Float64 , 
                            strict = False
                        ).fill_null(0.0) == 0.0
                    )
                    .then(pl.col('TMG Selling Price'))
                    .otherwise(pl.col('TMG Promotion Price')).alias('TMG Promotion Price') , 
                    
                    pl.lit('SGD').alias('Pack Price Currency')
                ]
            ).select(ROOT_CSV_COLUMNS)
            
            st.session_state.df = pl.concat(
                [
                    updated_df , 
                    new_rows
                ] , 
                how = 'diagonal'
            )
            
            st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])
            
            st.session_state.pending_po_data = []
            
            st.success('Master list updated successfully with approved products!')
            time.sleep(1)
            st.rerun()

        else : 
            
            st.warning('No valid rows were selected for approval.')
st.markdown('---')

if not st.session_state.df.is_empty() : 
    
    display_df : pl.DataFrame = get_display_df(st.session_state.df)
    
    pandas_display_df : pd.DataFrame = display_df.to_pandas()
    pandas_display_df.index = pandas_display_df.index + 1

    edit_mode : bool = st.toggle('Enable Edit Mode')

    if edit_mode : 
        
        edited_df : pd.DataFrame = st.data_editor(
            pandas_display_df , 
            use_container_width = True , 
            num_rows = 'dynamic'
        )

        if st.button('Save Changes') : 
            
            temp_pl_df : pl.DataFrame = pl.from_pandas(edited_df)
            
            rename_map : dict[str , str] = {
                'Packing Price WOGST' : 'Pack Price' , 
                'Packing Price Currency' : 'Pack Price Currency'
            }
            
            for old_name , new_name in rename_map.items() : 
                if old_name in temp_pl_df.columns : 
                    temp_pl_df = temp_pl_df.rename(
                        {
                            old_name : new_name
                        }
                    )
            
            valid_edited_cols : list[str] = [
                col for col in temp_pl_df.columns 
                if col in ROOT_CSV_COLUMNS
            ]
            
            temp_pl_df = temp_pl_df.select(valid_edited_cols)
            
            original_df : pl.DataFrame = st.session_state.df
            
            missing_root_cols : list[str] = [
                col for col in ROOT_CSV_COLUMNS 
                if col not in valid_edited_cols and col in original_df.columns
            ]
            
            recovery_df : pl.DataFrame = original_df.select(
                missing_root_cols + [
                    'Product Name' , 
                    'Supplier'
                ]
            )
            
            final_save_df : pl.DataFrame = temp_pl_df.join(
                recovery_df , 
                on = [
                    'Product Name' , 
                    'Supplier'
                ] , 
                how = 'left'
            )
            
            final_ordered_cols : list[str] = [
                col for col in ROOT_CSV_COLUMNS 
                if col in final_save_df.columns
            ]
            
            final_save_df = final_save_df.select(final_ordered_cols)
            
            st.session_state.df = final_save_df
            st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])
            
            st.success('Master list updated successfully!')
            time.sleep(1)
            st.rerun()

    else : 

        st.dataframe(
            pandas_display_df , 
            use_container_width = True
        )
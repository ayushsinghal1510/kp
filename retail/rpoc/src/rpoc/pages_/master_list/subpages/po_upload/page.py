import time

import numpy as np
import pandas as pd
import polars as pl
import streamlit as st

from typing import Any

from .services_ import process_document_with_llm , suggest_master_matches
from ..services_ import sanitize_dataframe_for_polars , normalize_string , save_uploaded_file


def handle_po_upload_section(
    col : Any
) -> None : 

    with col :

        st.subheader('Upload Purchase Order')

        mode : str = st.radio(
            'PO Upload Mode' ,
            [
                'Upload New Invoice' ,
                'Update Existing Invoice'
            ] ,
            horizontal = True ,
            key = 'po_upload_mode'
        )

        selected_supplier : str | None = None

        if mode == 'Update Existing Invoice' :

            supplier_options : list[str] = sorted(
                s for s in st.session_state.df.drop_nulls(
                    subset = ['Supplier']
                )['Supplier'].unique().to_list()
                if isinstance(s , str) and s.strip()
            )

            if not supplier_options :

                st.info('No suppliers found in the master list yet. Use "Upload New Invoice" instead.')

            else :

                selected_supplier = st.selectbox(
                    'Supplier' ,
                    supplier_options ,
                    key = 'po_upload_supplier'
                )

        po_files : list[Any] | None = st.file_uploader(
            'Upload Purchase Order (LLM)' ,
            accept_multiple_files = True ,
            key = 'po_upload'
        )

        extract_clicked : bool = st.button('Extract PO with LLM')

        if extract_clicked and mode == 'Update Existing Invoice' and not selected_supplier :

            st.warning('Select a supplier first.')

        elif extract_clicked and po_files :

            all_new_data : list[dict[str , Any]] = []
            total_files : int = len(po_files)

            progress_bar : Any = st.progress(
                0 ,
                text = 'Starting PO processing...'
            )

            for idx , file in enumerate(po_files) :

                save_uploaded_file(file)

                extracted_data : list[dict[str , Any]] = process_document_with_llm(
                    file ,
                    st.session_state.prompts['ingestion'] ,
                    st.session_state.openrouter_client ,
                    selected_supplier ,
                    st.session_state.df
                )

                for row in extracted_data :

                    row['Filename'] = file.name

                    if mode == 'Update Existing Invoice' and selected_supplier :
                        row['Supplier'] = selected_supplier

                all_new_data.extend(extracted_data)
                
                current_step : int = idx + 1
                progress_percentage : float = current_step / total_files
                
                progress_bar.progress(
                    progress_percentage , 
                    text = f'Processed {current_step} of {total_files} POs'
                )
                
            st.session_state.pending_po_data = all_new_data
            progress_bar.empty()


def handle_po_approval_section() -> None : 

    st.markdown('---')
    st.subheader('Review & Approve PO Products')
    
    pending_df : pd.DataFrame = pd.DataFrame(
        st.session_state.pending_po_data
    )

    if pending_df.empty : 
        
        return
    
    pending_df['Original Order'] = range(len(pending_df))

    pending_df['Product Name'] = pending_df['Product Name'].astype(str).str.replace(
        r'\s+' , 
        ' ' , 
        regex = True
    ).str.strip()
    
    pending_df['Supplier'] = pending_df['Supplier'].astype(str).str.replace(
        r'\s+' , 
        ' ' , 
        regex = True
    ).str.strip()
    
    pending_df['Match Product Name'] = pending_df['Product Name'].apply(
        normalize_string
    ).str.lower()
    
    pending_df['Match Supplier'] = pending_df['Supplier'].apply(
        normalize_string
    ).str.lower()
    
    if 'Pack Price' not in pending_df.columns : 
        pending_df['Pack Price'] = 0.0
    else :
        pending_df['Pack Price'] = pd.to_numeric(
            pending_df['Pack Price'] , 
            errors = 'coerce'
        ).fillna(0.0)

    pending_df.sort_values(
        by = ['Match Product Name' , 'Match Supplier' , 'Pack Price'] , 
        ascending = [True , True , False] , 
        inplace = True
    )
    
    pending_df.drop_duplicates(
        subset = ['Match Product Name' , 'Match Supplier'] , 
        keep = 'first' , 
        inplace = True
    )

    pending_df.sort_values(
        by = ['Original Order'] , 
        ascending = True , 
        inplace = True
    )
    
    pending_df.drop(
        columns = ['Original Order'] , 
        inplace = True
    )

    # * Suggest which existing master product each invoice line is (barcode ->
    # * same name -> close name + packing size + price). The user confirms or
    # * changes it in the 'Match To' column ; current prices are looked up by it.
    pending_df['Match To'] = suggest_master_matches(
        pending_df.to_dict('records') ,
        st.session_state.df
    )

    # * Re-apply 'Match To' picks the user already made in the editor so the
    # * Current price columns follow a manual pick on the next rerun.
    editor_state : Any = st.session_state.get('po_approval_editor')

    if isinstance(editor_state , dict) :

        for row_pos , changes in editor_state.get('edited_rows' , {}).items() :

            if 'Match To' in changes and int(row_pos) < len(pending_df) :

                pending_df.iloc[
                    int(row_pos) ,
                    pending_df.columns.get_loc('Match To')
                ] = changes['Match To'] or ''

    pending_df['Match Product Name'] = pd.Series(
        np.where(
            pending_df['Match To'] != '' ,
            pending_df['Match To'] ,
            pending_df['Product Name']
        ) ,
        index = pending_df.index
    ).astype(str).str.replace(r'\s+' , ' ' , regex = True).str.strip().str.lower()

    for carry_col in ['Barcode' , 'Filename'] :

        if carry_col not in pending_df.columns :
            pending_df[carry_col] = ''

    if 'Packing Size' not in pending_df.columns : 
        
        pending_df['Packing Size'] = 1

    pending_df['Packing Size'] = pending_df['Packing Size'].replace(
        0 , 
        1
    ).fillna(1)
    
    if 'Selling Price' not in pending_df.columns : 
        
        pending_df['Selling Price'] = 0.0

    pending_df.rename(
        columns = {
            'Packing Size' : 'Incoming Packing Size' , 
            'Pack Price' : 'Incoming Packing Price' , 
            'Selling Price' : 'Incoming Selling Price'
        } , 
        inplace = True
    )

    master_df_pd : pd.DataFrame = st.session_state.df.to_pandas()

    if not master_df_pd.empty : 

        master_subset : pd.DataFrame = master_df_pd[[
            'Product Name' , 
            'Supplier' , 
            'Packing Size' , 
            'Pack Price' , 
            'Selling Price'
        ]].copy()
        
        master_subset.rename(
            columns = {
                'Packing Size' : 'Current Packing Size' , 
                'Pack Price' : 'Current Packing Price' , 
                'Selling Price' : 'Current Selling Price'
            } , 
            inplace = True
        )
        
        master_subset['Match Product Name'] = master_subset['Product Name'].apply(
            normalize_string
        ).str.replace(r'\s+', ' ', regex=True).str.strip().str.lower()
        
        master_subset['Match Supplier'] = master_subset['Supplier'].apply(
            normalize_string
        ).str.replace(r'\s+', ' ', regex=True).str.strip().str.lower()
        
        master_subset.drop(columns=['Product Name', 'Supplier'], inplace=True)
        
        merged_df : pd.DataFrame = pending_df.merge(
            master_subset , 
            on = [
                'Match Product Name' , 
                'Match Supplier'
            ] , 
            how = 'left'
        )

    else : 
        
        merged_df : pd.DataFrame = pending_df.copy()
        merged_df['Current Packing Size'] = np.nan
        merged_df['Current Packing Price'] = np.nan
        merged_df['Current Selling Price'] = np.nan

    merged_df['Current Packing Size'] = merged_df['Current Packing Size'].fillna(0)
    merged_df['Current Packing Price'] = merged_df['Current Packing Price'].fillna(0.0)
    merged_df['Current Selling Price'] = merged_df['Current Selling Price'].fillna(0.0)

    merged_df['Incoming Selling Price'] = np.where(
        merged_df['Incoming Selling Price'].fillna(0.0) == 0.0 , 
        merged_df['Current Selling Price'] , 
        merged_df['Incoming Selling Price']
    )

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
        'Match To' ,
        'Supplier' ,
        'Current Packing Size' , 
        'Incoming Packing Size' , 
        'Current Packing Price' , 
        'Incoming Packing Price' , 
        'Current Unit Price' , 
        'Incoming Unit Price' , 
        'Current Selling Price' , 
        'Incoming Selling Price'
    ]
    
    for c in display_cols : 
        
        if c not in merged_df.columns : 
            
            merged_df[c] = None

    # * Barcode / Filename ride along hidden (column_order) so they reach the commit.
    hidden_cols : list[str] = ['Barcode' , 'Filename']

    pending_suppliers : set[str] = set(merged_df['Supplier'].astype(str).str.strip().str.lower())

    match_options : list[str] = [''] + sorted(
        str(name) for name , sup in zip(
            st.session_state.df['Product Name'].to_list() ,
            st.session_state.df['Supplier'].to_list()
        )
        if name is not None and str(sup).strip().lower() in pending_suppliers
    )

    styled_merged_df : Any = merged_df[display_cols + hidden_cols].style.map(
        lambda _ : 'background-color : #6496fa26' , 
        subset = [
            'Current Packing Size' , 
            'Incoming Packing Size'
        ]
    ).map(
        lambda _ : 'background-color : #64c86426' , 
        subset = [
            'Current Packing Price' , 
            'Incoming Packing Price'
        ]
    ).map(
        lambda _ : 'background-color : #fa963226' , 
        subset = [
            'Current Unit Price' , 
            'Incoming Unit Price'
        ]
    ).map(
        lambda _ : 'background-color : #9664fa26' , 
        subset = [
            'Current Selling Price' , 
            'Incoming Selling Price'
        ]
    )

    st.caption(
        '**Match To** = the existing master product this invoice line updates '
        '(auto-suggested ; pick another or clear it to add the line as a new product).'
    )

    edited_pending_df : pd.DataFrame = st.data_editor(
        styled_merged_df ,
        use_container_width = True ,
        num_rows = 'dynamic' ,
        key = 'po_approval_editor' ,
        column_order = display_cols ,
        column_config = {
            'Match To' : st.column_config.SelectboxColumn(
                'Match To' ,
                options = match_options ,
                help = 'Existing product this line updates. Blank = add as new product.'
            )
        }
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
                    'Incoming Unit Price' , 
                    'Current Selling Price'
                ] , 
                inplace = True , 
                errors = 'ignore'
            )
            
            approved_df.rename(
                columns = {
                    'Incoming Packing Size' : 'Packing Size' , 
                    'Incoming Packing Price' : 'Pack Price' , 
                    'Incoming Selling Price' : 'Selling Price'
                } , 
                inplace = True
            )

            # * A confirmed 'Match To' makes this line update that existing master
            # * row (its name is kept) instead of being added as a new product.
            match_to : pd.Series = approved_df['Match To'].fillna('').astype(str).str.strip()

            approved_df['Product Name'] = np.where(
                match_to != '' ,
                match_to ,
                approved_df['Product Name']
            )

            approved_df.drop(
                columns = ['Match To'] ,
                inplace = True
            )

            # * Empty barcode must not blank out an existing one in the coalesce below.
            approved_df['Barcode'] = approved_df['Barcode'].replace('' , None)

            approved_df['Match Product Name'] = approved_df['Product Name'].astype(str).str.replace(r'\s+' , ' ' , regex = True).str.strip().str.lower()
            approved_df['Match Supplier'] = approved_df['Supplier'].astype(str).str.replace(r'\s+' , ' ' , regex = True).str.strip().str.lower()

            duplicate_mask : pd.Series = approved_df.duplicated(
                subset = ['Match Product Name' , 'Match Supplier'] ,
                keep = 'first'
            )

            if duplicate_mask.any() :

                st.warning(
                    'These lines point at the same product as an earlier line and were skipped : '
                    + ' , '.join(approved_df.loc[duplicate_mask , 'Product Name'].astype(str))
                )

                approved_df = approved_df[~duplicate_mask]

            approved_df['Discount'] = 0.0

            master_pl_df : pl.DataFrame = st.session_state.df

            new_pl_df : pl.DataFrame = pl.from_pandas(approved_df)
            
            new_pl_df = sanitize_dataframe_for_polars(
                new_pl_df , 
                st.session_state.root_csv_columns
            )

            for col_name , col_type in master_pl_df.schema.items() : 
                
                if col_name in new_pl_df.columns : 
                    
                    new_pl_df = new_pl_df.with_columns(
                        pl.col(col_name).cast(
                            col_type , 
                            strict = False
                        )
                    )

            master_pl_df = master_pl_df.with_columns([
                pl.col('Product Name').str.replace_all(r'\s+' , ' ').str.strip_chars().str.to_lowercase().alias('Match Product Name'),
                pl.col('Supplier').str.replace_all(r'\s+' , ' ').str.strip_chars().str.to_lowercase().alias('Match Supplier')
            ])

            new_pl_df = new_pl_df.with_columns([
                pl.col('Product Name').str.replace_all(r'\s+' , ' ').str.strip_chars().str.to_lowercase().alias('Match Product Name'),
                pl.col('Supplier').str.replace_all(r'\s+' , ' ').str.strip_chars().str.to_lowercase().alias('Match Supplier')
            ])
            
            standard_cols : list[str] = [
                c for c in st.session_state.root_csv_columns
                if c not in [
                    'Previous Price' ,
                    'Promotion Price' ,
                    'Pack Price Currency' ,
                    'Product Name' ,
                    'Supplier' ,
                    'Match Product Name' ,
                    'Match Supplier' ,
                    'Discount' ,
                    # * Packing Size is owned by Excel ; keep the existing master
                    # * value and do not let the invoice overwrite it.
                    'Packing Size'
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
                # * Previous Price comes from invoices only. When a product still has
                # * no real invoice price (Excel-seeded, Pack Price == 0), the first
                # * invoice sets BOTH the current and previous price to the invoice
                # * value — the Excel price is never used as the previous price.
                pl.when(
                    pl.col('Pack Price_new').is_not_null()
                ).then(
                    pl.when(
                        pl.col('Pack Price').fill_null(0.0) > 0.0
                    ).then(
                        pl.col('Pack Price')
                    ).otherwise(
                        pl.col('Pack Price_new')
                    )
                ).otherwise(
                    pl.col('Previous Price')
                ).alias('Previous Price') ,
                
                pl.when(
                    pl.col('Promotion Price_new').cast(
                        pl.Float64 , 
                        strict = False
                    ).fill_null(0.0) == 0.0
                ).then(
                    pl.coalesce(
                        pl.col('Selling Price_new') , 
                        pl.col('Selling Price')
                    )
                ).otherwise(
                    pl.coalesce(
                        pl.col('Promotion Price_new') , 
                        pl.col('Promotion Price')
                    )
                ).alias('Promotion Price') , 
                
                pl.lit('SGD').alias('Pack Price Currency') ,
                
                pl.col('Discount').fill_null(0.0).alias('Discount')
            ]
            
            updated_df : pl.DataFrame = master_pl_df.join(
                new_pl_df , 
                on = [
                    'Match Product Name' , 
                    'Match Supplier'
                ] , 
                how = 'left' , 
                suffix = '_new'
            ).with_columns(
                special_exprs + coalesce_exprs
            ).select(st.session_state.root_csv_columns)
            
            new_rows : pl.DataFrame = new_pl_df.join(
                master_pl_df , 
                on = [
                    'Match Product Name' , 
                    'Match Supplier'
                ] , 
                how = 'anti'
            ).with_columns(
                [
                    pl.col('Pack Price').alias('Previous Price') , 
                    
                    pl.when(
                        pl.col('Promotion Price').cast(
                            pl.Float64 , 
                            strict = False
                        ).fill_null(0.0) == 0.0
                    ).then(
                        pl.col('Selling Price')
                    ).otherwise(
                        pl.col('Promotion Price')
                    ).alias('Promotion Price') , 
                    
                    pl.lit('SGD').alias('Pack Price Currency')
                ]
            ).select(st.session_state.root_csv_columns)
            
            st.session_state.df = pl.concat(
                [
                    updated_df , 
                    new_rows
                ] , 
                how = 'diagonal'
            )
            
            st.session_state.df.write_csv(
                st.session_state.config['main']['path']['csv']
            )
            
            st.session_state.pending_po_data = []
            
            st.success('Master list updated successfully with approved products!')
            
            time.sleep(1)
            
            st.rerun()

        else : 
            
            st.warning('No valid rows were selected for approval.')
import time
import numpy as np
import pandas as pd
import polars as pl
import streamlit as st 

from typing import Any

from .services_ import get_display_df

def handle_master_list_display() -> None : 

    st.markdown('---')

    if not st.session_state.df.is_empty() : 
        
        display_df : pl.DataFrame = get_display_df(
            st.session_state.df
        )
        
        pandas_display_df : pd.DataFrame = display_df.to_pandas()
        pandas_display_df.index = pandas_display_df.index + 1

        layout_cols : list[Any] = st.columns(2)
        col_edit : Any = layout_cols[0]
        col_export : Any = layout_cols[1]

        with col_edit : 
            
            edit_mode : bool = st.toggle('Enable Edit Mode')

        with col_export : 
            
            csv_export_data : bytes = pandas_display_df.to_csv(
                index = False
            ).encode('utf-8')
            
            st.download_button(
                label = '🖨️ Download / Print Master List' , 
                data = csv_export_data , 
                file_name = 'master_list_export.csv' , 
                mime = 'text/csv'
            )
        
        if edit_mode : 
            
            if 'master_list_editor' in st.session_state and st.session_state.master_list_editor.get('edited_rows') : 
                
                changes : dict[Any, Any] = st.session_state.master_list_editor['edited_rows']
                
                for row_idx_str , row_changes in changes.items() : 
                    
                    row_idx : int = int(row_idx_str) 
                    
                    for col_name , new_val in row_changes.items() : 
                        
                        col_idx : int = pandas_display_df.columns.get_loc(col_name)
                        pandas_display_df.iloc[row_idx , col_idx] = new_val
                
                pandas_display_df['UNIT PROFIT ($)'] = pandas_display_df['TMG Selling Price'] - pandas_display_df['Unit Price (SGD) (W GST)']
                
                pandas_display_df['Profit Margin - %'] = np.where(
                    pandas_display_df['TMG Selling Price'] > 0 , 
                    (pandas_display_df['UNIT PROFIT ($)'] / pandas_display_df['TMG Selling Price']) * 100 , 
                    -100.0
                )

                pandas_display_df['Promotion Profit'] = pandas_display_df['TMG Promotion Price'] - pandas_display_df['Unit Price (SGD) (W GST)']
                
                pandas_display_df['Promotion Profit Percentage'] = np.where(
                    pandas_display_df['TMG Promotion Price'] > 0 , 
                    (pandas_display_df['Promotion Profit'] / pandas_display_df['TMG Promotion Price']) * 100 , 
                    -100.0
                )

            edited_df : pd.DataFrame = st.data_editor(
                pandas_display_df , 
                use_container_width = True , 
                num_rows = 'dynamic' ,
                key = 'master_list_editor'
            )

            if st.button('Save Changes') : 
                
                temp_pl_df : pl.DataFrame = pl.from_pandas(edited_df)
                
                rename_map : dict[str , str] = {
                    'Packing Price WOGST' : 'Pack Price' , 
                    'Packing Price Currency' : 'Pack Price Currency' ,
                    'TMG Selling Price' : 'Selling Price' ,
                    'TMG Promotion Price' : 'Promotion Price' ,
                    'Packing Size (PC)' : 'Packing Size'
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
                    if col in st.session_state.root_csv_columns
                ]
                
                temp_pl_df = temp_pl_df.select(valid_edited_cols)
                
                original_df : pl.DataFrame = st.session_state.df

                for col_name , col_type in original_df.schema.items() : 
                    
                    if col_name in temp_pl_df.columns : 
                        
                        temp_pl_df = temp_pl_df.with_columns(
                            pl.col(col_name).cast(
                                col_type , 
                                strict = False
                            )
                        )
                
                missing_root_cols : list[str] = [
                    col for col in st.session_state.root_csv_columns 
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
                    col for col in st.session_state.root_csv_columns 
                    if col in final_save_df.columns
                ]
                
                final_save_df = final_save_df.select(final_ordered_cols)
                
                st.session_state.df = final_save_df
                
                st.session_state.df.write_csv(
                    st.session_state.config['main']['path']['csv']
                )
                
                st.success('Master list updated successfully!')
                
                time.sleep(1)
                
                st.rerun()

        else : 
            st.dataframe(
                pandas_display_df , 
                use_container_width = True
            )
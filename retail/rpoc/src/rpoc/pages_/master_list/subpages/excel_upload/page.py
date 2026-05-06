import polars as pl
import streamlit as st

from typing import Any 

from .services_ import process_excel_with_llm , _get_promo_price_expr
from ..services_ import sanitize_dataframe_for_polars , normalize_string , save_uploaded_file

def handle_excel_upload_section(
    col : Any
) -> None : 

    with col : 

        st.subheader('Upload TMG Aggregated Price')

        excel_files : list[Any] | None = st.file_uploader(
            'Upload Excel Pricing (Direct DB)' , 
            type = ['xlsx' , 'xls'] , 
            accept_multiple_files = True , 
            key = 'master_excel_upload'
        )

        if not st.button('Process & Import Excel') or not excel_files : 
            return

        existing_df : pl.DataFrame = st.session_state.df

        if not existing_df.is_empty() : 

            existing_norm_exprs : list[pl.Expr] = [
                pl.col(c).map_elements(
                    normalize_string , 
                    return_dtype = pl.String
                ).alias(c)
                for c in [
                    'Product Name' , 
                    'Supplier'
                ] if c in existing_df.columns
            ]

            if existing_norm_exprs : 
                existing_df = existing_df.with_columns(*existing_norm_exprs)

        for file in excel_files : 

            save_uploaded_file(
                file
            )

            try : 

                new_rows : pl.DataFrame
                exchange_rate : float
                
                new_rows , exchange_rate = process_excel_with_llm(
                    file
                )

                if new_rows.is_empty() : 
                    continue

                new_rows = new_rows.with_columns(
                    pl.lit(file.name).alias('Filename')
                )

                new_norm_exprs : list[pl.Expr] = [
                    pl.col(c).map_elements(
                        normalize_string , 
                        return_dtype = pl.String
                    ).alias(c)
                    for c in [
                        'Product Name' , 
                        'Supplier'
                    ] if c in new_rows.columns
                ]

                if new_norm_exprs : 
                    new_rows = new_rows.with_columns(*new_norm_exprs)

                numeric_cols_to_cast : list[str] = [
                    'Packing Size' , 
                    'Pack Price' , 
                    'Selling Price' , 
                    'Promotion Price' , 
                    'Previous Price'
                ]

                cast_exprs : list[pl.Expr] = [
                    pl.col(c).cast(
                        pl.Float64 , 
                        strict = False
                    ).alias(c)
                    for c in numeric_cols_to_cast if c in new_rows.columns
                ]

                if cast_exprs : 
                    new_rows = new_rows.with_columns(*cast_exprs)

                if 'Pack Price' in new_rows.columns : 
                    new_rows = new_rows.with_columns(
                        pl.col('Pack Price').alias('Previous Price')
                    )

                if 'Promotion Price' in new_rows.columns : 
                    new_rows = new_rows.with_columns(
                        _get_promo_price_expr()
                    )

                elif 'Selling Price' in new_rows.columns : 
                    new_rows = new_rows.with_columns(
                        pl.col('Selling Price').alias('Promotion Price')
                    )

                if existing_df.is_empty() : 

                    # Deduplicate the very first upload just in case
                    new_rows = new_rows.unique(
                        subset = [
                            'Product Name' , 
                            'Supplier'
                        ] , 
                        keep = 'last'
                    )

                    existing_df = new_rows
                    
                    st.success(f'Imported Excel : {file.name} with exchange rate : {exchange_rate}')
                    st.info(f'Added {new_rows.height} new rows.')

                    continue

                key_expr : pl.Expr = (
                    pl.col('Product Name').cast(
                        pl.String
                    ).str.to_lowercase().str.strip_chars() + 
                    pl.lit('|') + 
                    pl.col('Supplier').fill_null(
                        ''
                    ).cast(
                        pl.String
                    ).str.to_lowercase().str.strip_chars()
                )

                existing_df = existing_df.with_columns(
                    key_expr.alias('_key')
                )
                
                new_rows = new_rows.with_columns(
                    key_expr.alias('_key')
                )

                # --- FIX: Deduplicate incoming LLM data to prevent Cartesian joins ---
                new_rows = new_rows.unique(
                    subset = ['_key'] , 
                    keep = 'last'
                )
                # ----------------------------------------------------------------------

                existing_keys : pl.DataFrame = existing_df.select('_key')

                updates : pl.DataFrame = new_rows.join(
                    existing_keys , 
                    on = '_key' , 
                    how = 'inner'
                )

                inserts : pl.DataFrame = new_rows.join(
                    existing_keys , 
                    on = '_key' , 
                    how = 'anti'
                )

                if not updates.is_empty() : 

                    if 'Pack Price' in existing_df.columns : 
                        existing_df = existing_df.with_columns(
                            pl.when(
                                pl.col('_key').is_in(
                                    updates.get_column('_key')
                                )
                            ).then(
                                pl.col('Pack Price')
                            ).otherwise(
                                pl.col('Previous Price')
                            ).alias('Previous Price')
                        )

                    existing_df = existing_df.join(
                        updates , 
                        on = '_key' , 
                        how = 'left' , 
                        suffix = '_new'
                    )
                    
                    update_cols : list[str] = [
                        'Pack Price' , 
                        'Selling Price' , 
                        'Promotion Price' , 
                        'Pack Price Currency' , 
                        'Filename'
                    ]

                    exprs : list[pl.Expr] = [
                        pl.col(f'{c}_new').fill_null(
                            pl.col(c)
                        ).alias(c)
                        for c in update_cols if f'{c}_new' in existing_df.columns
                    ]

                    if exprs : 
                        existing_df = existing_df.with_columns(*exprs)

                    if 'Promotion Price' in existing_df.columns and 'Selling Price' in existing_df.columns : 
                        existing_df = existing_df.with_columns(
                            _get_promo_price_expr()
                        )

                    drop_cols : list[str] = [
                        c for c in existing_df.columns if c.endswith('_new')
                    ]

                    existing_df = existing_df.drop(drop_cols)

                if not inserts.is_empty() : 
                    existing_df = pl.concat(
                        [
                            existing_df , 
                            inserts
                        ] , 
                        how = 'diagonal'
                    )

                existing_df = existing_df.drop('_key')

                inserted_count : int = inserts.height
                updated_count : int = updates.height

                st.success(f'Imported Excel : {file.name} with exchange rate : {exchange_rate}')
                st.info(f'Added {inserted_count} new rows.')

                if updated_count > 0 : 
                    
                    with st.expander(f'View {updated_count} Overridden / Duplicate Rows') : 
                        
                        st.dataframe(
                            updates.drop('_key').to_pandas() , 
                            use_container_width = True
                        )

            except Exception as e : 
                st.error(f'Error on {file.name} : {e}')

        existing_df = sanitize_dataframe_for_polars(
            existing_df , 
            st.session_state.root_csv_columns
        )

        st.session_state.df = existing_df

        st.session_state.df.write_csv(
            st.session_state.config['main']['path']['csv']
        )
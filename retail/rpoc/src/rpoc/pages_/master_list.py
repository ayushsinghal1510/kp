import os
import time
import streamlit as st
import polars as pl
import pandas as pd

from rpoc.services import (
    process_document_with_llm , 
    get_display_df
)

st.header(st.session_state.master_list_config['header'])

uploaded_files : list | None = st.file_uploader(
    **st.session_state.master_list_config['upload-file']
)

if st.button('Process & Import Files') and uploaded_files : 

    all_new_data : list[dict] = []

    progress_text : str = 'Operation in progress. Please wait.'
    my_bar : st.delta_generator.DeltaGenerator = st.progress(
        0 , 
        text = progress_text
    )
    
    total_files : int = len(uploaded_files)

    for index , file in enumerate(uploaded_files) : 

        try : 

            file_path : str = os.path.join(
                st.session_state.config['main']['path']['save'] , 
                file.name
            )

            current_progress : int = int((index / total_files) * 80)
            
            my_bar.progress(
                current_progress , 
                text = f"Processing {file.name} ({index+1}/{total_files})"
            )

            with open(
                file_path , 
                'wb'
            ) as file_obj : 
                file_obj.write(file.getbuffer())

            data : list[dict] = process_document_with_llm(
                file , 
                st.session_state.prompts['ingestion'] , 
                st.session_state.gemini_client
            )

            for row in data : 
                row['Filename'] = file.name

            all_new_data.extend(data)

        except Exception as e : 
            st.error(f"Error processing {file.name} : {e}")

    if all_new_data : 

        my_bar.progress(
            85 , 
            text = 'Updating Master List'
        )
        
        new_data_df : pl.DataFrame = pl.DataFrame(all_new_data)

        sales_cols : list[str] = [
            'TMG Selling Price' , 
            'TMG Promotion Price'
        ]
        
        for col in sales_cols : 
            if col not in new_data_df.columns : 
                new_data_df = new_data_df.with_columns(pl.lit(0.0).alias(col))
            else : 
                new_data_df = new_data_df.with_columns(
                    pl.col(col).fill_null(0.0).cast(
                        pl.Float64 , 
                        strict = False
                    )
                )

        new_data_df = new_data_df.with_columns(
            pl.when(pl.col('TMG Promotion Price') == 0)
            .then(pl.col('TMG Selling Price'))
            .otherwise(pl.col('TMG Promotion Price')).alias('TMG Promotion Price')
        )

        master_df : pl.DataFrame = st.session_state.df

        if 'Previous Price' not in master_df.columns : 
            if 'Pack Price' in master_df.columns : 
                master_df = master_df.with_columns(pl.col('Pack Price').alias('Previous Price'))
            else : 
                master_df = master_df.with_columns(pl.lit(0.0).alias('Previous Price'))

        if 'Barcode' not in master_df.columns : 
            master_df = master_df.with_columns(pl.lit('').alias('Barcode'))

        if 'Barcode' not in new_data_df.columns : 
            new_data_df = new_data_df.with_columns(pl.lit('').alias('Barcode'))

        for col_name , dtype in master_df.schema.items() : 
            if col_name in new_data_df.columns : 
                new_data_df = new_data_df.with_columns(
                    pl.col(col_name).cast(
                        dtype , 
                        strict = False
                    )
                )

        standard_update_cols : list[str] = [
            c for c in st.session_state.config['main']['update-cols'] 
            if c not in [
                'Pack Price' , 
                'Previous Price' , 
                'Barcode'
            ]
        ]

        updated_df : pl.DataFrame = master_df.join(
            new_data_df , 
            on = [
                'Product Name' , 
                'Supplier'
            ] , 
            how = 'left' , 
            suffix = '_new'
        ).with_columns(
            [
                pl.when(pl.col('Pack Price_new').is_not_null())
                .then(pl.col('Pack Price'))
                .otherwise(pl.col('Previous Price')).alias('Previous Price') , 

                pl.coalesce(
                    pl.col('Pack Price_new') , 
                    pl.col('Pack Price')
                ).alias('Pack Price') , 

                pl.coalesce(
                    pl.col('Barcode_new') , 
                    pl.col('Barcode')
                ).alias('Barcode')
            ] + [
                pl.coalesce(
                    pl.col(f"{c}_new") , 
                    pl.col(c)
                ).alias(c)

                for c in standard_update_cols
            ]
        ).select(master_df.columns)

        new_rows : pl.DataFrame = new_data_df.join(
            master_df ,  
            on = [
                'Product Name' , 
                'Supplier'
            ] , 
            how = 'anti'
        )

        new_data_df = new_data_df.unique(
            subset = [
                'Product Name' , 
                'Supplier'
            ] , 
            keep = 'last'
        )

        st.session_state.df = pl.concat(
            [
                updated_df , 
                new_rows
            ] , 
            how = 'diagonal'
        )

        my_bar.progress(
            95 , 
            text = 'Saving to CSV (This may take a moment)...'
        )
        
        st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])
        
        my_bar.progress(
            100 , 
            text = 'Process Complete!'
        )
        
        time.sleep(1) 
        my_bar.empty() 

        st.success(f"Processed {len(uploaded_files)} files. Total rows: {len(st.session_state.df)}")

if not st.session_state.df.is_empty() : 
    
    display_df : pl.DataFrame = get_display_df(st.session_state.df)

    if 'TMG Selling Price' in display_df.columns and 'Pack Price' in display_df.columns : 
        
        display_df = display_df.with_columns(
            [
                pl.col('TMG Selling Price').fill_null(0.0).cast(
                    pl.Float64 , 
                    strict = False
                ).alias('__tmg_sell') , 
                
                pl.col('TMG Promotion Price').fill_null(0.0).cast(
                    pl.Float64 , 
                    strict = False
                ).alias('__tmg_promo') , 
                
                pl.col('Pack Price').fill_null(0.0).cast(
                    pl.Float64 , 
                    strict = False
                ).alias('__pack_price') , 
                
                pl.col('Packing Size').fill_null(1.0).cast(
                    pl.Float64 , 
                    strict = False
                ).alias('__pack_size') , 
                
                pl.col('GST').fill_null(0.0).cast(
                    pl.Float64 , 
                    strict = False
                ).alias('__gst') 
            ]
        )

        display_df = display_df.with_columns(
            pl.when(pl.col('__pack_size') == 0).then(1.0).otherwise(pl.col('__pack_size')).alias('__pack_size')
        )
        
        display_df = display_df.with_columns(
            ((pl.col('__pack_price') / pl.col('__pack_size')) * (1 + pl.col('__gst'))).alias('__unit_cost_wgst')
        )

        display_df = display_df.with_columns(
            [
                (pl.col('__tmg_sell') - pl.col('__unit_cost_wgst')).alias('Base Profit') , 
                (pl.col('__tmg_promo') - pl.col('__unit_cost_wgst')).alias('Promotion Profit')
            ]
        )

        display_df = display_df.with_columns(
            [
                pl.when(pl.col('__tmg_sell') > 0)
                .then((pl.col('Base Profit') / pl.col('__tmg_sell')) * 100)
                .otherwise(0.0).alias('Base Profit %') , 
                  
                pl.when(pl.col('__tmg_promo') > 0)
                .then((pl.col('Promotion Profit') / pl.col('__tmg_promo')) * 100)
                .otherwise(0.0).alias('Promotion Profit %')
            ]
        ).drop(
            [
                '__tmg_sell' , 
                '__tmg_promo' , 
                '__pack_price' , 
                '__pack_size' , 
                '__gst' , 
                '__unit_cost_wgst'
            ]
        )

    pandas_display_df : pd.DataFrame = display_df.to_pandas()
    
    pandas_display_df.index = pandas_display_df.index + 1

    st.dataframe(
        pandas_display_df , 
        use_container_width = True
    )


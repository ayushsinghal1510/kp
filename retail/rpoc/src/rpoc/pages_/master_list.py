import os
import time
import streamlit as st
import polars as pl

from rpoc.services import (
    process_document_with_llm , 
    get_display_df
)

st.header(st.session_state.master_list_config['header'])

uploaded_files = st.file_uploader(
    **st.session_state.master_list_config['upload-file']
)

if st.button('Process & Import Files') and uploaded_files : 

    all_new_data = []

    progress_text = "Operation in progress. Please wait."
    my_bar = st.progress(0 , text = progress_text)
    
    total_files = len(uploaded_files)

    for index , file in enumerate(uploaded_files): 

        try : 

            file_path = os.path.join(st.session_state.config['main']['path']['save'], file.name)

            current_progress = int((index / total_files) * 80)
            my_bar.progress(current_progress, text=f"Processing {file.name} ({index+1}/{total_files})")

            with open(file_path , 'wb') as file_obj : 
                file_obj.write(file.getbuffer())

            data = process_document_with_llm(
                file , 
                st.session_state.prompts['ingestion'] , 
                st.session_state.gemini_client
            )

            st.write(data)

            for row in data:
                row['Filename'] = file.name

            all_new_data.extend(data)

        except Exception as e : 
            st.error(f'Error processing {file.name}: {e}')

    if all_new_data : 

        my_bar.progress(85, text="Updating Master List")
        new_data_df = pl.DataFrame(all_new_data)

        # ─── NEW SALES COLUMNS LOGIC (INGESTION PHASE) ────────────────────
        sales_cols = ['TMG Selling Price', 'TMG Promotion Price']
        
        # 1. Ensure columns exist and fill missing with 0.0
        for col in sales_cols:
            if col not in new_data_df.columns:
                new_data_df = new_data_df.with_columns(pl.lit(0.0).alias(col))
            else:
                new_data_df = new_data_df.with_columns(
                    pl.col(col).fill_null(0.0).cast(pl.Float64, strict=False)
                )

        # 2. If Promotion Price is 0, replace with TMG Selling Price
        new_data_df = new_data_df.with_columns(
            pl.when(pl.col('TMG Promotion Price') == 0)
              .then(pl.col('TMG Selling Price'))
              .otherwise(pl.col('TMG Promotion Price')).alias('TMG Promotion Price')
        )
        # ──────────────────────────────────────────────────────────────────

        master_df = st.session_state.df

        for col_name, dtype in master_df.schema.items():
            if col_name in new_data_df.columns:
                new_data_df = new_data_df.with_columns(
                    pl.col(col_name).cast(dtype, strict=False)
                )

        updated_df = master_df.join(
            new_data_df , 
            on = ['Product Name' , 'Supplier'] , 
            how = 'left' , 
            suffix = '_new'
        ).with_columns(
            [
                pl.coalesce(pl.col(f'{c}_new') , 
                pl.col(c)).alias(c)

                for c in st.session_state.config['main']['update-cols']
            ]
        ).select(master_df.columns)

        new_rows = new_data_df.join(
            master_df ,  
            on = ['Product Name' , 'Supplier'] , 
            how = 'anti'
        )

        new_data_df = new_data_df.unique(
                subset = ['Product Name' , 'Supplier'] , 
                keep='last'
            )

        st.session_state.df = pl.concat([updated_df , new_rows] , how = 'diagonal')

        my_bar.progress(95, text="Saving to CSV (This may take a moment)...")
        st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])
        
        # Complete
        my_bar.progress(100, text="Process Complete!")
        time.sleep(1) # Small delay so user sees 100%
        my_bar.empty() # Remove progress bar

        st.success(f'Processed {len(uploaded_files)} files. Total rows: {len(st.session_state.df)}')

if not st.session_state.df.is_empty() : 
    
    # Get base display df
    display_df = get_display_df(st.session_state.df)

    # ─── ON THE FLY PROFIT CALCULATIONS (DISPLAY PHASE) ───────────────
    if 'TMG Selling Price' in display_df.columns and 'Pack Price' in display_df.columns:
        
        # Safely cast all required columns to Float
        display_df = display_df.with_columns([
            pl.col('TMG Selling Price').fill_null(0.0).cast(pl.Float64, strict=False).alias('__tmg_sell'),
            pl.col('TMG Promotion Price').fill_null(0.0).cast(pl.Float64, strict=False).alias('__tmg_promo'),
            pl.col('Pack Price').fill_null(0.0).cast(pl.Float64, strict=False).alias('__pack_price'),
            pl.col('Packing Size').fill_null(1.0).cast(pl.Float64, strict=False).alias('__pack_size'),
            pl.col('GST').fill_null(0.0).cast(pl.Float64, strict=False).alias('__gst') # Assumes GST is decimal (e.g. 0.09)
        ])

        # Prevent division by zero
        display_df = display_df.with_columns(
            pl.when(pl.col('__pack_size') == 0).then(1.0).otherwise(pl.col('__pack_size')).alias('__pack_size')
        )
        
        # Calculate Unit Cost WGST = (Pack Price / Packing Size) * (1 + GST)
        display_df = display_df.with_columns(
            ((pl.col('__pack_price') / pl.col('__pack_size')) * (1 + pl.col('__gst'))).alias('__unit_cost_wgst')
        )

        # Calculate Absolute Profits
        display_df = display_df.with_columns([
            (pl.col('__tmg_sell') - pl.col('__unit_cost_wgst')).alias('Base Profit'),
            (pl.col('__tmg_promo') - pl.col('__unit_cost_wgst')).alias('Promotion Profit')
        ])

        # Calculate Profit Percentages
        display_df = display_df.with_columns([
            pl.when(pl.col('__tmg_sell') > 0)
              .then((pl.col('Base Profit') / pl.col('__tmg_sell')) * 100)
              .otherwise(0.0).alias('Base Profit %'),
              
            pl.when(pl.col('__tmg_promo') > 0)
              .then((pl.col('Promotion Profit') / pl.col('__tmg_promo')) * 100)
              .otherwise(0.0).alias('Promotion Profit %')
        ]).drop(['__tmg_sell', '__tmg_promo', '__pack_price', '__pack_size', '__gst', '__unit_cost_wgst'])
    # ──────────────────────────────────────────────────────────────────

    st.dataframe(
        display_df.to_pandas() , 
        use_container_width = True
    )
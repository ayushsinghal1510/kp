import polars as pl 
from polars import DataFrame, Float64

def get_display_df(df: DataFrame) -> DataFrame:

    # 1. Ensure the sales columns exist (in case older master lists don't have them)
    for col in ['TMG Selling Price', 'TMG Promotion Price']:
        if col not in df.columns:
            df = df.with_columns(pl.lit(0.0).alias(col))

    # 2. Safely cast to Float64 and handle nulls/zeroes
    df = df.with_columns([
        pl.col('Pack Price').cast(Float64, strict=False).fill_null(0.0), 
        pl.col('Packing Size').cast(Float64, strict=False).fill_null(1.0), 
        pl.col('GST').cast(Float64, strict=False).fill_null(0.0),
        pl.col('TMG Selling Price').cast(Float64, strict=False).fill_null(0.0),
        pl.col('TMG Promotion Price').cast(Float64, strict=False).fill_null(0.0)
    ])

    # Prevent division by zero
    df = df.with_columns(
        pl.when(pl.col('Packing Size') == 0).then(1.0).otherwise(pl.col('Packing Size')).alias('Packing Size')
    )

    # 3. Base calculations
    df = df.with_columns(
        [
            # * CTN Price WOGST
            (pl.col('Pack Price') / pl.col('Packing Size')).alias('CTN Price WOGST'), 
            # * Packing Price WGST (Price * (1 + GST))
            (pl.col('Pack Price') * (1 + pl.col('GST'))).alias('Packing Price WGST')
        ]
    ).with_columns(
        [
            # * CTN Price WGST (Calculated from the result above. This acts as Unit Cost WGST)
            (pl.col('Packing Price WGST') / pl.col('Packing Size')).alias('CTN Price WGST'), 
            # * Alias existing columns to match the UI requirements
            pl.col('Pack Price').alias('Packing Price WOGST'), 
        ]
    )

    # 4. Profit Calculations (Using CTN Price WGST as the base cost)
    df = df.with_columns([
        (pl.col('TMG Selling Price') - pl.col('CTN Price WGST')).alias('Base Profit'),
        (pl.col('TMG Promotion Price') - pl.col('CTN Price WGST')).alias('Promotion Profit')
    ])

# 5. Profit Percentages & Formatting
    df = df.with_columns(
        [
            # Base Profit Percentage
            pl.when(pl.col('TMG Selling Price') > 0)
              .then((pl.col('Base Profit') / pl.col('TMG Selling Price')) * 100)
              .when(pl.col('CTN Price WGST') > 0)
              .then(-100.0) # Represents a 100% loss if price is 0 but cost exists
              .otherwise(0.0).alias('Base Profit Percentage'),
              
            # Promotion Profit Percentage
            pl.when(pl.col('TMG Promotion Price') > 0)
              .then((pl.col('Promotion Profit') / pl.col('TMG Promotion Price')) * 100)
              .when(pl.col('CTN Price WGST') > 0)
              .then(-100.0) # Represents a 100% loss if price is 0 but cost exists
              .otherwise(0.0).alias('Promotion Profit Percentage'),

            pl.col('Pack Price Currency').alias('Packing Price Currency')
        ]
    ).with_columns(
        [
            pl.col('Packing Price Currency').alias('CTN Price Currency')
        ]
    ).with_columns(
        [
            (pl.col('GST') * 100).alias('GST Percentage')
        ]
    )
    # 6. Final Select (Explicitly outputting the new columns to the UI)
    return df.select(
        [
            'Product Name', 
            'Supplier', 
            'Packing Price WOGST', 
            'Packing Price Currency',
            'Packing Size' ,  
            'CTN Price WOGST', 
            'CTN Price Currency', 
            'GST Percentage', 
            'Packing Price WGST', 
            'CTN Price WGST',
            
            # --- New Columns ---
            'TMG Selling Price',
            'TMG Promotion Price',
            'Base Profit',
            'Base Profit Percentage',
            'Promotion Profit',
            'Promotion Profit Percentage'
        ]
    )
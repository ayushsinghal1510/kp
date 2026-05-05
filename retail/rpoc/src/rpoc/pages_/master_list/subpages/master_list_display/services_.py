import polars as pl

from polars import (
    DataFrame , 
    Float64 , 
    Utf8
)

def get_display_df(
    df : DataFrame , 
) -> DataFrame : 

    sales_cols : list[str] = [
        'Selling Price' , 
        'Promotion Price' , 
        'Previous Price'
    ]
    
    for col in sales_cols : 
        if col not in df.columns : 
            df = df.with_columns(
                pl.lit(0.0).alias(col)
            )

    if 'Barcode' not in df.columns : 
        df = df.with_columns(
            pl.lit('').alias('Barcode')
        )

    df = df.with_columns(
        [
            pl.col('Barcode').cast(
                Utf8 , 
                strict = False
            ).fill_null('') , 
            pl.col('Pack Price').cast(
                Float64 , 
                strict = False
            ).fill_null(0.0) , 
            pl.col('Previous Price').cast(
                Float64 , 
                strict = False
            ).fill_null(0.0) , 
            pl.col('Packing Size').cast(
                Float64 , 
                strict = False
            ).fill_null(1.0) , 
            pl.col('Selling Price').cast(
                Float64 , 
                strict = False
            ).fill_null(0.0) , 
            pl.col('Promotion Price').cast(
                Float64 , 
                strict = False
            ).fill_null(0.0)
        ]
    )

    df = df.with_columns(
        pl.when(
            pl.col('Packing Size') == 0
        ).then(1.0).otherwise(
            pl.col('Packing Size')
        ).alias('Packing Size')
    )

    gst_rate : float = 0.09

    df = df.with_columns(
        [
            (pl.col('Pack Price') / pl.col('Packing Size')).alias('CTN Price WOGST') , 
            (pl.col('Pack Price') * (1.0 + gst_rate)).alias('Packing Price WGST')
        ]
    ).with_columns(
        [
            (pl.col('Packing Price WGST') / pl.col('Packing Size')).alias('CTN Price WGST') , 
            pl.col('Pack Price').alias('Packing Price WOGST')
        ]
    )

    df = df.with_columns(
        [
            (pl.col('Selling Price') - pl.col('CTN Price WGST')).alias('Base Profit') , 
            (pl.col('Promotion Price') - pl.col('CTN Price WGST')).alias('Promotion Profit')
        ]
    )

    df = df.with_columns(
        [
            pl.when(
                pl.col('Selling Price') > 0
            ).then(
                (pl.col('Base Profit') / pl.col('Selling Price')) * 100
            ).when(
                pl.col('CTN Price WGST') > 0
            ).then(-100.0).otherwise(0.0).alias('Base Profit Percentage') , 

            pl.when(
                pl.col('Promotion Price') > 0
            ).then(
                (pl.col('Promotion Profit') / pl.col('Promotion Price')) * 100
            ).when(
                pl.col('CTN Price WGST') > 0
            ).then(-100.0).otherwise(0.0).alias('Promotion Profit Percentage') , 
        ]
    )
    
    return df.select(
        [
            'Barcode' , 
            'Product Name' , 
            'Supplier' , 
            'Previous Price' , 
            'Packing Price WOGST' , 
            'Packing Size' ,  
            'CTN Price WOGST' , 
            'Packing Price WGST' , 
            'CTN Price WGST' , 
            'Selling Price' , 
            'Promotion Price' , 
            'Base Profit' , 
            'Base Profit Percentage' , 
            'Promotion Profit' , 
            'Promotion Profit Percentage'
        ]
    )

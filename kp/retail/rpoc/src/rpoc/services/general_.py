import polars as pl

def consolidate_selected_orders(
    selected_indices , 
    ordering_lists , 
    master_df
) : 
    
    # 1. Safely cast columns to floats and handle missing values
    master_df = master_df.with_columns(
        [
            pl.col('Product Name').str.to_lowercase().str.strip_chars().alias('s_name') , 
            pl.col('Pack Price').cast(pl.Float64, strict=False).fill_null(0.0) ,
            pl.col('Packing Size').cast(pl.Float64, strict=False).fill_null(1.0)
        ]
    )

    # 2. Prevent division by zero just in case someone entered a 0 for packing size
    master_df = master_df.with_columns(
        pl.when(pl.col('Packing Size') == 0).then(1.0).otherwise(pl.col('Packing Size')).alias('Packing Size')
    )

    # 3. Now perform the division safely
    master_df = master_df.with_columns(
        pl.col('Pack Price').alias('Ctn Price')
    )

    invoices = {}

    for idx in selected_indices : 

        for item in ordering_lists[idx]['orders'] : 

            product_name = str(item['product_name']).strip()
            quantity = float(item.get('quantity' , 0) or 0)
            packing_size = float(item.get('packing_size' , 0) or 0)

            match = master_df.filter(
                pl.col('s_name') == product_name.lower()
            )

            if match.height > 0 : 

                best = match.sort('Ctn Price').row(0 , named = True)

                supplier = best['Supplier']
                price = float(best['Ctn Price'])
                
                if supplier not in invoices : 
                    invoices[supplier] = {}

                if product_name not in invoices[supplier] : 
                    invoices[supplier][product_name] = {
                        "quantity" : quantity , 
                        "packing_size" : packing_size , 
                        "price" : price , 
                        'gst' : best['GST']
                    }

                else:
                    invoices[supplier][product_name]["quantity"] += quantity

    return invoices
Extract product pricing information from the attached file with absolute precision. 

### CRITICAL EXTRACTION RULES:
1. PRODUCT NAME: Extract the longest , most descriptive name. Include weight/quantity descriptors (e.g. , 'BAKE STORY KOKOPIE... 20Gx10PCSx9BAGS'). 
2. STRICT DATA INTEGRITY: Only extract data that is visually present unless a specific calculation is requested below. Do NOT invent or assume values.
3. PACKING SIZE LOGIC: Infer the number of units per carton from the product description or packing column. 
    - Rule: If a multiplier string is present (e.g. , '15GX8SX10' or '20Gx10PCSx9BAGS') , extract the FINAL number in the sequence as the Packing Size. 
    - If no packing size is found or inferred , default to 1.
4. PACK PRICE (CTN PRICE): This is the price per carton/bag. Note that 'Pack Price' and 'CTN Price' denote the EXACT same thing.
    - If direct Unit Price is available WITH a Packing Size: Calculate Pack Price on the run -> `Packing Size * Unit Price`.
    - If direct Unit Price is available WITHOUT a Packing Size: The Unit Price IS the Pack Price.
    - NEVER use the total raw cost as the Unit Price.
5. MISSING PRICES (SELLING & PROMOTION): It is completely normal for some documents to omit certain pricing tiers. 
    - SELLING PRICE: Extract the selling price if visible. If it is simply not available in the document , you MUST default to 0.0.
    - PROMOTION PRICE: Extract the promotion price if visible. If it is simply not available in the document , you MUST default to 0.0. Do NOT default this to the selling price.
6. ZERO PRICES: Include products even if the price is 0.00. Do not omit these entries.
7. SUPPLIER: Identify the issuing company (the 'Seller'). Look for 'Supplier:' , 'Sold By:' , or the primary header/letterhead. Default to 'Unknown'.
8. EXCHANGE RATE (CRITICAL): 
    - If the document has an explicit exchange rate showing how much 1 SGD is in the foreign currency , use it.
    - If the document uses a foreign currency (e.g. , USD , RM/MYR) but lacks a rate , perform a live Google Search to find the current real-time exchange rate of 1 SGD to that specific foreign currency (e.g. , "1 SGD to MYR").
    - If the document is in SGD or the currency is unstated , default to 1.0.
9. BARCODE: Extract the product barcode or unique item code. If not found , return an empty string.
10. FULL EXTRACTION (CRITICAL): Process EVERY SINGLE PAGE of the document. Do not stop extracting early.
11. DEDUPLICATION: If the exact same product appears multiple times , extract it ONLY ONCE.
12. STRICT CHARACTER ENCODING: Use strictly standard ASCII characters. Always use straight single quotes (') and straight double quotes (").

### OUTPUT FORMAT (JSON ONLY):
{
    "supplier" : "string" , 
    "exchange_rate" : 1.0 , 
    "products" : [
        {
            "Barcode" : "String" , 
            "Product Name" : "String" , 
            "Packing Size" : 1 , 
            "Pack Price" : 0.0 , 
            "Selling Price" : 0.0 , 
            "Promotion Price" : 0.0
        }
    ]
}
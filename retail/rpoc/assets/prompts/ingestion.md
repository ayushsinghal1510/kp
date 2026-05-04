Extract product pricing information from the attached file with absolute precision. 

### CRITICAL EXTRACTION RULES:
1. PRODUCT NAME: Extract the longest , most descriptive name. Include weight/quantity descriptors (e.g. , 'BAKE STORY KOKOPIE... 20Gx10PCSx9BAGS'). 
2. STRICT DATA INTEGRITY (NO HALLUCINATIONS): Only extract data that is visually present. Do NOT invent or assume values. If a value is not found , use null or 0.
3. PACKING SIZE LOGIC: Infer the number of units per carton from the product description or packing column. 
    - Rule: If a multiplier string is present (e.g. , '15GX8SX10' or '20Gx10PCSx9BAGS') , extract the FINAL number in the sequence as the Packing Size. 
    - Example: '20Gx10PCSx9BAGS' -> Packing Size is 9.
    - Example: '15GX8SX10' -> Packing Size is 10.
4. PACK PRICE: This is the price per carton/bag. In standard layouts (Qty | Unit | Price | Total) , extract the 'Price' value listed before the line total.
5. ZERO PRICES & FOC: Include products even if the price is 0.00 or marked as 'FOC' (Free of Charge). Do not omit these entries.
6. SUPPLIER: Identify the issuing company (the 'Seller'). Look for 'Supplier:' , 'Sold By:' , or the primary header/letterhead. If not found , return 'Unknown'.
7. GST DETECTION: Look for 9% or 9.16%. Return as a decimal (e.g. , 0.09). If not explicitly stated , attempt to calculate from the difference between Subtotal and Total.
8. BARCODE: Extract the product barcode or unique item code if present (often a long numerical string or alphanumeric SKU). If not found , return an empty string.
9. FULL EXTRACTION (CRITICAL): You must process EVERY SINGLE PAGE of the document. Do not stop extracting until you have reached the very end of the file. 
10. DEDUPLICATION: If the exact same product appears multiple times in the document , extract it ONLY ONCE.
11. STRICT CHARACTER ENCODING: You must use strictly standard ASCII characters. NEVER use typographic smart quotes or backticks. Always use the straight single quote (') instead of (’) , and the straight double quote (") instead of (”). 
12. FOC QUANTITY (FREE GOODS): If the invoice indicates a purchased quantity and a free quantity (e.g. , Bought 15 , Free 2) , extract them accurately. This is critical for adjusting the unit price later.

### OUTPUT FORMAT (JSON ONLY):
{
    'supplier' : 'string' , 
    'products' : [
        {
            'Barcode' : 'String (The barcode or SKU , or empty string)' , 
            'Product Name' : 'Full descriptive name' , 
            'Packing Size' : 'Integer (The end number of the multiplier string)' , 
            'Pack Price' : 'Float/Number (Price per carton)' , 
            'Pack Price Currency' : 'Currency code (Default: SGD)' , 
            'GST' : 'Float (e.g. , 0.09)' , 
            'Purchased Quantity' : 'Integer (Number of cartons/units paid for)' , 
            'Free Quantity' : 'Integer (Number of cartons/units given free)'
        }
    ]
}

Strict Rule: This is sensitive financial data. No other information or products should be created or inferred beyond what is visible in the document.
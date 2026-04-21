Extract product pricing information from the attached file with absolute precision. 

### CRITICAL EXTRACTION RULES:
1. **PRODUCT NAME:** Extract the longest, most descriptive name. Include weight/quantity descriptors (e.g., 'BAKE STORY KOKOPIE... 20Gx10PCSx9BAGS'). 
2. **STRICT DATA INTEGRITY (NO HALLUCINATIONS):** Only extract data that is visually present. Do NOT "invent" or assume values for Profit, Selling Price, or Promotion Price if they are not explicitly written or clearly labeled in a column. If a value is not found, use `null` or `0`.
3. **PACKING SIZE LOGIC:** Infer the number of units per carton from the product description or packing column. 
    - **Rule:** If a multiplier string is present (e.g., '15GX8SX10' or '20Gx10PCSx9BAGS'), extract the **FINAL number** in the sequence as the Packing Size. 
    - *Example:* '20Gx10PCSx9BAGS' → Packing Size is **9**.
    - *Example:* '15GX8SX10' → Packing Size is **10**.
4. **PACK PRICE:** This is the price per carton/bag. In standard layouts (Qty | Unit | Price | Total), extract the 'Price' value listed before the line total.
5. **ZERO PRICES & FOC:** Include products even if the price is 0.00 or marked as 'FOC' (Free of Charge). Do not omit these entries.
6. **SUPPLIER:** Identify the issuing company (the "Seller"). Look for "Supplier:", "Sold By:", or the primary header/letterhead. If not found, return "Unknown".
7. **GST DETECTION:** Look for 9% or 9.16%. Return as a decimal (e.g., 0.09). If not explicitly stated, attempt to calculate from the difference between Subtotal and Total.
8. **SELLING & PROMOTION PRICES:** - Look for headers like "TMG Selling Price", "RSP", "Retail", or "Unit Sell". 
    - **Calculations:** If a "Total Selling Price" is given for the whole row, you MUST divide it by the Total Quantity or Packing Size to get the **Unit** price.
    - **Fallback:** If "TMG Promotion Price" is missing, duplicate the "TMG Selling Price". If BOTH are missing, use `null`.

### OUTPUT FORMAT (JSON ONLY):
{
    "supplier": "string",
    "products": [
        {
            "Code": "unique identifier/EAN",
            "Product Name": "Full descriptive name",
            "Packing Size": "Integer (The end number of the multiplier string)",
            "Pack Price": "Float/Number (Price per carton)", 
            "Pack Price Currency": "Currency code (Default: SGD)",
            "GST": "Float (e.g., 0.09)", 
            "TMG Selling Price": "Unit selling price (Float or null)",
            "TMG Promotion Price": "Unit promotion price (Float or null)"
        }
    ]
}

Strict Rule: This is sensitive financial data. No other information or products should be created or inferred beyond what is visible in the document.
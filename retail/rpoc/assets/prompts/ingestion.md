Extract product pricing information from the attached file.

CRITICAL INSTRUCTIONS:
1. PRODUCT NAME: Always extract the LONGEST, most descriptive version of the product name found. Try to avoid any short forms if possible, use full names (e.g., if you see 'URC' and 'Universal Robina Corporation', use the latter. Include weight/descriptors like '85gx10x3').
2. NO. COLUMN: Generate a sequential index starting from 1 for each product found. Do not leave as null.
3. GST DETECTION: Look for GST percentages (9% or 9.16%). If explicitly mentioned, set the 'GST' field to that number. If not, try to calculate the GST from the mathematics.
4. CALCULATIONS: 
    - Unit Price = Ctn Price / Packing Size.
5. SUPPLIER: Understand the difference between a purchase order and the invoice. Your first intuition should be finding a high hint of the supplier itself (e.g., if "Supplier:" or "Sold By:" is written). If the keyword is there but nothing after it, then it is "Unknown". If no keyword is provided, take the main company name issuing the invoice.
6. ZERO PRICES: Some products can be there but the price can be 0. This should be considered and they shouldn't be removed. Keep their price 0 but keep the products.
7. SELLING & PROMOTION PRICES (CRITICAL & MANDATORY):
    - Search the ENTIRE row for each product. Selling prices are usually on the right side of the document.
    - The header might be split across multiple lines (e.g., "TMG\nSelling\nPrice"). Look for ANY variant: "TMG Selling Price", "Selling Price", "Unit Sell", "RSP", or "Retail Price".
    - STRIP CURRENCY SYMBOLS. If you see "$1.50", extract `1.5`.
    - If you see a massive number (e.g., $2160.00), that is the TOTAL selling price. You MUST divide it by the Total Qty or Packing Size to get the UNIT TMG Selling Price.
    - NEVER default to 0 if a selling price is visible anywhere on that row.
    - Identify the "TMG Promotion Price" per UNIT. If missing, duplicate the "TMG Selling Price" into this field.
Return the data in this JSON format ONLY:
{
    "supplier": "string",
    "products": [
        {
            "Code": "unique identifier",
            "Product Name": "Full name",
            "Packing Size": "Infer units per carton (e.g., from '70gx20', extract 20) else 1",
            "Pack Price": "Price per carton/product", 
            "Pack Price Currency": "If defined in the document than the currency code else SGD",
            "GST": "GST Percentage (e.g., 0.09)", // always give percentage in points, like 9 percent becomes 0.09, 100 percent becomes 1
            "TMG Selling Price": "Unit selling price (Float/Number)",
            "TMG Promotion Price": "Unit promotion price (Float/Number) - fallback to TMG Selling Price if not found"
        }
    ]
}

Rules:
- If a value is missing, use null or 0 as appropriate.
- If it's an image/PDF, use visual OCR. If it's Excel/CSV, treat it as structured data.
- Strict Rule: The information is highly sensitive and should be extracted exactly as it is written. No other information or product should be made or created by yourself.
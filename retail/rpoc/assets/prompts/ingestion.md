# Integrated Data Extraction

Extract product pricing information from the attached file with absolute precision.

### CRITICAL EXTRACTION RULES

1. **PRODUCT NAME:** Extract the **longest possible**, most descriptive name visually present. Include all weight/quantity descriptors, flavor profiles, and packaging variations (e.g., 'BAKE STORY KOKOPIE CHOCOLATE FLAVOUR 20Gx10PCSx9BAGS'). Never truncate or abbreviate.
2. **STRICT DATA INTEGRITY:** Only extract data that is visually present unless a specific calculation is requested below. Do NOT invent or assume values.

---

### 1. PACKING SIZE EXTRACTION

* Do NOT multiply numbers together to get the packing size **unless** dealing with explicit multi-tier grid notations (see multi-tier rule below). Extract the explicit integer value representing the carton/pack multiplier.
* The packing size can sometimes be at the start of the product name or number series. However, a starting number is ONLY the packing size if there is NO alphabetical character (like 's', 'g', 'ml') immediately following it.
* **Character Suffix Exception:** If characters like 'P', 'p', 'S', 's', 'pcs', 'PKTS', 'pkts', or 'packets' follow a number, it is considered a valid packing size identifier.

#### A. Packaging Suffix Precedence (B > P > S)

When multiple letter-coded packaging tiers are present, resolve them in chronological order from outer container to inner container: **B (Bags/Boxes/Cartons) > P (Packs/Packets) > S (Small items/Sachets)**.

* *Example:* "6SX7PX8B" -> The outermost container multiplier is 'B', so the packing size is **8**.

#### B. Multi-Tier Grid Rule

If the configuration explicitly lists an interleaved multi-tier multiplier network (e.g., `[Qty]X[Qty]PCKS`), multiply the tiers to get the net packing size per primary transacted unit.

* *Example:* "240GM10X12PCKS COLADA BISCORNIVAL NAIYU SODA" -> 10 x 12 = Packing size is **120**.

(1 CTN x 10 Bag x 12 Pkts) -> 10 x 12 = Packing size is 120

#### C. Drink Volume Defaults (Use unless explicit specifications contradict)

* **Canned/Bottled Drinks [250ml - 450ml]:** Default Packing Size = **24**
* **Canned/Bottled Drinks [500ml]:** Default Packing Size = **24**
* **Canned/Bottled Drinks [1000ml - 1500ml]:** Default Packing Size = **12**
* **Tetra Pack Drinks [pkt]:** Default Packing Size = **4**
* **Ribena Regular [850ml]:** Explicitly Packing Size = **6**
* **Ribena Regular [600ml]:** Explicitly Packing Size = **12**
* *Overriding Specification Example:* "qoo white grape 300ml x 12" -> Explicitly Packing Size = **12**.

#### D. General Reference Examples

QTY to be considered always as quantity instead of packing size 

* "24 x 45g" -> Packing Size: 24
* "24 x 45g x 34" -> Packing Size: 34
* "24s x 45g" -> Packing Size: 24
* "45g x 34" -> Packing Size: 34
* "45g x 34s" -> Packing Size: 34
* "24 x (12 x 20s)" -> Packing Size : 24
* "55GMX5PX6B" -> Packing Size : 6
* "55GMX5TX6B" -> Packing Size : 6
* "24S" -> Packing Size : 1
* "18GX8SX10 FP(FY18) SG" -> Packing size : 10
* "85g x24 (SG)" -> Packing size : 24
* "64g*6+2*8" -> Packing size : 6
* "120g*6*8" -> Packing size : 48
* " 10s" -> Packing size : 10
* "CHEWY GINGER (ORI) 4 (20PKT X 125G) 4PKGCTN" : Packing size : 4 * 20 = 80
* "240GM@10X12PCKS COLADA BIS.CORNIVAL NAIYU" : Packing size : 10 * 12 = 120 : @ acts as delimiter
* "200GMX10@12PCK BIS.COLADA LIGHT TREAT C.C.SP" : Packing size : 12 : @ acts as delimiter

* @ AS DELIMITER — TWO DISTINCT CASES:

  CASE A: [weight]@[tierA]X[tierB] — @ appears right after the weight/GM value,
  before any multiplier tiers. Treat everything after @ as a multi-tier grid.
  Multiply all tiers together.
  Example: "240GM@10X12PCKS" → 10 × 12 = 120
  Example: "240GM@10X24PCKS" → 10 × 24 = 240

  CASE B: [weight]X[tierA]@[tierB] — @ appears AFTER at least one X-multiplier 
  tier. The @ acts as a hard reset. Discard everything before @. 
  Take ONLY the number immediately after @.
  Example: "200GMX10@12PCK" → 12 (ignore the X10 entirely)
  Example: "200GMX10@24PCK" → 24 (ignore the X10 entirely)

  KEY TEST: Is there an X-tier BEFORE the @? 
  YES → Case B (take only after @). NO → Case A (multiply all after @).

* FOC DETECTION & ADJUSTED PACK PRICE:

  PATTERN: FOC items appear as a DUPLICATE line with the same barcode/
  material number, but with Unit Price = 0.00 and a smaller quantity.
  This 0.00-priced duplicate is the FOC quantity — NOT a free product 
  to be extracted separately.

  STEP 1 — DETECT: If the same barcode name appears more than once and one 
  of those rows has Unit Price = 0.00, treat the 0.00 row as FOC.
  Do NOT extract the 0.00 row as a separate product.

  STEP 2 — MERGE: Combine both rows into one product entry.
  - Paid Qty = quantity from the row with a real Unit Price
  - FOC Qty = quantity from the 0.00 row
  - Total Value = Value from the paid row only

  STEP 3 — ADJUSTED PACK PRICE FORMULA:
  Adjusted Pack Price = Total Value / (Paid Qty + FOC Qty)

  Example from invoice:
  Barcode 100541417, Paid Qty = 24, FOC Qty = 2, Total Value = 1,944.00
  Adjusted Pack Price = 1,944.00 / (24 + 2) = 1,944.00 / 26 = 74.77

  Example 2:
  Barcode 100474283, Paid Qty = 12, FOC Qty = 1, Total Value = 604.44
  Adjusted Pack Price = 604.44 / (12 + 1) = 604.44 / 13 = 46.50

  IMPORTANT: If a product has NO 0.00 duplicate row, no FOC adjustment 
  is made. Use Pack Price = U/Price × Packing Size as normal.
---

### 1. PACKING SIZE EXTRACTION

* Find the packing tier multiplier strictly from the product text or description configuration patterns (e.g., "1*3" -> 3, "1*24" -> 24, "1*18" -> 18).
* Never calculate a packing size by dividing document totals, dividing quantities, or matching "Pack UOM" against "Qty".

---

### 2. PACK PRICE / CARTON PRICE CALCULATION (ZERO MATH EXCEPT MULTIPLICATION)

Rate means Packing price and not unit price
If you see rate column, its packing price only
* **CRITICAL MANDATE:** You are strictly forbidden from looking at the "Total" or "Total RM" columns to calculate or cross-verify prices. Do NOT reverse-engineer prices using row totals or overall quantities.
* **DISCOUNTS & FOC:** Assume all discounts are 0%. Completely ignore dicsount based columns, the current discount is 0, FOC is there, but the current discount is always 0.
* **THE ONLY VALID PRICE FORMULA:** Locate the raw, single unit price printed in the "U/ Price" or "Unit Price" column. 
  * `Pack Price = [U/ Price Column Value] * [Packing Size]`
  * **Example:** If "U/ Price" is visually printed as 12.31000 and "Packing Size" is extracted as 3, the calculation MUST be exactly: 12.31 * 3 = 36.93. 
  * Do not adjust, do not slice, do not round intermediate states, and do not use any hidden values. Use exactly what your eyes see in the unit price field.* *Note:* Use the raw, undiscounted Unit Price to find the "Stated Pack Price" before applying this formula.* *Exampl   e:* A supplier lists a product at a CTN Price of $10. The buyer purchases 10 CTNs ($100 total value) and receives 1 extra CTN for free (1 FOC). The adjusted Pack Price is calculated as `$100 / (10 + 1) = $9.09`.

* **DISCOUNTS — ALWAYS ZERO:** The "Disc" column must be completely ignored 
  in all calculations. Treat it as if it does not exist on the page. 
  Never multiply U/Price by (1 - disc%). 
  WRONG: 12.31 × 0.96 × 3 = 35.45 ← FORBIDDEN
  CORRECT: 12.31 × 3 = 36.93 ← ONLY valid formula

* **FOC (Free of Charge) — APPLY THIS ADJUSTMENT:** If a FOC quantity is 
  stated (e.g. buy 10 get 1 free), adjust the Pack Price as follows:
  Adjusted Pack Price = (Purchased Qty × Pack Price) / (Purchased Qty + FOC Qty)
  Example: Pack Price = 36.93, buy 10 get 1 FOC →
  Adjusted Pack Price = (10 × 36.93) / (10 + 1) = 369.30 / 11 = 33.57
  If no FOC quantity is stated, do NOT apply any FOC adjustment.

---

### 3. GENERAL TIER & DATA RULES

* **SUPPLIER NAME RESOLUTION (CRITICAL):** Identify the issuing seller by looking for 'Supplier:', 'Sold By:', or the primary header/letterhead.
* Extract the **longest, most complete version** of the name available.
* If the name on the document is abbreviated, acronymized, or inconsistent (e.g., "Tong Garden Food (S) Pte Ltd"), **you must perform a live Google Search** using the visible text to find and extract the full, official registered legal corporate name (e.g., "TONG GARDEN FOOD (SINGAPORE) PTE LTD").
* Default to **'Unknown'** if completely unidentifiable.


* **MISSING PRICES (SELLING & PROMOTION):** Documents frequently omit these.
* *SELLING PRICE:* If omitted, default to **0.0**.
* *PROMOTION PRICE:* If omitted, default to **0.0**. Do NOT mirror or copy the selling price into this field.


* **ZERO PRICES:** Process and include items even if their extracted price evaluates to 0.00.
* **EXCHANGE RATE:** If the document uses a foreign currency (e.g., USD, RM/MYR) but lacks an explicit rate, look up the real-time conversion rate of **1 SGD to that foreign currency**. If the document is in SGD or the currency is unstated, default to **1.0**.
* **BARCODE:** Extract the unique item barcode/SKU code. If missing, return an empty string `""`.
* **FULL EXTRACTION & DEDUPLICATION:** Process every single page completely. If an identical product line occurs multiple times across pages, extract it **only once**.
* **STRICT CHARACTER ENCODING:** Use strictly standard ASCII characters. Always use straight single quotes (') and straight double quotes (").

---

### OUTPUT FORMAT (JSON ONLY)

```json
{
    "supplier": "string", 
    "exchange_rate": 1.0, 
    "products": [
        {
            "Barcode": "string", 
            "Product Name": "string", 
            "Packing Size": 1, 
            "Pack Price": 0.0, 
            "Selling Price": 0.0, 
            "Promotion Price": 0.0
        }
    ]
}

```
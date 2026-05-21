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

---

### 2. PACK PRICE / CARTON PRICE CALCULATION & FOC ADJUSTMENTS

* **Pack Price** and **CTN Price** denote the EXACT same thing (price per carton/bag).
* Column headers like "COST/PKT", "COST/PK", or "NEW COST/PK" mean cost per individual packet (**Unit Price**). They are **never** the carton price.
* **Base Formula:** If direct Unit Price is available, `Pack Price = Unit Price * Packing Size`. If direct Unit Price is available WITHOUT a Packing Size, the Unit Price IS the Pack Price.

#### FOC (Free of Charge) Amortization Rule

If an invoice line features FOC items, the static item cost is altered because the free items lower the effective unit cost across the total shipment. You must adjust the Pack Price dynamically based on the total paid amount distributed over the true total received quantity (Paid + FOC).

* **Amortized Pack Price Formula:** `(Paid Quantity * Stated Pack Price) / (Paid Quantity + FOC Quantity)`
* *Example:* A supplier lists a product at a CTN Price of $10. The buyer purchases 10 CTNs ($100 total value) and receives 1 extra CTN for free (1 FOC). The adjusted Pack Price is calculated as `$100 / (10 + 1) = $9.09`.

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
# Integrated Data Extraction

Extract product pricing information from the attached file with absolute precision.

### CRITICAL EXTRACTION RULES

1. **PRODUCT NAME — VERBATIM, ZERO EXCEPTIONS (this is checked run-to-run for consistency):** `Product Name` MUST equal the ENTIRE printed Description text for that row, character for character, including the trailing weight/quantity/dimension descriptor (e.g. "18 x 140g", "6 x (2 x 800ml) Twin Pack") — do NOT drop that suffix just because the same numbers are also captured separately in `Packing Size`. `Product Name` and `Packing Size` are independent fields; filling in `Packing Size` is never a reason to shorten `Product Name`.
   * WRONG (dropped the dimension suffix): "Twisties Cheeky Cheddar Cheese 140g"
   * CORRECT (full row text kept, joined with a single space — verified against the master list convention): "Twisties Cheeky Cheddar Cheese 140g 18 x 140g"
   * **Do NOT insert a comma (or any other punctuation) between the base name and the dimension suffix unless a comma is actually printed on the invoice.** Join them exactly as they appear — usually just a space. Inserting punctuation that isn't in the source is itself a form of not-verbatim and has been observed to break matching against the master list.
   * This has been observed to vary between re-extractions of the exact same invoice — treat "keep every character of the Description cell" as a hard requirement, not a stylistic preference. Include all weight/quantity descriptors, flavor profiles, and packaging variations that are printed INSIDE the Description cell itself (e.g., 'MAMEE CHEF CREAMY TOMYAM THAI 8(4X82G)'), even put asterisk as there in the product name. Never truncate, abbreviate, or "clean up" the name. (If the weight/packing notation is instead printed in a SEPARATE column next to Description rather than inside the Description cell, see the SEPARATE "PACKING" COLUMN rule below instead — it is NOT always appended.)
   * **EXCEPTION — do NOT include the barcode/article-number digit string in `Product Name`, even when it is printed immediately next to or overlapping the description text.** The barcode has its own dedicated `Barcode` field (see the ROBUST BARCODE EXTRACTION rule below) — copying it into `Product Name` as well is redundant AND has been observed to vary run-to-run (sometimes the digits get glued in, sometimes not), which breaks product matching. If you can identify a run of 8-14 digits as a barcode/article number, it goes in `Barcode` ONLY, never appended into `Product Name`.
     * WRONG: `"APOLLO (1044A) CHOC STICK WAFER 726165382071024(30X11G)"` (barcode digits `726165382071` bled into the name)
     * CORRECT: `Product Name` = `"APOLLO (1044A) CHOC STICK WAFER 24(30X11G)"`, `Barcode` = `"726165382071"` (kept separate)
   * **SEPARATE "PACKING" COLUMN — SUPPLIER-SPECIFIC, CHECK WHICH CONVENTION APPLIES:** Several suppliers print `DESCRIPTION` and `PACKING`/`CARTON PACKING` as two DIFFERENT table columns (the dimension/carton notation is a distinct column next to Description, not glued into the same cell — e.g. Description cell says "COKE", separate Packing column says "12X1.25LT"). Whether the Packing-column text belongs in `Product Name` depends on the SPECIFIC SUPPLIER, verified against the master list — there is NO single universal rule here, and suppliers with this same two-column layout do NOT all behave the same way:
     * **TGS GROUP SDN BHD** invoices (columns: `ITEM QTY | DESCRIPTION | ITEM CODE | PACKING | WEIGHT | U.PRICE | AMOUNT`): APPEND — `Product Name` = Description + " " + Packing. E.g. Description "COKE" + Packing "12X1.25LT" -> `"COKE 12X1.25LT"`; Description "MAGGI HOT CUP (C)" + Packing "54X57G" -> `"MAGGI HOT CUP (C) 54X57G"`.
     * **Sheng Sheng F&B Industries** invoices (`PACKING` column printed BEFORE `DESCRIPTION`): PREPEND — `Product Name` = Packing + " " + Description. E.g. Packing "24X310ML" + Description "ICE COOL YOUNG COCONUT WITH PULP" -> `"24X310ML ICE COOL YOUNG COCONUT WITH PULP"`.
     * **Liverpool International, Sun Lim Garden Foodstuffs, Winstar Marketing** invoices (and any other supplier not listed above with a separate Packing/Carton Packing column): DROP IT — `Product Name` = the Description-cell text only, verbatim, do NOT append or prepend the Packing-column text. E.g. Description "Doritos Nacho Cheese 75g" with separate Packing column "75g X 64" -> `Product Name` = `"Doritos Nacho Cheese 75g"` (Packing column ignored).
     * If the supplier is not one of the ones named above and you cannot tell which convention applies, default to Description-cell text only (do not invent a concatenation).
2. **STRICT DATA INTEGRITY:** Only extract data that is visually present unless a specific calculation is requested below. Do NOT invent or assume values.

---

⚠️ SPECIAL CHARACTER PRESERVATION (MANDATORY):
Preserve ALL characters exactly as printed in the source document within 
the "Product Name" field. This includes asterisks (*), plus signs (+), 
parentheses, slashes, and any other symbols. Never strip, escape, or 
replace any character for formatting reasons.

### 1. PACKING SIZE EXTRACTION

* Do NOT multiply numbers together to get the packing size **unless** dealing with explicit multi-tier grid notations (see multi-tier rule below). Extract the explicit integer value representing the carton/pack multiplier.
* The packing size can sometimes be at the start of the product name or number series. However, a starting number is ONLY the packing size if there is NO alphabetical character (like 's', 'g', 'ml') immediately following it.
* **Character Suffix Exception:** If characters like 'P', 'p', 'S', 's', 'pcs', 'PKTS', 'pkts', or 'packets' follow a number, it is considered a valid packing size identifier.
* **NO PACKING NOTATION PRESENT — DEFAULT TO 1, NEVER USE THE ORDER QUANTITY (real example, LOKE KEE BISCUITS AND CAKE SHOP):** Some invoices sell items loose/individually with NO carton or multi-pack notation anywhere in the Description at all — just a plain name (e.g. "Biscuit SKM", "Lou Poh Ben", "Heong Peah (Ori)") next to a "Quantity" column showing how many packets were ordered (e.g. "360 Pkt", "700 Pkt"). That Quantity/Qty/Order-Qty column is HOW MANY were ordered, not a packing multiplier — it must NEVER be copied into `Packing Size`. When the Description has no packing/dimension notation whatsoever, `Packing Size` MUST default to **1**.
  * WRONG: Description = "Biscuit SKM", Quantity column = "360 Pkt" -> Packing Size = 360 (this is the order quantity, not a pack size)
  * CORRECT: Packing Size = **1**

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
* YAN YAN CHOCOLATE 10X50G44G (No Return) 8 OUTCTN : Pakcing size : 10 * 8 = 80 : 10 from the first and 8 is the outer ctn, so 80
* CWM CHERRY PLUM 10X80G : Packing size : 10
* @ AS DELIMITER — TWO DISTINCT CASES:
CASE A: [weight]@[tierA]X[tierB] — @ appears right after the weight/GM value, before any multiplier tiers. Treat everything after @ as a multi-tier grid. Multiply all tiers together.
Example: "240GM@10X12PCKS" → 10 × 12 = 120
Example: "240GM@10X24PCKS" → 10 × 24 = 240
CASE B: [weight]X[tierA]@[tierB] — @ appears AFTER at least one X-multiplier tier. The @ acts as a hard reset. Discard everything before @. Take ONLY the number immediately after @.
Example: "200GMX10@12PCK" → 12 (ignore the X10 entirely)
Example: "200GMX10@24PCK" → 24 (ignore the X10 entirely)
KEY TEST: Is there an X-tier BEFORE the @?
YES → Case B (take only after @). NO → Case A (multiply all after @).

#### E. Multi-Number Grids — Default is NOT Multiplication; Table 4.3 Overrides ALWAYS Win (CRITICAL)

This has been checked directly against the verified master list (many SKUs per supplier, not
just one or two examples), and the result is clear: when a product's packing description has
**two or more numbers after the weight/size token**, the correct Packing Size is **almost always
just ONE of those numbers taken as-is — never multiply them together by default.** Which one
depends on the shape:

* **Flat sequence, no parentheses** (`[weight]X[tierA]X[tierB]`, e.g. `13GX8X15`) -> default to
  the LAST (rightmost) number.
  * "24 x 45g x 34" -> `24` is before the weight (discard) -> `34` is after the weight -> **34**
  * "45g x 34" -> `34` is after the weight -> **34**
  * "13GX8X15" (real example, MJ TIAN — "CHEEZELS ORIGINAL MULTIPACK 13GX8X15") -> **15** (NOT
    8 × 15 = 120)
  * "14GX8X30" (real example, MJ TIAN — "SUPER RING CHEESE" / "ORIENTAL ROTA PRAWN CRACKERS") ->
    **30** (NOT 8 × 30 = 240)
  * ⚠ **CAUTION — do not confuse a REPEATED weight with a second tier.** If the trailing
    number-with-unit is the SAME value as the weight already stated earlier in the description
    (e.g. "Cheezels Original **140g** 12 x **140g**" — "140g" is printed TWICE, once right after
    the product name and again at the end), that trailing repeat is NOT a second tier to fall
    back on — it is just the weight restated. In that case use the single number that sits
    between the two weight mentions (here, **12**) as the Packing Size, per the simple `[tier] x
    [weight]` pattern (Section 1D's very first example, "24 x 45g" -> 24) — do NOT take the
    trailing "140" as if this were a `13GX8X15`-style three-number grid.
    * "Cheezels Original 140g 12 x 140g" (real example, WEMBS) -> **12** (NOT 140 — this has been
      observed as a real extraction error: taking the repeated weight instead of the tier)
    * "Chipsmore Original 135g 24 x 135g" (real example, WEMBS) -> **24** (NOT 135)
    * "Chipsmore Original Mini 72g 48 x 72g" (real example, WEMBS) -> **48** (NOT 72)
* **Parenthesized sub-group** (`[outer] x ([inner] x [weight])`, e.g. `15 x (8 x 13g)`) ->
  default to the OUTER (leftmost, before the parenthesis) number — this is the OPPOSITE end from
  the flat-sequence case above, so don't conflate the two shapes.
  * "15 x (8 x 13g)" (real example, WEMBS — "Cheezels Original Mp") -> **15** (NOT 15 × 8 = 120)
  * "16 x (8 x 24g)" (real example, WEMBS — "Chipsmore ... Handy Mp") -> **16** (NOT 16 × 8 = 128)
  * "12 x (5's x 80g)" (real example, WEMBS — "Ibumie Dry Noodles") -> **12** (NOT 12 × 5 = 60)
  * "10 x (10 x 25g)" (real example, WEMBS — "Mamee Monster") -> **10** (NOT 10 × 10 = 100)

**A meaningful minority of specific SKUs genuinely DO need multiplication instead of this
default** — e.g. MJ TIAN's "TWISTIES KABOOM BBQ CURRY 13GX30X8" is verified at Packing Size
**240** (= 30 × 8), MJ TIAN's "twisties 60g" / "chipster 60g" families (e.g.
"TWISTIES TOMATO 60GX10X6" = 60, "TWISTIES CHIPSTER HOT & SPICY 60GX10X3" = 30) are verified to
need tierA × tierB, and several WEMBS SKUs (Halls xs, Ribena Pasttile, CDM Black Forest/Fruit &
Nut, Super Ring, Tiger (Small), Cheezels-60g/Twisties-60g non-MP lines) are verified to need
outer × inner. **None of this is predictable from the text pattern alone** — there is no
separator, suffix, or number-magnitude signal that reliably distinguishes these from the
"single number, no multiply" majority; both groups use identical-looking notation, sometimes on
the very same invoice. **This means: ALWAYS check Table 4.3 for the exact SKU FIRST, before
applying the default in this section.** If the SKU (or its brand/weight family) is listed in
Table 4.3, use that value — full stop, do not second-guess it against the default here. Only
fall back to the single-number default when Table 4.3 has no matching entry for that supplier.

⚠ **Specific known trouble spot — the flat `[weight]GX[tierA]X[tierB]` shape (no parentheses) is
where this default-vs-override mixup has been observed most often**, because the flat shape is
exactly the pattern this section's own default example uses, which pulls attention toward
applying the default even when a matching Table 4.3 row exists. Two concrete cases this has
gone wrong on before, to calibrate against: JB YAP "JACKER Potato Cheese/Original/BBQ/Seaweed/
Honey Butter/S. Cream 110g*14" must use Table 4.3's override (**36**), not this section's default
(14); JB YAP "CORNTOZ Smoky BBQZ/Hotz & Spicy 100g*10*5" must use Table 4.3's override (**50**),
not this section's default (5). Before finalizing Packing Size for ANY flat `[weight]GX[A]X[B]`
product, re-read Table 4.3 for that supplier one more time — it is very easy to skip this step
for exactly this shape.

* FOC DETECTION & ADJUSTED PACK PRICE:
PATTERN: FOC items appear as a DUPLICATE line with the same barcode/material number, but with Unit Price = 0.00 and a smaller quantity. This 0.00-priced duplicate is the FOC quantity — NOT a free product to be extracted separately.
STEP 1 — DETECT: If the same barcode name appears more than once and one of those rows has Unit Price = 0.00, treat the 0.00 row as FOC. Do NOT extract the 0.00 row as a separate product.
STEP 2 — MERGE: Combine both rows into one product entry.
* Paid Qty = quantity from the row with a real Unit Price
* FOC Qty = quantity from the 0.00 row
* Total Value = Value from the paid row only


STEP 3 — ADJUSTED PACK PRICE FORMULA:
Adjusted Pack Price = Total Value / (Paid Qty + FOC Qty)
Example from invoice:
Barcode 100541417, Paid Qty = 24, FOC Qty = 2, Total Value = 1,944.00
Adjusted Pack Price = 1,944.00 / (24 + 2) = 1,944.00 / 26 = 74.77
Example 2:
Barcode 100474283, Paid Qty = 12, FOC Qty = 1, Total Value = 604.44
Adjusted Pack Price = 604.44 / (12 + 1) = 604.44 / 13 = 46.50
IMPORTANT: If a product has NO 0.00 duplicate row, no FOC adjustment is made. Use Pack Price = U/Price × Packing Size as normal.

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
* Do not adjust, do not slice, do not round intermediate states, and do not use any hidden values. Use exactly what your eyes see in the unit price field.* *Note:* Use the raw, undiscounted Unit Price to find the "Stated Pack Price" before applying this formula.* *Example:* A supplier lists a product at a CTN Price of $10. The buyer purchases 10 CTNs ($100 total value) and receives 1 extra CTN for free (1 FOC). The adjusted Pack Price is calculated as `$100 / (10 + 1) = $9.09`.


* **DISCOUNTS — ALWAYS ZERO:** The "Disc" column must be completely ignored in all calculations. Treat it as if it does not exist on the page. Never multiply U/Price by (1 - disc%).
WRONG: 12.31 × 0.96 × 3 = 35.45 ← FORBIDDEN
CORRECT: 12.31 × 3 = 36.93 ← ONLY valid formula
* **FOC (Free of Charge) — APPLY THIS ADJUSTMENT:** If a FOC quantity is stated (e.g. buy 10 get 1 free), adjust the Pack Price as follows:
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
* **EXCHANGE RATE — MANDATORY CHECK, NEVER SKIP, AND DO NOT CONVERT PACK PRICE YOURSELF:** Before extracting a single price, check the invoice header/letterhead address and the price-column currency label (e.g. "RM", "MYR", "US$"). This is a required step, not optional.
* **`Pack Price` must ALWAYS be left in the ORIGINAL printed invoice currency.** Do not do any SGD conversion math yourself when filling in `Pack Price` — the downstream system does that conversion automatically by dividing `Pack Price` by `exchange_rate`. If you convert `Pack Price` to SGD yourself AND also provide an `exchange_rate`, the price gets converted TWICE and comes out wrong.
* If the document uses a foreign currency (e.g., USD, RM/MYR) — including when a Malaysian company address is printed but no rate is stated — you MUST look up the real-time conversion rate and set `exchange_rate` to it.
* **`exchange_rate` DIRECTION (this is the part that most often gets inverted):** `exchange_rate` must equal "how many units of the invoice's foreign currency equal 1 SGD" — e.g. for MYR this is roughly **3.1 to 3.5** (since 1 SGD ≈ 3.1-3.5 RM). It is **NEVER a value below 1** for a MYR invoice. If you find yourself about to write an `exchange_rate` less than 1 for a RM/MYR document (e.g. 0.31, which is the RM→SGD rate, the wrong direction), you have it backwards — invert it (1 / 0.31 ≈ 3.2) before writing it out.
* Defaulting `exchange_rate` to **1.0** is ONLY correct when the document is genuinely in SGD or the currency is truly unstated/undeterminable.
* **Known RM/MYR suppliers (verified from source invoices):** WEMBS MARKETING, MJ TIAN SDN. BHD. Treat any other supplier whose letterhead address is in Malaysia the same way — leave `Pack Price` in RM as printed, and set `exchange_rate` to the ~3.1-3.5 SGD→MYR rate.
* **ROBUST BARCODE EXTRACTION:** * Actively scan the row data and structural margins for any unbroken 8, 12, 13, or 14-digit numeric sequences (e.g., `8901396319702`, `309978695110`).
* Due to multi-page or shifting column OCR text wrapping, a barcode may appear slightly above, below, or offset from the main text string of the Product Description.
* Trace the horizontal table row strictly to locate and bind this number to the item. If and only if no valid digit chain can be identified anywhere within the item's row boundaries, return an empty string `""`.


* **MULTI-PAGE CHRONOLOGICAL DEDUPLICATION:** * Process all pages completely.
* If a product (matching by identical Barcode and Product Name) appears multiple times across different dates or pages with varying rates or prices, **deduplicate the list by prioritizing the latest date's transaction price**.
* Retain only the single entry representing the most recent pricing version found in the document, discarding older historical rates.

---

### 4. SUPPLIER-SPECIFIC PRICE INTERPRETATION RULES

These rules **override** the general Pack Price formula for the named suppliers. Match the detected
supplier against Table 4.1 before any price calculation, then check Table 4.3 for any
product/brand-level packing-size override on top of that. If the detected supplier is **not
listed** anywhere below, fall back to the general rules (Sections 1-2).

Legend for the "Price Basis" column in Table 4.1:
* **CTN_AS_PRINTED** — the printed Rate/U-Price column IS already the final CTN/Pack Price.
  `Pack Price = Price as printed.` Do NOT multiply by Packing Size.
* **UOM_CONDITIONAL** — depends on the UOM column per line item; see Rule 4.2.

---

#### 4.1 Supplier Price-Basis Table

| Supplier (match key) | Price Basis | Notes |
| --- | --- | --- |
| BISCOTTI TRADING PTE LTD | CTN_AS_PRINTED | |
| CAMMER INDUSTRIES | CTN_AS_PRINTED | |
| JB YAP | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| LIVER POOL | CTN_AS_PRINTED | |
| CANDY WORLD | CTN_AS_PRINTED, then × OUTCTN multiplier | See Table 4.3 (YAN YAN VANILLA, NUTELLA GO) |
| HOCK LEONG TECK KEE PTE LTD | CTN_AS_PRINTED | |
| POKKA | CTN_AS_PRINTED | **Verified pitfall:** "T/B POKKA LEMON/OOLONG TEA (250ML X 6S X 4)" -> Packing Size = **4** (the last number, per the Section 1E default) — this has been observed to get WRONGLY multiplied to 24 (6 × 4); do not multiply here, there is no override for this SKU. |
| SUNLIM | CTN_AS_PRINTED | |
| MJ TIAN | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| RAZON TRADING PTE LTD | CTN_AS_PRINTED | |
| SKY PLUS TRADING | CTN_AS_PRINTED | Packing size = first number in the dimension string (e.g. "4 x 6 x 250ml" -> 4) |
| TONG GARDEN | CTN_AS_PRINTED | ⚠ short match key — see "Open Questions" below re: full legal name `TONG GARDEN FOOD (SINGAPORE) PTE LTD` |
| U DISTRIBUTION | CTN_AS_PRINTED | |
| URC FOODS | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| TGS | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| SHENG SHENG FB INDUSTRIES PTE LTD | CTN_AS_PRINTED | (Longest-name extraction already applies globally, Rule 1). **Verified pitfall:** this supplier's invoices often print a leading case-count number directly before the volume, e.g. "15 X 500ml KANGSHIFU HONEY POMELO DRINK" — that leading "15" is a quantity prefix like any other (see Section 1 "QTY to be considered always as quantity instead of packing size") and must be discarded; do NOT use it as Packing Size. Since there is no other multiplier tier printed, fall back to the Section 1C drink-volume default for 500ml (**24**), not the printed "15". Verified against master list on 3 separate SKUs (Honey Pomelo Drink, Ice Black Tea, Cha Pai Pomelo Green Tea — all 24). **Second pitfall:** "115GX20X3B...GROUNDNUT 115G" -> Packing Size = **60** (= 20 × 3, tierA × tierB) — do NOT apply Section A's "outermost B-tier" rule here (which would wrongly give 3); this SKU needs multiplication instead. |
| SY FOODSTUFF | CTN_AS_PRINTED | ⚠ see "Open Questions" below re: `SY FOODS`. Product-level packing-size overrides in Table 4.3 |
| SY FOODS | CTN_AS_PRINTED | ⚠ see "Open Questions" below — same entity as `SY FOODSTUFF`? |
| WINSTAR MARKETING PTE LTD | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| HOUTEN | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| WEMBS MARKETING (canonical output name: `WEMBS MARKETING SDN. BHD.`, see Rule 4.4) | CTN_AS_PRINTED | Product-level packing-size overrides in Table 4.3 |
| MENG CHONG | CTN_AS_PRINTED, except one SKU — see Rule 4.5 | |
| BHAVNA PTE LTD | UOM_CONDITIONAL | See Rule 4.2. **Packing Size exception:** for this supplier specifically, whenever the Description has the shape `[weight/code] X [tierA] X [tierB]` (e.g. "CADBURY MILK MOULDED BAR 130GM X 12 X 6 ROAST ALMOND", "KINDER BUENO T6 X 11 X 4 CHOCOLATE"), ALWAYS multiply tierA × tierB — do NOT apply the Section 1E "last number only" default for this supplier. Verified against the master list across 9+ SKUs with zero exceptions (e.g. 12×6=72, 12×24=288, 10×24=240, 11×4=44, 15×8=120, 10×16=160, 12×20=240). This is a supplier-wide convention, unlike other suppliers where multiplication is a per-SKU exception. |
| PYS DISTRIBUTION PTE LTD | UOM_CONDITIONAL | See Rule 4.2 |

---

#### 4.2 UOM-Conditional Rule (BHAVNA PTE LTD & PYS DISTRIBUTION PTE LTD only)

Inspect the **UOM (Unit of Measure) column** on each line item:

* If UOM = **CTN** → The printed price **is already the CTN Price**. `Pack Price = Price as printed.`
* If UOM = **PCS** → The printed price is the per-piece price AND the CTN price are the **same**. `Pack Price = Price as printed. Packing Size = 1.`

---

#### 4.3 Product / Brand Packing-Size Overrides

Each row is scoped ONLY to the supplier in the first column — the same brand/product bought from a
different supplier does NOT get this override; it falls back to the general packing-size rules
(Section 1).

| Applies to Supplier | Product / Brand keyword | Packing Size | Notes |
| --- | --- | --- | --- |
| CANDY WORLD | YAN YAN VANILLA 10X50G 44G (CUP) (No Return) 8 OUTCTN | — | Pack Price = printed price × 8 (outctn), e.g. 7.7 × 8 = 61.6 |
| CANDY WORLD | NUTELLA GO 12X48G NEW (no return) (80050100) 4 Outctn | — | Pack Price = printed price × 4 (outctn), e.g. 19 × 4 = 76 |
| MJ TIAN | SUPER RING CHEESE 14GX8X30 | 30 | Take the biggest number |
| MJ TIAN | SOFTLAN SPRING FRESH 1.6LX8 | 16 | Verified against master list. NOTE: this does NOT extend to other Softlan flavors — SOFTLAN FLORAL FANTASY 1.6LX8 and SOFTLAN LAVENDER FRESH 1.6X8 are verified at Packing Size 8 (the general default, last-number-only), despite printing the same "1.6LX8" notation and the same price as Spring Fresh. Match this override on the exact flavor "SPRING FRESH" only. |
| MJ TIAN | twisties 60g (e.g. TWISTIES KABOOM BBQ CURRY 60GX10X6) or cheezels 60g (e.g. CHEEZELS BBQ CHEESE 60GX10X6, CHEEZELS ORIGINAL 60GMX10X6) | 60 | Verified against master list: tierA × tierB (10 × 6) |
| MJ TIAN | chipster 60g (e.g. TWISTIES CHIPSTER HOT & SPICY/FLAMING BBQ/SOUR CREAM & ONION 60GX10X3) — takes priority over the "twisties 60g" row above when a product matches both | 30 | Verified against master list: tierA × tierB (10 × 3) |
| MJ TIAN | MAGGI HOT CUP | 54 | |
| MJ TIAN | TWISTIES KABOOM BBQ CURRY 13GX30X8 | 240 | Verified against master list: 30 × 8. This is a genuine exception to the Section 1E default (last number only) — do not generalize it to other 13G/14G-prefixed products in this invoice (e.g. CHEEZELS ORIGINAL MULTIPACK 13GX8X15 is verified at 15, NOT 8×15). |
| SKY PLUS TRADING | Yeo's Lychee 4 x 6 x 250ml | 4 | First number in the dimension string |
| SKY PLUS TRADING | Maggi Hot Cup (any flavor, e.g. "Maggi Hot Cup Curry 9 (6 x 58g)", "Maggi Hot Cup Tom Yam 9(6 x 60g)") | 54 | Verified against master list: 6 × 9. This overrides the supplier's general "first number" rule above — cross-verified, MJ TIAN's Maggi Hot Cup lines need the same 6 × 9 = 54 multiplication. |
| URC FOODS | ROLLER COASTER (any flavor, e.g. CHEESE/BBQ/ORIGINAL) 100GX14SX1 CAN SG | 14 | Not scoped to CHEESE flavor only |
| URC FOODS | PIATTOS (any flavor) 85Gx10x3 | 30 | Verified against master list: 10 × 3 |
| URC FOODS | Chippy BBQ 110Gx10x3 | 30 | Verified against master list: 10 × 3 |
| URC FOODS | C2 (any flavor) 455 ml x 6 x 4 (SG) | 24 | Verified against master list: 6 × 4 |
| WINSTAR MARKETING PTE LTD | IKA'S KARA SQUID HONEY 6'S / 5Gx6'Sx12PKTSx4BAG | 48 | 12 × 4 |
| HOUTEN | (HOUTEN BRAND) Chilli Tapioca Chips 1bag x 20pkts x 35g x 8s | 20 | |
| WEMBS MARKETING | twisties 60g (any flavor, e.g. Flaming Cheese/Kaboom BBQ Curry/Roast Chicken Dance/Cheeky Cheddar Cheese/Cherry Tomato Bomb 60g) — does NOT include "...MP" suffixed SKUs like "Cheeky Cheddar Cheese MP". **If the product is a "Chipster" flavor, use the "chipster 60g" row below instead — it takes priority over this row when both match.** | 60 | |
| WEMBS MARKETING | chipster 60g (e.g. "Twisties Chipster Flaming BBQ/Original/SC & Onion 60g") — takes priority over the "twisties 60g" row above when a product matches both | 30 | |
| WEMBS MARKETING | Any TIGER product marked "(Small)" that is 53.2g — match on the concept (Tiger + Small + 53.2g), not on the literal substring "tiger 53.2g", since the printed text usually has other words in between (e.g. "Tiger Chocolate (Small) 8 x (12 x 53.2g)") | 96 | Verified against master list: 8 × 12 |
| WEMBS MARKETING | ribena pastille / ribena pasttile | 288 | |
| WEMBS MARKETING | halls xs | 288 | |
| WEMBS MARKETING | CDM Black Forest 130g / CDM Fruit & Nut 130g | 72 | Verified against master list: 6 × 12 |
| WEMBS MARKETING | Cheezels Bbq Cheese 60g / Cheezels Original 60g — does NOT include "Cheezels Original Mp" (that one is verified at 15, the general default) | 60 | Verified against master list: 6 × 10 |
| WEMBS MARKETING | Super Ring | 60 | Verified against master list: 6 × 10 |
| JB YAP | KHY, YELLOW SPICY, JOMEI BIG SPICY | 144 | |
| JB YAP | kuaci 40g | 150 | |
| JB YAP | joystix (all SKUs) | 72 | |
| JB YAP | mamee cup | 64 | |
| JB YAP | mentos | 48 | |
| JB YAP | SHOYUEMI or MIMI, any flavor, WEIGHT-GATED: apply ONLY when the weight is 50g or 60g (e.g. "SHOYUEMI Curry/Black Pepper/Spicy/Original 50g*10*6", "MIMI 60g*10*6"). The flavor name does NOT matter — the SAME flavor word can appear at both a covered and uncovered weight (e.g. "SHOYUEMI Black Pepper 50g*10*6" needs this override, but "SHOYUEMI Black Pepper 14g*8*24" does NOT). Do NOT apply when weight is 14g (verified at 24, the default) or when the brand is "SNEK KU" (a different brand entirely, e.g. "SNEK KU Mimi/Tam Tam (20g*8)*24" — verified at 24, the default, regardless of weight) | 60 | |
| JB YAP | corntoz — plain/Cheesey Pizza variants (e.g. "CORNTOZ 100g", "CORNTOZ Cheesey Pizza 80g*10*5") | 50 | Verified against master list. Does NOT include "CORNTOZ F/P ..." variants (Smoky BBQ/Chili Cheez/Hotz & Spicy) — those are verified at 10, the general default (last number) — do not apply this override to any "CORNTOZ F/P" product. |
| JB YAP | dan hua cake | 100 | |
| JB YAP | pagoda | 60 | |
| JB YAP | khy abang latio stick | 144 | |
| JB YAP | KHY Mini Latiao 72*12 | 144 | Verified against master list: 72 × 12. Unusual case — neither "72" nor "12" has a unit suffix (no "g"/"ml"), so the normal "first number is the weight" heuristic doesn't apply here; both numbers are packing tiers. |
| JB YAP | himalaya | 144 | |
| JB YAP | woods | 270 | |
| JB YAP | jch meishija | 48 | |
| JB YAP | ejh (may appear at the END of the description rather than the start, e.g. "55g*16*5 EJH Vita Ball" — still apply the override; do not skip it just because "EJH" isn't the first word) | 80 | |
| JB YAP | Plain "TAM TAM" (JB YAP's own line, any weight — e.g. "TAM TAM 60g*10*6") — does NOT include "TAM TAM Chill Crab" flavor (verified at 6, the default) and does NOT include "SNEK KU Tam Tam" (a different brand, verified at 24, the default regardless of weight) | 60 | |
| JB YAP | dahfa fish fillet — ONLY the 50g variant. The 280g variant ("DAHFA Fish Fillet 280g*20") is verified at 20, the general default — do not apply this override there just because the product name contains "dahfa fish fillet". | 80 | |
| JB YAP | DOLPHIN Konjac Drink (e.g. "DOLPHIN Konjac Drink Grape/Lychee 180g*10*4") | 40 | Verified against master list: 10 × 4. Does NOT extend to "DOLPHIN Konjac Jelly" or "DOLPHIN Jelly With Nata" — those are verified at 24, the general default (last number) — do not apply this override to any Konjac Jelly / Jelly With Nata product. |
| JB YAP | ylf | 144 | |
| JB YAP | jacker POTATO specifically — ANY "JACKER Potato [flavor]" product regardless of which weight/tier numbers are printed (verified across multiple notations: "110g*14" AND "(60g*12)*3" both need this same override — e.g. Cheese/Original/Seaweed/Honey Butter/BBQ/S. Cream/Tomato/Natural/H & S). **This override has been observed to be skipped even when it clearly applies — double-check every "JACKER Potato" line against this row before falling back to the Section 1E default.** | 36 | Verified against master list. Does NOT extend to other Jacker sub-lines — "JACKER Wafer Cube" (Hazelnut/Peanut/Choco) is verified at 30 (the general default, no override) — do not apply this row to Wafer Cube. |
| JB YAP | BIKA Ayam (chicken) flavor specifically, e.g. "BIKA Ayam M/H 60g*10*6" | 60 | Verified against master list: 10 × 6. Does NOT extend to "BIKA SEAFOOD Hot&Spicy" (verified at 6, the general default) or other non-Ayam Bika flavors — only Ayam is confirmed. |
| JB YAP | "T/fish N/crisp Peanut Cdy" (Peanut Candy) — this line's Description cell has a stray "RM2.80" price fragment glued to the front, e.g. "RM2.80*12*12 T/fish N/crisp Peanut Cdy 8"; ignore the leading "RM2.80" price fragment and use the two tier numbers that follow it | 144 | Verified against master list: 12 × 12 |
| JB YAP | double decker | 50 | |
| JB YAP | HS/Wang Wang Ball Cake 45g*10*4 | 40 | Verified against master list: 10 × 4 |
| TGS | ORIENTAL CHEESE BALL 6X10X60G | 60 | Verified against master list: 10 × 6 |
| WENKEN | 3 Legs CW 200ml 8 x 6's x 200ml (1 ctn x 8 clusters x 6's x 200ml) | 8 | Verified against master list: the first number (8 = clusters per carton per the invoice's own explanatory note), NOT 8 × 6 = 48. |
| YHS | 250ML TB YEOS F.HARVEST GT HORSE 4X6 SG | 4 | Verified against master list: the first number, NOT 4 × 6 = 24 |
| SY FOODSTUFF / SY FOODS | CADBURY HAZELNUT BAR 130G X 12 X 6 | 72 | Verified against master list: 12 × 6. Same convention as Bhavna's Cadbury lines (Rule 4.1) — if other Cadbury SKUs from this supplier show the same "[weight]G X tierA X tierB" shape, multiply tierA × tierB rather than using the Section 1E default. |
| SY FOODSTUFF / SY FOODS | MAGGI CURRY MEE / MAGGI CHICKEN MEE 12 X 5PKT | 12 | Verified against master list: the first number, NOT tierA × tierB (would be wrong at 60). This is a different Maggi product line from MJ TIAN/SKY PLUS's "Maggi Hot Cup" (which does need multiplication, =54) — do not conflate the two just because both are Maggi-branded. |

---

#### 4.4 Supplier Name Canonicalization

If one of these suppliers is found, always use this exact string as the output `supplier` value,
regardless of how it's abbreviated on the document:

* WEMBS → `"WEMBS MARKETING SDN. BHD."`

---

#### 4.5 MENG CHONG — Special Fix

For the product matching **"60GMSX5PX6B MAMA CREAMY SHRIMP TOM YAM NOODLES"**:

* Configuration `60GMSX5PX6B` → Packing Size = **6** (outermost B tier)
* Flag this product with a note: `"price_requires_manual_review": true`
* Apply the CTN price rule (price as printed = CTN price) for all other MENG CHONG products.

⚠ This flag is not currently in the OUTPUT FORMAT schema below and is not read by the app — see
"Open Questions".

---

#### 4.6 Priority Order

When a supplier match is found in this section, these rules take precedence in this order:

1. Product/brand packing-size override (Table 4.3) — overrides the general packing-size extraction (Section 1)
2. Supplier price-basis rule (Table 4.1 / 4.2)
3. FOC adjustment (Section 2)
4. General Pack Price formula (Section 2)

---

#### Open Questions (flagged, not yet resolved — do not silently guess)

* Is `SY FOODSTUFF` the same legal entity as `SY FOODS`? They currently have separate, inconsistent
  rule entries.
* Should `TONG GARDEN` in Table 4.1 be the short form, or the full legal name
  `TONG GARDEN FOOD (SINGAPORE) PTE LTD` that Rule 3's "Supplier Name Resolution" would otherwise
  produce via Google Search?
* Should `price_requires_manual_review` (4.5) be added to the OUTPUT FORMAT schema and read by
  `po_upload/services_.py`, or dropped from the prompt since it currently has no effect?

### OUTPUT FORMAT (JSON ONLY)

```json
{
    "supplier": "string", 
    "exchange_rate": 1.0, 
    "products": [
        {
            "Barcode": "string", 
            "Product Name": "string — the COMPLETE Description cell text verbatim, including the trailing weight/quantity/dimension descriptor (e.g. '18 x 140g') — do NOT drop that suffix even though Packing Size below also captures it numerically; preserve all special chars verbatim, including *; do NOT include the barcode/article-number digit string here even if printed adjacent to the description — that belongs ONLY in Barcode below", 
            "Packing Size": 1, 
            "Pack Price": 0.0, 
            "Selling Price": 0.0, 
            "Promotion Price": 0.0
        }
    ]
}

```
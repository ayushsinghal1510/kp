# Integrated Data Extraction

Extract product pricing information from the attached file with absolute precision.

### CRITICAL EXTRACTION RULES

1. **STRICT DATA INTEGRITY:** Only extract data that is visually present unless a specific calculation is requested below. Do NOT invent or assume values.
2. **YOU DO NOT COMPUTE THE PACKING SIZE.** A downstream calculator does that. Your only job for packing is to (a) keep the product description clean and (b) emit a **Packing Size String** that the calculator can evaluate. See "PACKING SIZE STRING" below.
3. **DO NOT STRIP WEIGHT PREFIXES WITHOUT `@`.** A string like `240GM10X24PCKS` (no `@` present) must NOT be split into `10 x 24PCKS`. The `@` normalisation rule in Section 2 requires a literal `@` character. Without it, the fused prefix `240GM10` is an opaque token — emit it with `igno` if supplier rules require, otherwise pass the whole string through unchanged.

---

⚠️ SPECIAL CHARACTER PRESERVATION (MANDATORY):
Preserve ALL characters exactly as printed in the source document within the
"Product Description" field. This includes asterisks (*), plus signs (+),
parentheses, slashes, and any other symbols. Never strip, escape, or replace
any character for formatting reasons.

---

### 1. PRODUCT DESCRIPTION (ROOT NAME ONLY)

* Extract the **longest, most descriptive product name** visually present — flavour, brand, variant, everything that identifies the product.
* **Strip the packing/size configuration out of this field.** The packing configuration (the `12x1.2L`, `55GMX5PX6B`, `6 x (12 x 130g)` part) goes into the separate `Packing Size String` field, NOT here.
* Keep weight/flavour descriptors that are part of the product identity (e.g. a 60g variant) but remove the trailing carton/pack multiplier notation.
  * `BAKE STORY KOKOPIE CHOCOLATE FLAVOUR 20Gx10PCSx9BAGS` → Description: `BAKE STORY KOKOPIE CHOCOLATE FLAVOUR` , Packing Size String: `20Gx10PCSx9BAGS`
  * `100 PLUS 12x1.2L` → Description: `100 PLUS` , Packing Size String: `12x1.2L`
* The clean root description is what we use to match the same product across different suppliers, so keep it consistent and free of pack notation.

---

### 2. PACKING SIZE STRING (DO NOT COMPUTE — EMIT A STRING)

Emit the packing configuration as a **string** the calculator will evaluate. **Never output a final integer** — output the expression.

#### How the calculator reads your string (so you emit the right one)

* Delimiter between tiers is **`x`**. Always normalise `*`, `X`, `·`, grids and `@` into `x`-separated form.
* **Keep the unit letters attached to each number** so the calculator can tell a weight from a pack tier:
  * Weight/volume units (`g, gm, gms, kg, mg, ml, l, cl, oz`) → that number is NOT a count (becomes 1).
  * Packaging tiers, outer-to-inner: **B** (`b, bag, ctn, carton, outctn`) > **P** (`p, pk, pkt, pkts, pack, pck, dp`) > **S** (`s, pcs, pc, sachet`). The **highest tier present wins**; lower lettered tiers become 1.
  * A **bare number** (no unit) always counts, and so does the **B** tier.
  * An **S** number only counts if there is no bare number, B or P beside it.
  * **Brackets** multiply through, UNLESS the bracket contains a sachet (`s`) tier — then that bracket is inner packaging and becomes 1.

#### Your normalisation duties (turn messy invoice text into a clean string)

1. **Drop the order QUANTITY.** A number that is the quantity ordered is NOT packing. Emit only the packing configuration.
   * `24 x 45g x 34` (24 = order qty) → emit `45g x 34`
2. **Resolve `@` — only when `@` is literally present in the string:**
   * `[weight]@[tierA]x[tierB]` (no x before @) → multiply all → emit `tierA x tierB`. e.g. `240GM@10X12PCKS` → `10 x 12PCKS`
   * `[weight]x[tierA]@[tierB]` (an x-tier before @) → @ is a hard reset, keep only after @ → emit `tierB`. e.g. `200GMX10@12PCK` → `12PCK`
   * ⚠️ **`@` MUST be literally in the string.** Do NOT apply this rule by analogy. `240GM10X24PCKS` has no `@` — it is NOT the same as `240GM@10X24PCKS` and must NOT be split into `10 x 24PCKS`. Treat the fused `<weight><unit><digits>` prefix as a single opaque token.
3. **`+` is NOT a delimiter.** The calculator cannot read a `7+3`-style expression, so any such segment collapses to **1**. If that segment is not the packing count, just keep it (`(7+3) x 12` → calculator gives 12). If it IS the intended count, resolve it yourself and emit the number.
4. **REDUNDANT TRAILING B-TIER AFTER A BRACKET — use `igno`.** When the pattern is `N (MPKT × Wg) NCTN` (a bare outer count, a bracket, then a B-tier token with the **same value** N), the trailing B-tier token is a redundant restatement of the outer carton count. The calculator would double-count it (bare × group × B = N × M × N). Fix: append `igno` to the trailing B-tier token so the calculator discards it. Keep the rest of the string unchanged. e.g. `4 (20PKT × 125G) 4PKGCTN` → emit `4 (20PKT X 125G) 4PKGCTNigno` (= 4 × 20 × 1 = **80**).
5. **OUTCTN / PKGCTN count that appears separately — always include it, even after a label bracket.** When an outer-carton count `M OUTCTN` appears at the end of the raw text — whether directly after the weight (`NxWg M OUTCTN`) or after a descriptive/label bracket (`NxWg (Label) M OUTCTN`) — do NOT drop it. The calculator reads `M` as a bare multiplier and the label bracket as 1 (no digits), giving N × 1 × 1 × M = N×M. Emit the whole string unchanged.
   * `12X48G 4 Outctn` → emit unchanged → 12 × 1 × 4 = **48**
   * `10X50G44G (No Return) 8 OUTCTN` → emit unchanged → 10 × 1 × (1) × 8 = **80**
   Dropping the trailing count produces only N (e.g. 10 or 12 — wrong).
6. **Drink volume defaults — bake the count INTO the string** (the calculator has no volume table). Use unless an explicit count is printed:
   * Canned/bottled drink 250ml–500ml → emit `24 x [volume]` (e.g. `24 x 300ml`)
   * 1000ml–1500ml → emit `12 x [volume]`
   * Tetra pack [pkt] → emit `4 x [volume]`
   * Ribena 850ml → `6 x 850ml` ; Ribena 600ml → `12 x 600ml`
   * If an explicit count IS printed, use it: `qoo white grape 300ml x 12` → emit `300ml x 12`
7. **Supplier / SKU specials — emit the string that yields the intended number** (see Section 5). e.g. twister 60g → emit `60` ; twister + chipster 60g → emit `30`.
8. **`igno` — force-ignore a leading segment.** Append the literal letters `igno` directly to a number (no space) to tell the calculator to discard that atom entirely (it becomes 1). Use this when a leading weight/count segment would otherwise be picked up as a bare multiplier but must be skipped.
   * `240ignoX24PCKS` → calculator sees (1) × 24 = **24** (the `240igno` atom is disqualified)
   * `100ignoX10X24PCKS` → 1 × 10 × 24 = **240**
   Only emit `igno` when a supplier-specific rule (Section 5) explicitly requires it.

#### Reference (raw → string you emit → calculator result)

* `24 x 45g` → `24 x 45g` → 24
* `24s x 45g` → `24s x 45g` → 24
* `45g x 34` → `45g x 34` → 34
* `24 x (12 x 20s)` → `24 x (12 x 20s)` → 24
* `55GMX5PX6B` → `55GMx5Px6B` → 6 (B wins)
* `6SX7PX8B` → `6Sx7Px8B` → 8 (B wins)
* `120g*6*8` → `120g x 6 x 8` → 48
* `(7+3) x 12` → `(7+3) x 12` → 12 (the `7+3` segment is unknown → 1)
* `10s` → `10s` → 10
* `CWM CHERRY PLUM 10X80G` → `10 x 80G` → 10
* `YAN YAN 10X50G44G 8 OUTCTN` → `10 x 8OUTCTN` → 80
* `CDM Black Forest 6 x (12 x 130g)` → `6 x (12 x 130g)` → 72
* `Super Ring 6 x (10 x 60g)` → `6 x (10 x 60g)` → 60
* `CHEWY GINGER 4 (20PKT X 125G) 4PKGCTN` → `4 (20PKT X 125G) 4PKGCTNigno` → 80  ← trailing `4PKGCTN` is the same carton count as the outer `4`; `igno` prevents double-counting
* `NUTELLA & GO 12X48G 4 Outctn` → `12X48G 4 Outctn` (unchanged) → 48  ← `4` is a bare multiplier; `Outctn` has no digits so it's ignored by the tokeniser; 12 × 1 × 4 = 48
* `YAN YAN CHOCOLATE 10X50G44G (No Return) 8 OUTCTN` → `10X50G44G (No Return) 8 OUTCTN` (unchanged) → 80  ← label bracket has no digits → 1; `8` is a bare multiplier; 10 × 1 × 1 × 8 = 80
* `POLA SNACK 10X(10x15g)` (CANDY WORLD) → `10X(10ignox15g)` → 10  ← bracket is per-pack composition; inner `10` gets `igno`; 10 × (1 × 1) = 10
* `240 x 12x75g` (DP PETS) → `240 x 12ignox75g` → 240  ← `12x75g` is inner-pack composition; `12` gets `igno`; 240 × 1 × 1 = 240
* `240GM@10X12PCKS` → `10 x 12PCKS` → 120
* `200GMX10@12PCK` → `12PCK` → 12
* `240GM10X24PCKS` (BISCOTTI TRADING) → `240GM10ignoX24PCKS` → 24 (**not** `10 x 24PCKS`)
* `200GM10X12PCK` (BISCOTTI TRADING) → `200GM10ignoX12PCK` → 12 (**not** `10 x 12PCK`)

---

### 3. PACK PRICE / CARTON PRICE CALCULATION (NO MULTIPLICATION)

There is no concept of "unit price" — any price column you see (Rate, U/Price, Unit Price, Price) is already the Pack Price. Extract it as-is. Never multiply by packing size.

* **CRITICAL MANDATE:** You are strictly forbidden from looking at the "Total" or "Total RM" columns to calculate or cross-verify prices. Do NOT reverse-engineer prices using row totals or overall quantities.
* **DISCOUNTS — ALWAYS ZERO:** Ignore the "Disc" column entirely. Never apply a discount percentage to any price.
* **THE ONLY VALID PRICE RULE:** `Pack Price = Price as printed in the document.` No multiplication. No formula. Whatever number appears in the price column is the Pack Price.
* **FOC (Free of Charge):** An FOC line is a DUPLICATE of the same barcode with Unit Price = 0.00 and a smaller qty. Do NOT extract it as a separate product. Merge, and:
  * `Adjusted Pack Price = Total Value / (Paid Qty + FOC Qty)`
  * e.g. Barcode 100541417, Paid Qty 24, FOC Qty 2, Total Value 1,944.00 → `1944 / 26 = 74.77`
  * If there is no 0.00 duplicate row, make no FOC adjustment.

---

### 4. GENERAL TIER & DATA RULES

* **SUPPLIER NAME RESOLUTION (CRITICAL):** Identify the issuing seller via 'Supplier:', 'Sold By:', or the letterhead. Extract the **longest, most complete legal name**. If abbreviated/inconsistent (e.g. "Tong Garden Food (S) Pte Ltd"), **perform a live Google Search** to find the full registered name (e.g. "TONG GARDEN FOOD (SINGAPORE) PTE LTD"). Default to **'Unknown'** if unidentifiable.
* **MISSING PRICES:** Selling Price omitted → **0.0**. Promotion Price omitted → **0.0** (do NOT mirror the selling price).
* **ZERO PRICES:** Include items even if the extracted price is 0.00.
* **EXCHANGE RATE:** Emit `exchange_rate` as the number of **foreign currency units that equal 1 SGD** (the system divides all prices by this number to convert to SGD). Steps: (1) Identify the invoice currency. (2) If SGD or unstated → emit `1.0` (no conversion). (3) If a foreign currency (RM/MYR, USD, etc.) is present and no explicit rate is printed, look up the real-time rate for **1 SGD = ? [foreign]** and emit that number. Example: if 1 SGD = 3.50 MYR, emit `3.5` — the system then does `RM_price / 3.5 = SGD_price`. (Wembs invoices are in RM — apply this rule.)
* **ROBUST BARCODE EXTRACTION:** Scan rows and margins for unbroken 8/12/13/14-digit numeric sequences. A barcode may sit slightly above/below/offset from the description due to OCR wrapping — bind it to the correct row. If none exists in the row, return `""`.
* **MULTI-PAGE CHRONOLOGICAL DEDUPLICATION:** Process all pages. If the same product (identical Barcode + Description) appears multiple times with varying prices, **keep only the latest date's price**, discard older ones.

---

### 5. SUPPLIER-SPECIFIC RULES

Match the detected supplier against this table BEFORE pricing. These override the general Pack Price formula. Packing guidance here means **emit the corresponding Packing Size String** (Section 2) — still never a bare integer.

#### A. Supplier-Specific Packing Rules

These suppliers have special rules for the **Packing Size String** field only. Price is always as printed (global rule — no multiplication).

| Supplier | Packing / Additional Rule |
| --- | --- |
| BISCOTTI TRADING PTE LTD | **⚠️ PACKING OVERRIDE — READ CAREFULLY:** For any packing string that looks like `<weight><unit><number>X<count><P-tier>` (e.g. raw text `240GM10X24PCKS` or `200GM10X12PCK`): you MUST emit it with `igno` fused onto the middle number — `240GM10ignoX24PCKS`, `200GM10ignoX12PCK`. **FORBIDDEN outputs:** `10 x 24PCKS`, `10 x 12PCK`, or any form that splits the leading segment away. The `igno` suffix is mandatory; omitting it causes the calculator to multiply the wrong numbers. |
| CANDY WORLD | Any product with trailing `M OUTCTN` (with or without a label bracket before it): emit the string unchanged — the calculator handles it. Examples: `YAN YAN VANILLA 10X50G 44G (CUP) 8 OUTCTN` → emit unchanged (=80) / `YAN YAN CHOCOLATE 10X50G44G (No Return) 8 OUTCTN` → emit unchanged (=80) / `NUTELLA & GO 12X48G 4 Outctn` → emit unchanged (=48) / `CHEWY GINGER 4 (20PKT X 125G) 4PKGCTN` → emit `4 (20PKT X 125G) 4PKGCTNigno` (=80); trailing `4PKGCTN` is redundant with outer `4` — append `igno` to it / **`NX(Nxwg)` pattern** (e.g. `POLA SNACK 10X(10x15g)`): the bracket is per-pack composition — append `igno` to the inner count: emit `10X(10ignox15g)` (=10) |
| DP PETS | When packing is `A x BxWg` (outer count × inner-count × weight), the inner count B is per-pack composition — append `igno` to it. e.g. `240 x 12x75g` → emit `240 x 12ignox75g` (=240). |
| MJ TIAN | `SUPER RING CHEESE 14GX8X30` → String `14G x 8 x 30` (=30, biggest). `SOFTLAN SPRING FRESH 16LX8` → String `16L x 8` (=8). twisties 60g → String `60`; chipster 60g → String `30`; `TWISTIES KABOOM BBQ CURRY 60GX10X6` → String `60`. MAGGI HOT CUP → String `54` |
| SKY PLUS TRADING | `Yeo's Lychee 4 x 6 x 250ml` → String `4`. `Maggi Hot Cup Tom Yam 9(6 x 60g)` → String `9 x 6` (=54). `MAGGI CHICKEN MEE 12 X 5PKT` → emit `12` |
| SY | `MAGGI CURRY MEE 12 X 5PKT` → String `12`. Drinks: canned/bottle 250-450ml → `24 x [vol]`; 500ml → `24 x [vol]`; 1000-1500ml → `12 x [vol]` unless an explicit count is printed (`qoo white grape 300ml x 12` → `300ml x 12`) |
| URC FOODS | `ROLLER COASTER CHEESE 100GX14SX1 CAN SG` → String `100G x 14S x 1` (=14) |
| TGS | `MAMEE MONSTER F/P BBQ 10(10X25G)` → String `10` |
| SHENG SHENG FB INDUSTRIES PTE LTD | Longest, most complete description |
| SY FOODSTUFF | Combine the description column and the packing column; description = first column, Packing Size String = the packing column |
| WINSTAR MARKETING PTE LTD | `IKA'S KARA SQUID HONEY 5Gx6'Sx12PKTSx4BAG` → String `5G x 6S x 12PKTS x 4BAG` (=48, B wins) |
| HOUTEN | `(HOUTEN BRAND) Chilli Tapioca Chips 1bag x 20pkts x 35g x 8s` → emit so packing = 20 → String `20pkts` |
| WEMBS MARKETING | twisties 60g → `60`; chipster 60g → `30`; tiger 53.2g → `96`; ribena pastille → `288`; halls xs → `288`; `CDM Black Forest 6 x (12 x 130g)` → `6 x (12 x 130g)` (=72); `Super Ring 6 x (10 x 60g)` → `6 x (10 x 60g)` (=60) |

#### Supplier Abbreviations
If found, keep this exact supplier name:
* WEMBS → `WEMBS MARKETING SDN. BHD.`

#### B. UOM-Conditional Suppliers (BHAVNA PTE. LTD & PYS DISTRIBUTION PTE LTD)

Inspect the **UOM** column per line:
* UOM = **CTN** → printed price is already the CTN Price. `Pack Price = Price as printed.`
* UOM = **PCS** → printed price is per-piece AND the CTN price. `Pack Price = Price as printed. Packing Size String = "1".`

#### C. MENG CHONG
* `60GMSX5PX6B MAMA CREAMY SHRIMP TOM YAM NOODLES` → Packing Size String `60GMS x 5P x 6B` (=6, B wins). Flag `"price_requires_manual_review": true`.
* CTN price rule (price as printed) for all other MENG CHONG products.

#### D. JB YAP — fixed packing strings
Emit these as the Packing Size String: KHY/YELLOW SPICY/JOMEI BIG SPICY → `144`; bika 60g → `60`; kuaci 40g → `150`; joystix → `72`; mamee cup → `64`; mentos → `48`; shoyuemi/mimi tam tam 50g/60g → `60`; corntoz 100g → `50`; dan hua cake → `100`; pagoda → `60`; khy abang latio stick → `144`; himalaya → `144`; woods → `270`; jch meishija → `48`; ejh → `80`; tam tam 70g → `60`; dahfa fish fillet 50g → `80`; dolphin → `40`; ylf → `144`; jacker → `36`; double decker → `50`; Lemon Tablets → `400`.

#### Priority Order
1. Supplier-specific rule (this section)
2. FOC adjustment (Section 3)
3. General Pack Price formula (Section 3)

If the detected supplier is **not listed**, fall back to the general rules.

---

### OUTPUT FORMAT (JSON ONLY)

```json
{
    "supplier": "string",
    "exchange_rate": 1.0,
    "products": [
        {
            "Barcode": "string",
            "Product Description": "string — ROOT product name, NO packing/size notation",
            "Packing Size String": "string — canonical packing expression, e.g. \"55GMx5Px6B\" or \"24 x 300ml\". NEVER a bare computed integer unless the rule says so.",
            "Pack Price": 0.0,
            "Selling Price": 0.0,
            "Promotion Price": 0.0
        }
    ]
}
```

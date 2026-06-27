import re
import json
import polars as pl
import streamlit as st

from typing import Any
from google.genai import types

from rpoc.pages_.new_master_list.services_ import (
    NML_CSV_PATH,
    NML_COLUMNS,
    split_product_names_with_groq,
    load_nml_csv,
    save_nml_csv,
)


# ── Load helpers ──────────────────────────────────────────────────────────────

def get_supplier_list() -> list[str]:
    df: pl.DataFrame = load_nml_csv()
    if "Supplier" not in df.columns or df.is_empty():
        return []
    suppliers: list[str] = (
        df.select("Supplier")
        .drop_nulls()
        .filter(pl.col("Supplier").str.strip_chars() != "")
        .unique()
        .sort("Supplier")
        .get_column("Supplier")
        .to_list()
    )
    return suppliers


def get_supplier_df_csv(supplier: str) -> str:
    """Return a CSV string of all rows for the given supplier."""
    df: pl.DataFrame = load_nml_csv()
    filtered: pl.DataFrame = df.filter(
        pl.col("Supplier").str.strip_chars().str.to_lowercase()
        == supplier.strip().lower()
    )
    return filtered.write_csv()


# ── Gemini: analyse invoice against supplier catalogue ────────────────────────

def analyse_invoice_with_gemini(
    pdf_bytes: bytes,
    pdf_mime_type: str,
    supplier_csv: str,
    supplier_name: str,
) -> dict[str, Any]:
    """
    Sends the supplier's existing product catalogue (CSV) + the invoice PDF to
    Gemini.  Gemini returns a JSON with three keys:

    {
      "updates": [
        {
          "csv_product_name": "<exact name from the CSV>",
          "old_price": <float>,
          "new_price": <float>
        }
      ],
      "new_products": [
        {
          "product_name": "<name as it appears on the invoice>",
          "packing_price": <float>,
          "inferred_packing_size": <int/float>,
          "inference_reason": "<short explanation>"
        }
      ],
      "unchanged": ["<csv_product_name>", ...]
    }
    """

    system_prompt: str = f"""
You are an expert retail inventory analyst for supplier "{supplier_name}".

You will receive:
1. A CSV of the supplier's existing product catalogue with columns:
   Product Name | Processed Product Name | Packing Style | Packing Size | Packing Price | Supplier
   - Packing Size = number of units per carton/pack.
   - Packing Price = cost per full carton/pack (not per unit).

2. An invoice PDF from the same supplier listing products and their prices.

Your job:

STEP 1 — Learn the catalogue pattern.
Study how Product Name relates to Packing Size across all rows.
For example, if every "500ML" product has Packing Size 24 and every "1.5L" product
has Packing Size 12, remember this pattern. You will need it for new products.

STEP 2 — Extract invoice line items.
From the PDF, extract every product description and its price per carton/pack.
Ignore sub-totals, totals, taxes, and header rows.

STEP 3 — Match and classify each invoice item:
  A. If the invoice product matches an existing catalogue row (fuzzy match on name):
       - If the invoice price == catalogue Packing Price → classify as "unchanged".
       - If the invoice price != catalogue Packing Price → classify as "update_price".
         Use the EXACT "Product Name" value from the CSV for csv_product_name.
  B. If the invoice product does NOT match any catalogue row → classify as "new_product".
     Infer its Packing Size from the pattern you learned in Step 1
     (look at similar brands, similar size suffixes like ML/L/G/KG).

Return ONLY a valid JSON object with exactly these three keys:
{{
  "updates": [
    {{"csv_product_name": "...", "old_price": 0.0, "new_price": 0.0}}
  ],
  "new_products": [
    {{"product_name": "...", "packing_price": 0.0, "inferred_packing_size": 0, "inference_reason": "..."}}
  ],
  "unchanged": ["..."]
}}

No markdown, no explanation outside the JSON.

--- CATALOGUE CSV ---
{supplier_csv}
--- END CATALOGUE ---
"""

    parts: list[Any] = [
        types.Part.from_text(text=system_prompt),
        types.Part.from_bytes(data=pdf_bytes, mime_type=pdf_mime_type),
    ]

    contents: list[Any] = [types.Content(role="user", parts=parts)]

    raw: str = ""

    for attempt in range(3):
        try:
            response: Any = st.session_state.gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(),
            )
            raw = response.text.strip()
            cleaned: str = re.sub(
                r"^```json\s*|```\s*$", "", raw, flags=re.MULTILINE | re.IGNORECASE
            )
            return json.loads(cleaned)
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(
                    f"Gemini failed after 3 attempts: {e}\n\nRaw response:\n{raw}"
                )

    return {}


# ── Apply changes to data7.csv ────────────────────────────────────────────────

def apply_changes(
    supplier: str,
    price_updates: list[dict[str, Any]],
    new_products: list[dict[str, Any]],   # may have user-edited packing_size
) -> tuple[int, int]:
    """
    Applies price updates and new-product inserts to data7.csv.
    Returns (updated_count, inserted_count).
    """
    df: pl.DataFrame = load_nml_csv()

    updated_count: int = 0

    # ── Price updates ──────────────────────────────────────────────────────────
    for upd in price_updates:
        csv_name: str = upd["csv_product_name"]
        new_price: float = float(upd["new_price"])

        mask: pl.Series = (
            df["Product Name"].str.strip_chars().str.to_lowercase()
            == csv_name.strip().lower()
        ) & (
            df["Supplier"].fill_null("").str.strip_chars().str.to_lowercase()
            == supplier.strip().lower()
        )

        if mask.sum() > 0:
            df = df.with_columns(
                pl.when(mask)
                .then(pl.lit(new_price))
                .otherwise(pl.col("Packing Price"))
                .alias("Packing Price")
            )
            updated_count += 1

    # ── New products ───────────────────────────────────────────────────────────
    inserted_count: int = 0

    if new_products:
        product_names: list[str] = [p["product_name"] for p in new_products]

        split_results: list[dict[str, str]] = []
        BATCH: int = 50
        for start in range(0, len(product_names), BATCH):
            batch: list[str] = product_names[start : start + BATCH]
            try:
                split_results.extend(split_product_names_with_groq(batch))
            except Exception:
                split_results.extend(
                    [{"processed_name": n, "packing_style": ""} for n in batch]
                )

        new_rows: list[dict[str, Any]] = []
        for i, prod in enumerate(new_products):
            split: dict[str, str] = split_results[i] if i < len(split_results) else {}
            new_rows.append(
                {
                    "Product Name": prod["product_name"],
                    "Processed Product Name": split.get("processed_name", prod["product_name"]),
                    "Packing Style": split.get("packing_style", ""),
                    "Packing Size": float(prod.get("packing_size", prod.get("inferred_packing_size", 1))),
                    "Packing Price": float(prod["packing_price"]),
                    "Supplier": supplier,
                }
            )

        new_df: pl.DataFrame = pl.DataFrame(new_rows)

        # Only insert rows that don't already exist (by Product Name + Supplier)
        existing_keys: pl.DataFrame = df.select(
            (
                pl.col("Product Name").str.strip_chars().str.to_lowercase()
                + pl.lit("|")
                + pl.col("Supplier").fill_null("").str.strip_chars().str.to_lowercase()
            ).alias("_key")
        )
        new_df_keyed: pl.DataFrame = new_df.with_columns(
            (
                pl.col("Product Name").str.strip_chars().str.to_lowercase()
                + pl.lit("|")
                + pl.col("Supplier").fill_null("").str.strip_chars().str.to_lowercase()
            ).alias("_key")
        )
        inserts: pl.DataFrame = (
            new_df_keyed.join(existing_keys, on="_key", how="anti").drop("_key")
        )
        inserted_count = inserts.height

        if not inserts.is_empty():
            df = pl.concat([df, inserts], how="diagonal").select(NML_COLUMNS)

    save_nml_csv(df)
    return updated_count, inserted_count

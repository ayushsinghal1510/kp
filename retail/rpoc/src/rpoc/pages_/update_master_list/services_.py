import re
import json
import polars as pl
import streamlit as st

from typing import Any
from google.genai import types

from rpoc.pages_.new_master_list.services_ import (
    NML_CSV_PATH,
    NML_COLUMNS,
    load_nml_csv,
    save_nml_csv,
)


# ── Load helpers ──────────────────────────────────────────────────────────────

def get_supplier_list() -> list[str]:
    df: pl.DataFrame = load_nml_csv()
    if "Supplier" not in df.columns or df.is_empty():
        return []
    return (
        df.select("Supplier")
        .drop_nulls()
        .filter(pl.col("Supplier").str.strip_chars() != "")
        .unique()
        .sort("Supplier")
        .get_column("Supplier")
        .to_list()
    )


def get_supplier_df_csv(supplier: str) -> str:
    """Return a CSV of the supplier's catalogue for LLM naming context."""
    df: pl.DataFrame = load_nml_csv()
    filtered: pl.DataFrame = df.filter(
        pl.col("Supplier").str.strip_chars().str.to_lowercase()
        == supplier.strip().lower()
    )
    context_cols = [
        c for c in ["Product Name", "Processed Product Name", "Packing Style", "Packing Size", "Supplier"]
        if c in filtered.columns
    ]
    return filtered.select(context_cols).write_csv()


# ── Fuzzy matching ────────────────────────────────────────────────────────────

def _normalize_for_match(name: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    (Milk) and Milk both normalize to 'milk'; mlk does not match milk.
    """
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ── Gemini: extract products from invoice ────────────────────────────────────

def analyse_invoice_with_gemini(
    pdf_bytes: bytes,
    pdf_mime_type: str,
    supplier_csv: str,
    supplier_name: str,
) -> dict[str, Any]:
    """
    Extracts raw product data from the invoice. Matching against the catalogue
    is done by the caller — Gemini only extracts and normalises names.

    Returns:
    {
      "exchange_rate": float,
      "products": [
        {
          "product_name":   str,   # raw name from invoice
          "processed_name": str,   # core brand/product name (no size/format)
          "packing_style":  str,   # size/format suffix, e.g. "800ML"
          "packing_size":   int,   # units per carton/pack
          "packing_price":  float  # price in invoice native currency (before exchange rate)
        }
      ]
    }
    """

    system_prompt: str = f"""
You are a data extraction expert for supplier "{supplier_name}".

You will receive:
1. A reference product catalogue (for naming context only — do NOT match or classify against it).
   Study it to understand the naming convention: what is a "core product name" vs a "packing style".
2. An invoice PDF from this supplier.

TASK 1 — Extract the exchange rate.
Find the currency conversion rate on the invoice (look for "汇率", "Rate", "Exchange Rate",
"CNY/SGD", or a line like "1 CNY = 0.19 SGD"). Return it as a float. If absent, return 1.0.

TASK 2 — Extract every product line item from the invoice.
For each product line:
  - product_name:   the raw product description exactly as written on the invoice
  - processed_name: the core brand/product name ONLY — no size, no format, no packing notation.
                    Use the same capitalisation and spelling style as the reference catalogue.
                    E.g. if catalogue uses "Mirinda", don't return "MIRINDA" or "mirinda orange".
  - packing_style:  the size/volume/weight/format suffix only (e.g. "800ML", "1.5L", "250G").
                    Empty string if none.
  - packing_size:   number of units per carton/pack as an integer.
  - packing_price:  the price in the invoice's native currency — do NOT apply exchange rate.

Ignore sub-totals, totals, taxes, FOC rows, discount rows, and header rows.

Return ONLY valid JSON — no markdown, no explanation:
{{
  "exchange_rate": 1.0,
  "products": [
    {{
      "product_name": "...",
      "processed_name": "...",
      "packing_style": "...",
      "packing_size": 12,
      "packing_price": 0.0
    }}
  ]
}}

--- REFERENCE CATALOGUE (naming context only) ---
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


# ── App-level matching ────────────────────────────────────────────────────────

def match_invoice_products(
    supplier: str,
    invoice_products: list[dict[str, Any]],
    exchange_rate: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """
    Fuzzy-matches invoice products against the master list on
    (normalize(Processed Product Name), normalize(Packing Style)).

    Returns:
      - updates:          products whose price changed
      - new_products:     products not found in master list
      - unchanged_count:  matched products with identical price
    Prices in both lists are already converted to SGD (÷ exchange_rate).
    """
    df: pl.DataFrame = load_nml_csv()
    supplier_df: pl.DataFrame = df.filter(
        pl.col("Supplier").str.strip_chars().str.to_lowercase()
        == supplier.strip().lower()
    )

    # Build lookup: normalize(processed_name)|normalize(packing_style) → row dict
    lookup: dict[str, dict[str, Any]] = {}
    for row in supplier_df.to_dicts():
        key = (
            _normalize_for_match(str(row.get("Processed Product Name") or ""))
            + "|"
            + _normalize_for_match(str(row.get("Packing Style") or ""))
        )
        lookup[key] = row

    rate: float = exchange_rate if exchange_rate else 1.0

    updates: list[dict[str, Any]] = []
    new_products: list[dict[str, Any]] = []
    unchanged_count: int = 0

    for prod in invoice_products:
        processed: str = prod.get("processed_name", "")
        style: str = prod.get("packing_style", "")
        key: str = _normalize_for_match(processed) + "|" + _normalize_for_match(style)
        sgd_price: float = round(float(prod["packing_price"]) / rate, 4)

        if key in lookup:
            existing = lookup[key]
            old_price = existing.get("Packing Price")
            old_float = float(old_price) if old_price is not None else None

            if old_float is None or abs(old_float - sgd_price) > 0.001:
                updates.append(
                    {
                        "csv_product_name": existing["Product Name"],
                        "processed_name": processed,
                        "packing_style": style,
                        "old_price": old_float if old_float is not None else 0.0,
                        "new_price": sgd_price,
                    }
                )
            else:
                unchanged_count += 1
        else:
            new_products.append(
                {
                    "product_name": prod["product_name"],
                    "processed_name": processed,
                    "packing_style": style,
                    "packing_size": int(prod.get("packing_size", 1)),
                    "packing_price": sgd_price,
                }
            )

    return updates, new_products, unchanged_count


# ── Apply changes to data7.csv ────────────────────────────────────────────────

def apply_changes(
    supplier: str,
    price_updates: list[dict[str, Any]],
    new_products: list[dict[str, Any]],
    exchange_rate: float,
) -> tuple[int, int]:
    """
    Applies price updates and new-product inserts to data7.csv.

    Price update: Packing Price → new value; old value → Previous Packing Price;
                  Exchange Rate column updated to invoice rate.
    New product:  inserted as a new row with all columns populated.

    Returns (updated_count, inserted_count).
    """
    df: pl.DataFrame = load_nml_csv()
    rate: float = float(exchange_rate) if exchange_rate else 1.0

    updated_count: int = 0

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
                [
                    # Shift current price to Previous Packing Price
                    pl.when(mask)
                    .then(pl.col("Packing Price"))
                    .otherwise(pl.col("Previous Packing Price"))
                    .alias("Previous Packing Price"),
                    # Set new price
                    pl.when(mask)
                    .then(pl.lit(new_price))
                    .otherwise(pl.col("Packing Price"))
                    .alias("Packing Price"),
                    # Update exchange rate
                    pl.when(mask)
                    .then(pl.lit(rate))
                    .otherwise(pl.col("Exchange Rate"))
                    .alias("Exchange Rate"),
                ]
            )
            updated_count += 1

    inserted_count: int = 0

    if new_products:
        new_rows: list[dict[str, Any]] = [
            {
                "Product Name": p["product_name"],
                "Processed Product Name": p["processed_name"],
                "Packing Style": p["packing_style"],
                "Packing Size": float(p.get("packing_size", 1)),
                "Packing Price": float(p["packing_price"]),
                "Previous Packing Price": None,
                "Exchange Rate": rate,
                "Supplier": supplier,
            }
            for p in new_products
        ]

        new_df: pl.DataFrame = pl.DataFrame(new_rows)

        # Only insert rows that don't already exist (Product Name + Supplier key)
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
        inserts: pl.DataFrame = new_df_keyed.join(
            existing_keys, on="_key", how="anti"
        ).drop("_key")
        inserted_count = inserts.height

        if not inserts.is_empty():
            df = pl.concat([df, inserts], how="diagonal").select(NML_COLUMNS)

    save_nml_csv(df)
    return updated_count, inserted_count

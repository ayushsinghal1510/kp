import re
import json
import pandas as pd
import polars as pl
import streamlit as st

from typing import Any
from google.genai import types


NML_CSV_PATH: str = "assets/data/data7.csv"
NML_COLUMNS: list[str] = [
    "Product Name",
    "Processed Product Name",
    "Packing Style",
    "Packing Size",
    "Packing Price",
    "Previous Packing Price",
    "Exchange Rate",
    "Supplier",
]


# ── column-name fuzzy matching ────────────────────────────────────────────────

def _find_col(gemini_name: str | None, actual_cols: list[str]) -> str | None:
    """
    Return the best-matching actual column name for what Gemini reported.
    Tries exact → case-insensitive → substring match.  Returns None on miss.
    """
    if not gemini_name:
        return None

    # exact
    if gemini_name in actual_cols:
        return gemini_name

    g_low = gemini_name.strip().lower()

    # case-insensitive exact
    for c in actual_cols:
        if c.strip().lower() == g_low:
            return c

    # one contains the other
    for c in actual_cols:
        c_low = c.strip().lower()
        if g_low in c_low or c_low in g_low:
            return c

    return None


# ── Gemini: detect columns from an 8-row preview ─────────────────────────────

def detect_columns_with_gemini(preview_csv: str) -> dict[str, Any]:
    """
    Returns:
      {
        "product_name_col":  <str | null>,
        "packing_size_col":  <str | null>,
        "packing_price_col": <str | null>,
        "supplier_col":      <str | null>,   # column name if supplier is a data column
        "supplier_name":     <str | null>,   # literal value if supplier is in metadata rows
        "header_row":        <int>
      }
    Exactly one of supplier_col / supplier_name should be non-null when a supplier
    is identifiable; both may be null if not found.
    """
    prompt = (
        "You are a data analyst. Below are the first several rows of a spreadsheet "
        "dumped as CSV. The leftmost number before the comma is the row index (0-based).\n\n"
        f"```\n{preview_csv}\n```\n\n"
        "Identify:\n"
        "1. The exact column name (as it appears in the header row) for the **product name** "
        "(brand + description, e.g. 'Product', 'Description', 'Item Name').\n"
        "2. The exact column name for **packing size** (numeric units per pack, e.g. 'Qty', 'Pack Qty', 'Size').\n"
        "3. The exact column name for **packing price** (cost per pack, e.g. 'Price', 'Unit Price', 'Pack Price').\n"
        "4. The **supplier / vendor name**. This may appear in two ways:\n"
        "   a. As a column in the data table — return the exact column name as `supplier_col`.\n"
        "   b. As a value in a metadata row above the table header (e.g. 'Supplier: ABC Trading', "
        "'Company: XYZ Pte Ltd') — extract the actual name string and return it as `supplier_name`.\n"
        "   If both forms exist, prefer the column. Set whichever does not apply to null.\n"
        "5. The **exchange rate** (currency conversion factor, e.g. '汇率', 'Rate', 'Exchange Rate', "
        "'CNY/SGD'). This may appear in two ways:\n"
        "   a. As a column in the data table — return the exact column name as `exchange_rate_col`.\n"
        "   b. As a numeric value in a metadata row (e.g. '汇率: 4.52', 'Rate = 0.19') — extract "
        "the number as `exchange_rate_value` (float).\n"
        "   If both forms exist, prefer the column. Set whichever does not apply to null.\n"
        "6. The 0-based row index of the **actual table header** (the row with column names).\n\n"
        "Respond ONLY with a valid JSON object with keys: "
        '"product_name_col", "packing_size_col", "packing_price_col", '
        '"supplier_col", "supplier_name", "exchange_rate_col", "exchange_rate_value", "header_row". '
        "Set a value to null if it cannot be identified. No markdown, no explanation."
    )

    contents: list[Any] = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]

    response: Any = st.session_state.gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
        config=types.GenerateContentConfig(),
    )

    raw: str = response.text.strip()
    cleaned: str = re.sub(
        r"^```json\s*|```\s*$", "", raw, flags=re.MULTILINE | re.IGNORECASE
    )
    return json.loads(cleaned)


# ── Parse one sheet using Gemini-detected column mapping ─────────────────────

def _parse_single_sheet(
    raw_df: pd.DataFrame,   # read with header=None
    col_mapping: dict[str, Any],
    sheet_name: str,
) -> pd.DataFrame:
    """
    Re-reads the sheet from raw_df using the detected header row, extracts the
    three target columns, and returns a clean DataFrame with columns:
      Product Name | Packing Size | Packing Price
    Raises ValueError if the product-name column cannot be matched.
    """
    header_row: int = int(col_mapping.get("header_row", 0))

    # Re-interpret raw_df with the proper header row
    new_header: list[str] = [str(v) for v in raw_df.iloc[header_row].tolist()]
    df: pd.DataFrame = raw_df.iloc[header_row + 1 :].copy()
    df.columns = new_header
    df = df.reset_index(drop=True)
    df.dropna(how="all", inplace=True)

    actual_cols: list[str] = list(df.columns)

    product_col: str | None = _find_col(col_mapping.get("product_name_col"), actual_cols)
    size_col: str | None = _find_col(col_mapping.get("packing_size_col"), actual_cols)
    price_col: str | None = _find_col(col_mapping.get("packing_price_col"), actual_cols)
    supplier_col: str | None = _find_col(col_mapping.get("supplier_col"), actual_cols)
    supplier_name: str | None = col_mapping.get("supplier_name") or None

    if product_col is None:
        raise ValueError(
            f"[Sheet: {sheet_name}] Cannot find product-name column "
            f"(Gemini said '{col_mapping.get('product_name_col')}', "
            f"actual columns: {actual_cols})"
        )

    select_cols: list[str] = [product_col]
    rename_map: dict[str, str] = {product_col: "Product Name"}

    if size_col:
        select_cols.append(size_col)
        rename_map[size_col] = "Packing Size"

    if price_col:
        select_cols.append(price_col)
        rename_map[price_col] = "Packing Price"

    if supplier_col:
        select_cols.append(supplier_col)
        rename_map[supplier_col] = "Supplier"

    exchange_rate_col: str | None = _find_col(col_mapping.get("exchange_rate_col"), actual_cols)
    exchange_rate_value: Any = col_mapping.get("exchange_rate_value")

    result: pd.DataFrame = df[select_cols].rename(columns=rename_map)

    result = result[result["Product Name"].notna()]
    result = result[result["Product Name"].astype(str).str.strip() != ""]
    result = result[result["Product Name"].astype(str).str.strip().str.lower() != "nan"]
    result = result.reset_index(drop=True)

    # If supplier came from metadata (not a column), fill every row with the literal
    if "Supplier" not in result.columns and supplier_name:
        result["Supplier"] = supplier_name

    # Determine exchange rate for this sheet and add as a constant column
    sheet_exchange_rate: float | None = None
    if exchange_rate_col and exchange_rate_col in df.columns:
        try:
            rate_vals = pd.to_numeric(df[exchange_rate_col], errors="coerce").dropna()
            if not rate_vals.empty:
                sheet_exchange_rate = float(rate_vals.iloc[0])
        except Exception:
            pass
    elif exchange_rate_value is not None:
        try:
            sheet_exchange_rate = float(exchange_rate_value)
        except (ValueError, TypeError):
            pass

    result["Exchange Rate"] = sheet_exchange_rate

    return result


# ── Main entry: process ALL sheets ───────────────────────────────────────────

def process_all_sheets(
    uploaded_file: Any,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Reads every sheet in the uploaded Excel.  For each sheet:
      1. Sends first 8 rows to Gemini to detect column mapping.
      2. Parses the sheet using that mapping.

    Returns:
      - combined pandas DataFrame with columns: Product Name, Packing Size, Packing Price
      - list of per-sheet status messages for display in the UI
    """
    all_sheets_raw: dict[str, pd.DataFrame] = pd.read_excel(
        uploaded_file,
        header=None,
        sheet_name=None,
    )

    combined_frames: list[pd.DataFrame] = []
    messages: list[str] = []

    for sheet_name, raw_df in all_sheets_raw.items():

        if raw_df.dropna(how="all").empty:
            messages.append(f"[{sheet_name}] Skipped — sheet is empty.")
            continue

        preview_csv: str = raw_df.head(8).to_csv(index=True, header=False)

        try:
            col_mapping: dict[str, Any] = detect_columns_with_gemini(preview_csv)
            messages.append(
                f"[{sheet_name}] Gemini mapping: {col_mapping}"
            )
        except Exception as e:
            messages.append(f"[{sheet_name}] Gemini detection failed: {e} — skipping.")
            continue

        try:
            sheet_df: pd.DataFrame = _parse_single_sheet(raw_df, col_mapping, sheet_name)
            sheet_df["_sheet"] = sheet_name
            combined_frames.append(sheet_df)
            messages.append(f"[{sheet_name}] Parsed {len(sheet_df)} rows.")
        except Exception as e:
            messages.append(f"[{sheet_name}] Parse error: {e} — skipping.")
            continue

    if not combined_frames:
        return pd.DataFrame(columns=["Product Name", "Packing Size", "Packing Price", "Supplier"]), messages

    combined: pd.DataFrame = pd.concat(combined_frames, ignore_index=True)
    combined.drop(columns=["_sheet"], inplace=True, errors="ignore")
    return combined, messages


# ── Groq: split product name from packing style ──────────────────────────────

def split_product_names_with_groq(
    product_names: list[str],
) -> list[dict[str, str]]:
    """
    Returns a list (same order) of:
      {"processed_name": "Mirinda", "packing_style": "800ML"}
    """
    names_json: str = json.dumps(product_names)

    prompt: str = (
        "You are a product data normaliser. "
        "For each product description in the JSON array below, split it into:\n"
        '  - "processed_name": the core brand / product name (e.g. "Mirinda", "Coca-Cola")\n'
        '  - "packing_style": the size, volume, weight, count, or format suffix '
        '(e.g. "800ML", "1.5L", "24x330ML", "250G", "6PK"). '
        "If there is no obvious size/format suffix, set packing_style to an empty string.\n\n"
        f"Input array:\n{names_json}\n\n"
        "Respond ONLY with a JSON array of objects with keys "
        '"processed_name" and "packing_style", one entry per input item, in the same order. '
        "No markdown, no explanation."
    )

    response: Any = st.session_state.groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0,
    )

    raw: str = response.choices[0].message.content.strip()
    cleaned: str = re.sub(
        r"^```json\s*|```\s*$", "", raw, flags=re.MULTILINE | re.IGNORECASE
    )

    parsed: list[dict[str, str]] = json.loads(cleaned)

    while len(parsed) < len(product_names):
        parsed.append({"processed_name": product_names[len(parsed)], "packing_style": ""})

    return parsed[: len(product_names)]


# ── Assemble final DataFrame ──────────────────────────────────────────────────

def build_nml_dataframe(
    parsed_df: pd.DataFrame,
    split_results: list[dict[str, str]],
) -> pl.DataFrame:
    """
    Uses .to_dict(orient='records') to avoid the itertuples column-name mangling
    that silently drops columns whose names contain spaces.
    """
    rows: list[dict[str, Any]] = []

    has_size: bool = "Packing Size" in parsed_df.columns
    has_price: bool = "Packing Price" in parsed_df.columns
    has_supplier: bool = "Supplier" in parsed_df.columns
    has_exchange_rate: bool = "Exchange Rate" in parsed_df.columns

    for i, row_dict in enumerate(parsed_df.to_dict(orient="records")):
        product_name: str = str(row_dict.get("Product Name", "")).strip()
        packing_size: Any = row_dict.get("Packing Size") if has_size else None
        packing_price: Any = row_dict.get("Packing Price") if has_price else None
        supplier: Any = str(row_dict.get("Supplier", "")).strip() if has_supplier else None
        exchange_rate: Any = row_dict.get("Exchange Rate") if has_exchange_rate else None

        split: dict[str, str] = split_results[i] if i < len(split_results) else {}

        rows.append(
            {
                "Product Name": product_name,
                "Processed Product Name": split.get("processed_name", product_name),
                "Packing Style": split.get("packing_style", ""),
                "Packing Size": packing_size,
                "Packing Price": packing_price,
                "Previous Packing Price": None,
                "Exchange Rate": exchange_rate,
                "Supplier": supplier,
            }
        )

    df: pl.DataFrame = pl.DataFrame(rows)

    for col in ("Packing Size", "Packing Price", "Previous Packing Price", "Exchange Rate"):
        if col in df.columns:
            df = df.with_columns(pl.col(col).cast(pl.Float64, strict=False).alias(col))

    return df


# ── CSV persistence ───────────────────────────────────────────────────────────

def load_nml_csv() -> pl.DataFrame:
    try:
        df: pl.DataFrame = pl.read_csv(NML_CSV_PATH)
        for col in NML_COLUMNS:
            if col not in df.columns:
                df = df.with_columns(pl.lit(None).alias(col))
        df = df.select(NML_COLUMNS).unique(
            subset=["Product Name", "Supplier"], keep="last"
        )
        return df
    except Exception:
        return pl.DataFrame({col: [] for col in NML_COLUMNS})


def save_nml_csv(df: pl.DataFrame) -> None:
    df.select(NML_COLUMNS).write_csv(NML_CSV_PATH)

import pandas as pd
import polars as pl
import streamlit as st

from typing import Any

from rpoc.pages_.new_master_list.services_ import (
    NML_COLUMNS,
    process_all_sheets,
    split_product_names_with_groq,
    build_nml_dataframe,
    load_nml_csv,
    save_nml_csv,
)

# ---------- session-state init ----------

if "nml_df" not in st.session_state:
    st.session_state.nml_df = load_nml_csv()

if "nml_pending" not in st.session_state:
    st.session_state.nml_pending = None  # pl.DataFrame | None

# ---------- page ----------

st.header("New Master List")
st.caption("Upload a supplier Excel file to extract and normalise product data into data7.csv.")

# ---- upload section ----

uploaded_file: Any = st.file_uploader(
    "Upload Supplier Excel",
    type=["xlsx", "xls"],
    key="nml_excel_upload",
)

process_btn: bool = st.button("Process Excel", disabled=uploaded_file is None)

if process_btn and uploaded_file is not None:

    # Step 1 & 2: Gemini column detection + parsing — one Gemini call per sheet
    with st.spinner("Step 1/2 — Detecting columns and parsing all sheets via Gemini…"):

        try:
            parsed_df: pd.DataFrame
            sheet_messages: list[str]
            parsed_df, sheet_messages = process_all_sheets(uploaded_file)
        except Exception as e:
            st.error(f"Sheet processing failed: {e}")
            st.stop()

    with st.expander("Sheet processing log", expanded=False):
        for msg in sheet_messages:
            st.text(msg)

    if parsed_df.empty:
        st.error("No product rows could be extracted from any sheet. Check the log above.")
        st.stop()

    st.info(f"Extracted {len(parsed_df)} product rows across all sheets.")

    # Step 2: Groq splitting
    with st.spinner("Step 2/2 — Splitting product names with Groq llama-3.1-8b-instant…"):

        product_names: list[str] = parsed_df["Product Name"].astype(str).tolist()

        BATCH: int = 50
        split_results: list[dict] = []

        for start in range(0, len(product_names), BATCH):
            batch: list[str] = product_names[start : start + BATCH]
            try:
                split_results.extend(split_product_names_with_groq(batch))
            except Exception as e:
                st.warning(
                    f"Groq batch {start}–{start + BATCH} failed ({e}); using raw names."
                )
                split_results.extend(
                    [{"processed_name": n, "packing_style": ""} for n in batch]
                )

        st.success("Product names split successfully.")

    new_df: pl.DataFrame = build_nml_dataframe(parsed_df, split_results)
    st.session_state.nml_pending = new_df

# ---- preview & confirm ----

if st.session_state.nml_pending is not None:

    pending: pl.DataFrame = st.session_state.nml_pending

    st.subheader("Preview — Processed Data")
    st.dataframe(pending.to_pandas(), use_container_width=True, hide_index=True)

    col_save, col_discard = st.columns(2)

    with col_save:
        if st.button("Save to data7.csv", type="primary"):

            existing: pl.DataFrame = st.session_state.nml_df

            def _make_key(df: pl.DataFrame) -> pl.DataFrame:
                return df.with_columns(
                    (
                        pl.col("Product Name").str.strip_chars().str.to_lowercase()
                        + pl.lit("|")
                        + pl.col("Supplier").fill_null("").str.strip_chars().str.to_lowercase()
                    ).alias("_key")
                )

            # Deduplicate the incoming batch itself (keep last occurrence)
            pending = _make_key(pending).unique(subset=["_key"], keep="last").drop("_key")

            if existing.is_empty():
                merged: pl.DataFrame = pending
            else:
                existing_keyed: pl.DataFrame = _make_key(existing)
                pending_keyed: pl.DataFrame = _make_key(pending)

                inserts: pl.DataFrame = pending_keyed.join(
                    existing_keyed.select("_key"), on="_key", how="anti"
                )
                updates: pl.DataFrame = pending_keyed.join(
                    existing_keyed.select("_key"), on="_key", how="inner"
                )

                if not updates.is_empty():
                    existing_keyed = existing_keyed.filter(
                        ~pl.col("_key").is_in(updates.get_column("_key"))
                    )

                parts: list[pl.DataFrame] = [existing_keyed, inserts]
                if not updates.is_empty():
                    parts.append(updates)

                merged = (
                    pl.concat(parts, how="diagonal")
                    .drop("_key")
                    .select(NML_COLUMNS)
                )

            save_nml_csv(merged)
            st.session_state.nml_df = merged
            st.session_state.nml_pending = None

            st.success(f"Saved {merged.height} rows to data7.csv.")
            st.rerun()

    with col_discard:
        if st.button("Discard"):
            st.session_state.nml_pending = None
            st.rerun()

# ---- current data display ----

st.divider()
st.subheader("Current data7.csv")

current: pl.DataFrame = st.session_state.nml_df

if current.is_empty():
    st.info("No data yet. Upload a supplier Excel file above.")
else:
    st.dataframe(current.to_pandas(), use_container_width=True, hide_index=True)
    st.caption(f"{current.height} rows total.")

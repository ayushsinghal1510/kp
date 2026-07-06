import pandas as pd
import streamlit as st

from typing import Any

from rpoc.pages_.update_master_list.services_ import (
    get_supplier_list,
    get_supplier_df_csv,
    analyse_invoice_with_gemini,
    match_invoice_products,
    apply_changes,
)

# ---------- session-state init ----------

if "uml_exchange_rate" not in st.session_state:
    st.session_state.uml_exchange_rate = None   # float | None
if "uml_updates" not in st.session_state:
    st.session_state.uml_updates = None         # list[dict] | None
if "uml_new_products" not in st.session_state:
    st.session_state.uml_new_products = None    # list[dict] | None
if "uml_unchanged_count" not in st.session_state:
    st.session_state.uml_unchanged_count = 0
if "uml_supplier" not in st.session_state:
    st.session_state.uml_supplier = None

# ---------- page ----------

st.header("Update Master List")
st.caption(
    "Upload an invoice PDF. Products are matched against the catalogue using fuzzy name matching — "
    "prices are updated in place and the exchange rate is taken from the invoice."
)

# ── Supplier selector ──────────────────────────────────────────────────────────

suppliers: list[str] = get_supplier_list()

if not suppliers:
    st.warning("No suppliers found in data7.csv. Add products via the New Master List page first.")
    st.stop()

selected_supplier: str = st.selectbox("Select Supplier", options=suppliers)

# ── Invoice upload ─────────────────────────────────────────────────────────────

invoice_file: Any = st.file_uploader(
    "Upload Invoice PDF",
    type=["pdf"],
    key="uml_invoice_upload",
)

process_btn: bool = st.button(
    "Process Invoice",
    disabled=(invoice_file is None),
)

if process_btn and invoice_file is not None:

    st.session_state.uml_exchange_rate = None
    st.session_state.uml_updates = None
    st.session_state.uml_new_products = None
    st.session_state.uml_unchanged_count = 0
    st.session_state.uml_supplier = selected_supplier

    # Step 1: Gemini extracts raw products + exchange rate from invoice
    with st.spinner("Step 1/2 — Extracting products from invoice via Gemini…"):
        supplier_csv: str = get_supplier_df_csv(selected_supplier)
        if not supplier_csv.strip():
            st.error(f"No products found in data7.csv for supplier '{selected_supplier}'.")
            st.stop()

        pdf_bytes: bytes = invoice_file.getvalue()
        pdf_mime: str = invoice_file.type or "application/pdf"

        try:
            raw_result: dict = analyse_invoice_with_gemini(
                pdf_bytes=pdf_bytes,
                pdf_mime_type=pdf_mime,
                supplier_csv=supplier_csv,
                supplier_name=selected_supplier,
            )
        except Exception as e:
            st.error(f"Gemini extraction failed: {e}")
            st.stop()

    exchange_rate: float = float(raw_result.get("exchange_rate", 1.0))
    invoice_products: list[dict] = raw_result.get("products", [])

    if not invoice_products:
        st.warning("Gemini found no product lines in this invoice.")
        st.stop()

    # Step 2: App-level fuzzy matching against master list
    with st.spinner(f"Step 2/2 — Matching {len(invoice_products)} invoice lines against catalogue…"):
        try:
            updates, new_products, unchanged_count = match_invoice_products(
                supplier=selected_supplier,
                invoice_products=invoice_products,
                exchange_rate=exchange_rate,
            )
        except Exception as e:
            st.error(f"Matching failed: {e}")
            st.stop()

    st.session_state.uml_exchange_rate = exchange_rate
    st.session_state.uml_updates = updates
    st.session_state.uml_new_products = new_products
    st.session_state.uml_unchanged_count = unchanged_count

# ── Results ────────────────────────────────────────────────────────────────────

if st.session_state.uml_updates is not None:

    updates: list[dict] = st.session_state.uml_updates
    new_products: list[dict] = st.session_state.uml_new_products
    unchanged_count: int = st.session_state.uml_unchanged_count
    supplier: str = st.session_state.uml_supplier
    exchange_rate: float = st.session_state.uml_exchange_rate

    st.divider()

    # ── Exchange rate banner ───────────────────────────────────────────────────

    total = len(updates) + len(new_products) + unchanged_count
    st.info(
        f"Invoice exchange rate: **{exchange_rate}**   |   "
        f"Total invoice lines: **{total}**   |   "
        f"Price updates: **{len(updates)}**   |   "
        f"New products: **{len(new_products)}**   |   "
        f"Unchanged: **{unchanged_count}**"
    )

    # ── Price updates table ────────────────────────────────────────────────────

    st.subheader(f"Price Updates ({len(updates)})")

    if updates:
        updates_df: pd.DataFrame = pd.DataFrame(updates).rename(
            columns={
                "csv_product_name": "Product Name",
                "processed_name": "Processed Name",
                "packing_style": "Packing Style",
                "old_price": "Old Price (SGD)",
                "new_price": "New Price (SGD)",
            }
        )
        updates_df["Δ"] = (
            updates_df["New Price (SGD)"] - updates_df["Old Price (SGD)"]
        ).round(4)
        st.dataframe(updates_df, use_container_width=True, hide_index=True)
    else:
        st.info("No price changes detected.")

    # ── New products (editable packing size) ───────────────────────────────────

    st.subheader(f"New Products to Add ({len(new_products)})")

    if new_products:
        new_df_display: pd.DataFrame = pd.DataFrame(new_products).rename(
            columns={
                "product_name": "Product Name",
                "processed_name": "Processed Name",
                "packing_style": "Packing Style",
                "packing_size": "Packing Size",
                "packing_price": "Packing Price (SGD)",
            }
        )

        edited_new: pd.DataFrame = st.data_editor(
            new_df_display,
            column_config={
                "Packing Size": st.column_config.NumberColumn(
                    "Packing Size", min_value=1, step=1
                ),
                "Packing Price (SGD)": st.column_config.NumberColumn(
                    "Packing Price (SGD)", format="%.4f"
                ),
                "Product Name": st.column_config.TextColumn("Product Name", disabled=True),
                "Processed Name": st.column_config.TextColumn("Processed Name"),
                "Packing Style": st.column_config.TextColumn("Packing Style"),
            },
            use_container_width=True,
            hide_index=True,
            key="uml_new_products_editor",
        )
    else:
        edited_new = pd.DataFrame()
        st.info("No new products detected on this invoice.")

    # ── Apply button ───────────────────────────────────────────────────────────

    st.divider()

    has_changes: bool = bool(updates) or (not edited_new.empty)

    if not has_changes:
        st.success("Nothing to apply — invoice matches the catalogue exactly.")
    else:
        if st.button("Apply Changes to data7.csv", type="primary"):

            final_new: list[dict] = []
            if not edited_new.empty:
                for row in edited_new.to_dict(orient="records"):
                    final_new.append(
                        {
                            "product_name": row.get("Product Name", ""),
                            "processed_name": row.get("Processed Name", ""),
                            "packing_style": row.get("Packing Style", ""),
                            "packing_size": int(row.get("Packing Size", 1)),
                            "packing_price": float(row.get("Packing Price (SGD)", 0.0)),
                        }
                    )

            with st.spinner("Applying changes…"):
                try:
                    updated_count: int
                    inserted_count: int
                    updated_count, inserted_count = apply_changes(
                        supplier=supplier,
                        price_updates=updates,
                        new_products=final_new,
                        exchange_rate=exchange_rate,
                    )

                    st.success(
                        f"Done — {updated_count} price(s) updated "
                        f"(previous prices preserved), "
                        f"{inserted_count} new product(s) added. "
                        f"Exchange rate {exchange_rate} applied."
                    )
                    st.session_state.uml_updates = None
                    st.session_state.uml_new_products = None
                    st.session_state.uml_exchange_rate = None
                    st.session_state.uml_unchanged_count = 0

                except Exception as e:
                    st.error(f"Failed to apply changes: {e}")

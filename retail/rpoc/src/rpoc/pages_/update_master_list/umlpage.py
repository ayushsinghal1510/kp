import polars as pl
import pandas as pd
import streamlit as st

from typing import Any

from rpoc.pages_.update_master_list.services_ import (
    get_supplier_list,
    get_supplier_df_csv,
    analyse_invoice_with_gemini,
    apply_changes,
)

# ---------- session-state init ----------

if "uml_result" not in st.session_state:
    st.session_state.uml_result = None   # raw Gemini JSON
if "uml_supplier" not in st.session_state:
    st.session_state.uml_supplier = None

# ---------- page ----------

st.header("Update Master List")
st.caption(
    "Upload an invoice PDF for a supplier. "
    "Gemini will detect price changes and infer packing sizes for new products."
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

    st.session_state.uml_result = None
    st.session_state.uml_supplier = selected_supplier

    with st.spinner("Fetching supplier catalogue from data7.csv…"):
        supplier_csv: str = get_supplier_df_csv(selected_supplier)

        if not supplier_csv.strip():
            st.error(f"No products found in data7.csv for supplier '{selected_supplier}'.")
            st.stop()

    with st.spinner("Sending catalogue + invoice to Gemini for analysis…"):
        pdf_bytes: bytes = invoice_file.getvalue()
        pdf_mime: str = invoice_file.type or "application/pdf"

        try:
            result: dict = analyse_invoice_with_gemini(
                pdf_bytes=pdf_bytes,
                pdf_mime_type=pdf_mime,
                supplier_csv=supplier_csv,
                supplier_name=selected_supplier,
            )
            st.session_state.uml_result = result
        except Exception as e:
            st.error(f"Gemini analysis failed: {e}")
            st.stop()

# ── Results ────────────────────────────────────────────────────────────────────

if st.session_state.uml_result is not None:

    result: dict = st.session_state.uml_result
    supplier: str = st.session_state.uml_supplier

    updates: list[dict] = result.get("updates", [])
    new_products: list[dict] = result.get("new_products", [])
    unchanged: list[str] = result.get("unchanged", [])

    st.divider()

    # ── Price updates table ────────────────────────────────────────────────────

    st.subheader(f"Price Updates ({len(updates)})")

    if updates:
        updates_df: pd.DataFrame = pd.DataFrame(updates).rename(
            columns={
                "csv_product_name": "Product Name",
                "old_price": "Old Price",
                "new_price": "New Price",
            }
        )
        updates_df["Δ"] = (updates_df["New Price"] - updates_df["Old Price"]).round(2)
        st.dataframe(updates_df, use_container_width=True, hide_index=True)
    else:
        st.info("No price changes detected.")

    # ── New products (editable packing size) ───────────────────────────────────

    st.subheader(f"New Products to Add ({len(new_products)})")

    if new_products:
        new_df_display: pd.DataFrame = pd.DataFrame(new_products).rename(
            columns={
                "product_name": "Product Name",
                "packing_price": "Packing Price",
                "inferred_packing_size": "Packing Size",
                "inference_reason": "Inference Reason",
            }
        )

        # Allow user to correct inferred packing sizes before saving
        edited_new: pd.DataFrame = st.data_editor(
            new_df_display,
            column_config={
                "Packing Size": st.column_config.NumberColumn(
                    "Packing Size", min_value=1, step=1
                ),
                "Packing Price": st.column_config.NumberColumn(
                    "Packing Price", format="%.2f"
                ),
                "Inference Reason": st.column_config.TextColumn(
                    "Inference Reason", disabled=True
                ),
            },
            use_container_width=True,
            hide_index=True,
            key="uml_new_products_editor",
        )
    else:
        edited_new = pd.DataFrame()
        st.info("No new products detected on this invoice.")

    # ── Unchanged (collapsed) ──────────────────────────────────────────────────

    if unchanged:
        with st.expander(f"Unchanged ({len(unchanged)}) — same price as catalogue"):
            for name in unchanged:
                st.text(f"• {name}")

    # ── Apply button ───────────────────────────────────────────────────────────

    st.divider()

    has_changes: bool = bool(updates) or (not edited_new.empty)

    if not has_changes:
        st.success("Nothing to apply — invoice matches the catalogue exactly.")
    else:
        if st.button("Apply Changes to data7.csv", type="primary"):

            # Rebuild new_products list from the (possibly edited) dataframe
            final_new: list[dict] = []
            if not edited_new.empty:
                for row in edited_new.to_dict(orient="records"):
                    final_new.append(
                        {
                            "product_name": row.get("Product Name", ""),
                            "packing_price": float(row.get("Packing Price", 0.0)),
                            "packing_size": float(row.get("Packing Size", 1)),
                            "inferred_packing_size": float(row.get("Packing Size", 1)),
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
                    )

                    st.success(
                        f"Done — {updated_count} price(s) updated, "
                        f"{inserted_count} new product(s) added."
                    )
                    st.session_state.uml_result = None

                except Exception as e:
                    st.error(f"Failed to apply changes: {e}")

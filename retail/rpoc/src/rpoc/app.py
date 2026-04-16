import streamlit as st
import pandas as pd
import numpy as np
from groq import Groq
import io
import sys
import re
import os
import json
import base64
import difflib
import random
from datetime import datetime
from fpdf import FPDF
from dotenv import load_dotenv

# --- Setup & Environment ---
load_dotenv()
client = Groq(api_key=os.environ['GROQ_API_KEY'])

st.set_page_config(layout="wide")

# --- File Paths ---
CSV_PATH = 'assets/data.csv'
ORDER_LISTS_PATH = 'assets/ordering_lists.json'
PURCHASES_PATH = 'assets/purchases.json'
CHECKPOINT_PATH = 'assets/checkpoints.json'

os.makedirs('assets', exist_ok=True)

# --- Persistence Helpers ---
def load_json(path):
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []

def save_json(path, data):
    def convert_types(obj):
        if isinstance(obj, (np.int64, np.int32, np.float64, np.float32)):
            return obj.item()
        if isinstance(obj, (datetime, pd.Timestamp)):
            return obj.isoformat()
        return obj
    with open(path, 'w') as f:
        json.dump(data, f, indent=4, default=convert_types)

# --- Document Generation Helpers ---
def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

def create_formatted_excel(vendor, date, df):
    """Generates a professional Excel PO with ALL columns including GST and Profit."""
    output = io.BytesIO()
    workbook = pd.ExcelWriter(output, engine='xlsxwriter').book
    worksheet = workbook.add_worksheet('Purchase Order')

    # Define Formats
    title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
    supplier_fmt = workbook.add_format({'bold': True, 'font_size': 12})
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#FCE4D6', 'border': 1, 'align': 'center'})
    cell_fmt = workbook.add_format({'border': 1, 'align': 'center'})
    money_fmt = workbook.add_format({'border': 1, 'num_format': '$#,##0.00', 'align': 'right'})
    money_unit_fmt = workbook.add_format({'border': 1, 'num_format': '$#,##0.0000', 'align': 'right'})
    summary_fmt = workbook.add_format({'bold': True, 'border': 1, 'align': 'right'})

    # Headers
    worksheet.merge_range(0, 0, 0, len(df.columns)-1, f"Supplier: {vendor}", supplier_fmt)
    worksheet.merge_range(1, 0, 1, len(df.columns)-1, f"PURCHASE ORDER: {date}", title_fmt)

    # Table Headers
    for i, col in enumerate(df.columns):
        worksheet.write(3, i, col, header_fmt)

    # Table Content
    for i, row in df.iterrows():
        for j, value in enumerate(row):
            if isinstance(value, float):
                fmt = money_unit_fmt if "Price" in df.columns[j] or "Cost" in df.columns[j] else money_fmt
                worksheet.write(i+4, j, value, fmt)
            else:
                worksheet.write(i+4, j, value, cell_fmt)

    # Summary
    s_row = len(df) + 5
    raw_sum = df["Total Cost (RAW)"].sum()
    worksheet.write(s_row, len(df.columns)-2, "SUB TOTAL:", summary_fmt)
    worksheet.write(s_row, len(df.columns)-1, raw_sum, money_fmt)
    worksheet.write(s_row+2, len(df.columns)-2, "TOTAL AMT (W GST):", summary_fmt)
    worksheet.write(s_row+2, len(df.columns)-1, raw_sum * 1.09, money_fmt)

    worksheet.set_column('A:A', 30)
    worksheet.set_column('B:Z', 18)
    workbook.close()
    return output.getvalue()

def create_purchase_order_pdf(vendor, date, df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, f"Supplier: {vendor}", ln=True)
    pdf.cell(0, 10, f"PURCHASE ORDER: {date}", ln=True, align='C')
    pdf.ln(5)
    
    # Internal PDF view simplified for space
    pdf.set_font("Arial", 'B', 8)
    cols = ["Product Name", "Qty", "Total Qty", "Ctn Price", "Total (RAW)", "Total (W GST)"]
    widths = [80, 20, 30, 40, 40, 40]
    for i, col in enumerate(cols): pdf.cell(widths[i], 10, col, border=1, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", '', 8)
    for idx, row in df.iterrows():
        pdf.cell(widths[0], 10, str(row["Product Name"]), border=1)
        pdf.cell(widths[1], 10, str(row["Qty (CTN)"]), border=1, align='C')
        pdf.cell(widths[2], 10, str(int(row["Total Ordered Qty"])), border=1, align='C')
        pdf.cell(widths[3], 10, f"$ {row['Ctn Price (SGD) (W/O GST)']:.2f}", border=1, align='R')
        pdf.cell(widths[4], 10, f"$ {row['Total Cost (RAW)']:.2f}", border=1, align='R')
        pdf.cell(widths[5], 10, f"$ {row['Total Cost (SGD) (W GST)']:.2f}", border=1, align='R')
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- Logic Engines ---
def calculate_purchase_metrics(product_name, qty_ctn, packing_size, ctn_price):
    qty_ctn, packing_size = float(qty_ctn), float(packing_size)
    total_qty = qty_ctn * packing_size
    unit_p_raw = ctn_price / packing_size
    total_raw = qty_ctn * ctn_price
    markup = random.uniform(0.25, 0.30)
    sell_p_pc = unit_p_raw * (1 + markup)
    total_sell = sell_p_pc * total_qty
    total_profit = total_sell - total_raw
    return {
        "Product Name": product_name, "Qty (CTN)": qty_ctn, "Packing Size (PC)": packing_size,
        "Total Ordered Qty": total_qty, "Ctn Price (SGD) (W/O GST)": round(ctn_price, 2),
        "Unit Price (SGD) (W/O GST)": round(unit_p_raw, 4), "Total (RAW)": round(total_raw, 2),
        "Unit Cost (SGD - PC) (W/O GST)": round(unit_p_raw, 4), "Total Cost (RAW)": round(total_raw, 2),
        "Unit Cost (9%) (SGD - PC)": round(unit_p_raw * 1.09, 4), "Ctn Price (9%) (SGD)": round(ctn_price * 1.09, 2),
        "Total Cost (SGD) (W GST)": round(total_raw * 1.09, 2), "TMG Selling Price per piece": round(sell_p_pc, 4),
        "Total Selling": round(total_sell, 2), "UNIT PROFIT ($)": round(sell_p_pc - unit_p_raw, 4),
        "TOTAL PROFIT ($)": round(total_profit, 2), "Profit Margin - %": round((total_profit / total_sell) * 100, 2) if total_sell > 0 else 0
    }

def process_order_image(uploaded_file):
    base64_image = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    prompt = "Extract details from this Purchase Order into JSON format. Keys: supplier, purchase_order_date, orders (list of {product_name, quantity, packing_size})."
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}],
        response_format={"type": "json_object"}
    )
    data = json.loads(completion.choices[0].message.content)
    return {
        "filename": uploaded_file.name, "name": f"Order_{datetime.now().strftime('%H%M%S')}",
        "supplier": data.get("supplier"), "purchase_order_date": data.get("purchase_order_date"),
        "orders": data.get("orders", []), "status": "pending", "timestamp": datetime.now().isoformat()
    }

def execute_code(code_str):
    output = io.StringIO()
    sys.stdout = output
    context = {"pd": pd, "st": st, "df": st.session_state.df.copy()}
    try:
        exec(code_str, context, context)
        st.session_state.df = context["df"]
        return True, output.getvalue(), None
    except Exception as e: return False, None, str(e)
    finally: sys.stdout = sys.__stdout__

# --- App Initialization ---
if 'df' not in st.session_state:
    st.session_state.df = pd.read_csv(CSV_PATH) if os.path.exists(CSV_PATH) else st.stop()
if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'ordering_lists' not in st.session_state: st.session_state.ordering_lists = load_json(ORDER_LISTS_PATH)
if 'purchases' not in st.session_state: st.session_state.purchases = load_json(PURCHASES_PATH)
if 'checkpoints' not in st.session_state: st.session_state.checkpoints = load_json(CHECKPOINT_PATH)

# --- UI Interface ---
tabs = st.tabs(["📊 Data View", "🧠 Agentic Chatbot", "📝 Ordering Lists", "📦 Orders", "🛒 Purchase"])
tab1, tab2, tab3, tab4, tab5 = tabs

with tab1:
    st.dataframe(st.session_state.df, use_container_width=True, hide_index=True)

with tab2:
    for i, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                st.download_button(label="📥 Download PDF", data=create_pdf(msg["content"]), file_name=f"res_{i}.pdf", key=f"chat_{i}")

    if prompt := st.chat_input("Ask the Data Agent..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        retries, success = 0, False
        status = st.status("Agent is working...", expanded=True)
        while retries < 3:
            history_context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[-5:]])
            coder_prompt = f"You are a Python Data Agent managing 'df'.\nCOLUMNS: {list(st.session_state.df.columns)}\nHISTORY: {history_context}\nTASK: {prompt}\nCRITICAL RULES: 1. For updates, use df.loc. 2. If Profit Margin updated, recalculate Final Price. 3. Return ONLY ```python blocks."
            res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": coder_prompt}], temperature=0)
            code_match = re.search(r"```python\n(.*?)\n```", res.choices[0].message.content, re.DOTALL)
            if not code_match: retries += 1; continue
            code = code_match.group(1)
            run_ok, out, err = execute_code(code)
            rev_prompt = f"User Task: {prompt}\nCode Ran: {code}\nResult: {out if run_ok else err}\nFriendly response: 'SUCCESS: [Answer]' or 'RETRY: [Reason]'"
            rev_res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": rev_prompt}], temperature=0)
            decision = rev_res.choices[0].message.content
            if "RETRY" in decision: retries += 1
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": decision.replace("SUCCESS:", "").strip()})
                success = True; break
        status.update(label="Complete!", state="complete", expanded=False)
        if success: st.rerun()

with tab3:
    st.header("Upload Ordering Lists")
    ups = st.file_uploader("Upload PO Images", type=['jpg','png','jpeg'], accept_multiple_files=True)
    if st.button("Process Images") and ups:
        with st.spinner("AI Reading..."):
            for f in ups: st.session_state.ordering_lists.append(process_order_image(f))
            save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()

with tab4:
    st.header("Order Management")
    c1, c2 = st.columns(2)
    start, end = c1.date_input("Start Date", value=datetime.now()), c2.date_input("End Date", value=datetime.now())
    visible = [(i, o) for i, o in enumerate(st.session_state.ordering_lists) if start <= datetime.fromisoformat(o['timestamp']).date() <= end]
    selected = []
    for idx, order in visible:
        col_s, col_info, col_v, col_d = st.columns([0.5, 3, 1, 1])
        comp = order.get("status") == "completed"
        if comp: col_s.write("✅")
        elif col_s.checkbox("", key=f"s_{idx}"): selected.append(idx)
        col_info.markdown(f"**{order['name']}** | {order['supplier']} | :{ 'green' if comp else 'orange' }[{order.get('status','pending').upper()}]")
        if col_v.button("View", key=f"v_{idx}"):
            @st.dialog("Details")
            def d(o, i):
                st.session_state.ordering_lists[i]['name'] = st.text_input("Name", o['name'])
                st.table(pd.DataFrame(o['orders']))
                if st.button("Save"): save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()
            d(order, idx)
        if col_d.button("🗑️", key=f"del_{idx}"):
            st.session_state.ordering_lists.pop(idx); save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()

    if st.button("Consolidate & Generate Purchases", type="primary") and selected:
        st.session_state.checkpoints.append({"timestamp": datetime.now().isoformat(), "data": json.loads(json.dumps(st.session_state.purchases)), "order_statuses": [o['status'] for o in st.session_state.ordering_lists]})
        save_json(CHECKPOINT_PATH, st.session_state.checkpoints)
        m_df = st.session_state.df.copy()
        m_df['s_name'] = m_df['Product Name'].str.lower().str.strip()
        agg = {}
        for idx in selected:
            st.session_state.ordering_lists[idx]['status'] = 'completed'
            for item in st.session_state.ordering_lists[idx]['orders']:
                raw = str(item['product_name']).strip()
                match = m_df[m_df['s_name'] == raw.lower()]
                if not match.empty:
                    best = match.sort_values('Vendor Price').iloc[0]
                    dlr = best['Vendor Name']
                    if dlr not in agg: agg[dlr] = {}
                    if raw not in agg[dlr]: agg[dlr][raw] = {"q": float(item['quantity']), "pk": float(item['packing_size']), "pr": float(best['Vendor Price'])}
                    else: agg[dlr][raw]["q"] += float(item['quantity'])
        
        st.session_state.purchases = [{"vendor": v, "date": datetime.now().strftime("%d %m %Y"), "items": [calculate_purchase_metrics(pn, d['q'], d['pk'], d['pr']) for pn, d in p.items()]} for v, p in agg.items()]
        save_json(PURCHASES_PATH, st.session_state.purchases); save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()

with tab5:
    st.header("Financial Purchases")
    if st.session_state.checkpoints:
        with st.expander("🔄 Revert to Checkpoint"):
            rev = st.number_input("Iter #", min_value=1, value=len(st.session_state.checkpoints))
            if st.button("Apply"):
                cp = st.session_state.checkpoints[rev-1]
                st.session_state.purchases = cp["data"]
                for i, s in enumerate(cp["order_statuses"]): st.session_state.ordering_lists[i]['status'] = s
                save_json(PURCHASES_PATH, st.session_state.purchases); save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()

    if not st.session_state.purchases: st.info("No data.")
    else:
        for pur in st.session_state.purchases:
            with st.expander(f"Supplier: {pur['vendor']} | Date: {pur['date']}", expanded=True):
                df_p = pd.DataFrame(pur['items'])
                st.dataframe(df_p, hide_index=True)
                
                # Financial Summary Layout from Image
                st.markdown("---")
                c1, c2, c3, c4 = st.columns(4)
                raw_sum = df_p["Total Cost (RAW)"].sum()
                sell_sum = df_p["Total Selling"].sum()
                prof_sum = df_p["TOTAL PROFIT ($)"].sum()
                gst_sum = raw_sum * 0.09
                
                with c1:
                    st.write("**Purchase**")
                    st.write(f"SUB TOTAL: ${raw_sum:,.2f}")
                    st.write(f"TOTAL: ${raw_sum:,.2f}")
                with c2:
                    st.write("**Cost (W/GST)**")
                    st.write(f"Total Cost: ${raw_sum:,.2f}")
                    st.write(f"9% GST: ${gst_sum:,.2f}")
                    st.write(f"**TOTAL AMT: ${(raw_sum + gst_sum):,.2f}**")
                with c3:
                    st.write("**Sales**")
                    st.write(f"Total Selling: ${sell_sum:,.2f}")
                with c4:
                    st.write("**Profitability**")
                    st.write(f"Total Profit: ${prof_sum:,.2f}")
                    p_margin = (prof_sum / (raw_sum + gst_sum)) * 100 if (raw_sum + gst_sum) > 0 else 0
                    st.write(f"Profit over Cost: {p_margin:.2f}%")
                
                # Export Buttons
                st.markdown("---")
                ex1, ex2 = st.columns(2)
                ex1.download_button("📥 Excel Purchase Order", create_formatted_excel(pur['vendor'], pur['date'], df_p), f"PO_{pur['vendor']}.xlsx", key=f"ex_{pur['vendor']}")
                ex2.download_button("📥 PDF Purchase Order", create_purchase_order_pdf(pur['vendor'], pur['date'], df_p), f"PO_{pur['vendor']}.pdf", key=f"pdf_{pur['vendor']}")
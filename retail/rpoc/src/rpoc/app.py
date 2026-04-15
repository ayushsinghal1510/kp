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

st.set_page_config(layout="wide", page_title="Supply Chain Multi-Agent System")

# --- File Paths ---
CSV_PATH = 'assets/data.csv'
ORDER_LISTS_PATH = 'assets/ordering_lists.json'
INVOICES_PATH = 'assets/invoices.json'
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

def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# --- Core Business Logic: Financial Calculations ---
def calculate_invoice_metrics(product_name, qty_ctn, packing_size, ctn_price):
    qty_ctn = float(qty_ctn)
    packing_size = float(packing_size)
    total_ordered_qty = qty_ctn * packing_size
    unit_price_raw = ctn_price / packing_size
    total_cost_raw = qty_ctn * ctn_price
    
    # GST and Markup logic applied to the consolidated quantity
    unit_cost_gst = unit_price_raw * 1.09
    ctn_price_gst = ctn_price * 1.09
    total_cost_gst = total_cost_raw * 1.09
    
    markup = random.uniform(0.25, 0.30)
    tmg_selling_price_pc = unit_price_raw * (1 + markup)
    total_selling = tmg_selling_price_pc * total_ordered_qty
    
    unit_profit = tmg_selling_price_pc - unit_price_raw
    total_profit = total_selling - total_cost_raw
    profit_margin = (total_profit / total_selling) * 100 if total_selling > 0 else 0
    
    return {
        "Product Name": product_name,
        "Qty (CTN)": qty_ctn,
        "Packing Size (PC)": packing_size,
        "Total Ordered Qty": total_ordered_qty,
        "Ctn Price (SGD) (W/O GST)": round(ctn_price, 2),
        "Unit Price (SGD) (W/O GST)": round(unit_price_raw, 4),
        "Total (RAW)": round(total_cost_raw, 2),
        "Unit Cost (SGD - PC) (W/O GST)": round(unit_price_raw, 4),
        "Total Cost (RAW)": round(total_cost_raw, 2),
        "Unit Cost (9%) (SGD - PC)": round(unit_cost_gst, 4),
        "Ctn Price (9%) (SGD)": round(ctn_price_gst, 2),
        "Total Cost (SGD) (W GST)": round(total_cost_gst, 2),
        "TMG Selling Price per piece": round(tmg_selling_price_pc, 4),
        "Total Selling": round(total_selling, 2),
        "UNIT PROFIT ($)": round(unit_profit, 4),
        "TOTAL PROFIT ($)": round(total_profit, 2),
        "Profit Margin - %": round(profit_margin, 2)
    }

# --- Vision Processing (Llama 4 Scout) ---
def process_order_image(uploaded_file):
    base64_image = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    prompt = """Extract details from this Purchase Order into JSON format. 
    Keys: supplier, purchase_order_date, orders (list of {product_name, quantity, packing_size})."""
    
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
        ]}],
        response_format={"type": "json_object"}
    )
    data = json.loads(completion.choices[0].message.content)
    return {
        "filename": uploaded_file.name,
        "name": f"Order_{datetime.now().strftime('%H%M%S')}",
        "supplier": data.get("supplier"),
        "purchase_order_date": data.get("purchase_order_date"),
        "orders": data.get("orders", []),
        "status": "pending",
        "timestamp": datetime.now().isoformat()
    }

# --- Session State ---
if 'df' not in st.session_state:
    if os.path.exists(CSV_PATH): st.session_state.df = pd.read_csv(CSV_PATH)
    else: st.error("CSV missing"); st.stop()

if 'chat_history' not in st.session_state: st.session_state.chat_history = []
if 'ordering_lists' not in st.session_state: st.session_state.ordering_lists = load_json(ORDER_LISTS_PATH)
if 'invoices' not in st.session_state: st.session_state.invoices = load_json(INVOICES_PATH)
if 'checkpoints' not in st.session_state: st.session_state.checkpoints = load_json(CHECKPOINT_PATH)

def execute_code(code_str):
    output = io.StringIO()
    sys.stdout = output
    context = {"pd": pd, "st": st, "df": st.session_state.df.copy()}
    try:
        exec(code_str, context, context)
        st.session_state.df = context["df"]
        st.session_state.df.to_csv(CSV_PATH, index=False)
        return True, output.getvalue(), None
    except Exception as e: return False, None, str(e)
    finally: sys.stdout = sys.__stdout__

# --- UI Tabs ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Data View", "🧠 Agentic Chatbot", "📝 Ordering Lists", "📦 Orders", "🧾 Invoices"])

with tab1:
    st.dataframe(st.session_state.df, use_container_width=True, hide_index=True)

with tab2:
    for i, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                pdf_bytes = create_pdf(msg["content"])
                st.download_button(label="📥 PDF", data=pdf_bytes, file_name=f"res_{i}.pdf", key=f"btn_{i}")

    if prompt := st.chat_input("Ask the Data Agent..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        retries, success = 0, False
        status = st.status("Agent processing...", expanded=True)
        while retries < 3:
            history_context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[-5:]])
            coder_prompt = f"Agent managing 'df'. Columns: {list(st.session_state.df.columns)}\n{history_context}\nTASK: {prompt}\nReturn ONLY ```python blocks."
            res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "system", "content": coder_prompt}], temperature=0)
            code_match = re.search(r"```python\n(.*?)\n```", res.choices[0].message.content, re.DOTALL)
            if not code_match: retries += 1; continue
            code = code_match.group(1)
            run_ok, out, err = execute_code(code)
            review_prompt = f"Task: {prompt}\nResult: {out if run_ok else err}\nConfirm success friendly: 'SUCCESS: [Answer]' or 'RETRY: [Reason]'"
            rev_res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": review_prompt}], temperature=0)
            decision = rev_res.choices[0].message.content
            if "RETRY" in decision: retries += 1
            else:
                st.session_state.chat_history.append({"role": "assistant", "content": decision.replace("SUCCESS:", "").strip()})
                success = True; break
        status.update(label="Complete!", state="complete", expanded=False)
        if success: st.rerun()

with tab3:
    st.header("Upload Ordering Lists")
    uploads = st.file_uploader("Upload PO Images", type=['jpg','png','jpeg'], accept_multiple_files=True)
    if st.button("Process Uploads") and uploads:
        with st.spinner("Processing..."):
            for f in uploads: st.session_state.ordering_lists.append(process_order_image(f))
            save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
            st.success("Orders saved!")

with tab4:
    st.header("Order Management")
    c1, c2 = st.columns(2)
    start, end = c1.date_input("Start Date", value=datetime.now()), c2.date_input("End Date", value=datetime.now())
    
    visible_orders = [(i, o) for i, o in enumerate(st.session_state.ordering_lists) 
                      if start <= datetime.fromisoformat(o['timestamp']).date() <= end]
    
    selected_indices = []
    if visible_orders:
        for idx, order in visible_orders:
            col_sel, col_info, col_v, col_d = st.columns([0.5, 3, 1, 1])
            is_completed = order.get("status") == "completed"
            if is_completed:
                col_sel.write("✅")
                is_ch = False
            else:
                is_ch = col_sel.checkbox("", key=f"sel_{idx}")
            if is_ch: selected_indices.append(idx)
            
            status_color = "green" if is_completed else "orange"
            col_info.markdown(f"**{order['name']}** | {order['supplier']} | :{status_color}[{order.get('status', 'pending').upper()}]")
            
            if col_v.button("View", key=f"v_{idx}"):
                @st.dialog("Details")
                def d(o, i):
                    st.session_state.ordering_lists[i]['name'] = st.text_input("Name", o['name'])
                    st.table(pd.DataFrame(o['orders']))
                    if st.button("Save"): save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()
                d(order, idx)
            if col_d.button("🗑️", key=f"d_{idx}"):
                st.session_state.ordering_lists.pop(idx)
                save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists); st.rerun()

        if st.button("Generate Detailed Invoices", type="primary"):
            st.session_state.checkpoints.append({
                "timestamp": datetime.now().isoformat(), 
                "data": json.loads(json.dumps(st.session_state.invoices)),
                "order_statuses": [o['status'] for o in st.session_state.ordering_lists]
            })
            save_json(CHECKPOINT_PATH, st.session_state.checkpoints)

            m_df = st.session_state.df.copy()
            m_df['s_name'] = m_df['Product Name'].str.lower().str.strip()
            
            # Use an aggregation dictionary to group products across multiple selected orders
            vendor_aggregation = {} # { dealer: { product_name: {qty, pack, ctn_price} } }
            missing = []

            for idx in selected_indices:
                st.session_state.ordering_lists[idx]['status'] = 'completed'
                for item in st.session_state.ordering_lists[idx]['orders']:
                    raw_name = str(item['product_name']).strip()
                    low_n = raw_name.lower()
                    match = m_df[m_df['s_name'] == low_n]
                    
                    if not match.empty:
                        best = match.sort_values('Vendor Price').iloc[0]
                        dealer = best['Dealer']
                        
                        if dealer not in vendor_aggregation:
                            vendor_aggregation[dealer] = {}
                        
                        # Consolidate duplicate products by adding quantities
                        if raw_name not in vendor_aggregation[dealer]:
                            vendor_aggregation[dealer][raw_name] = {
                                "qty": float(item['quantity']),
                                "pack": float(item['packing_size']),
                                "price": float(best['Vendor Price'])
                            }
                        else:
                            vendor_aggregation[dealer][raw_name]["qty"] += float(item['quantity'])
                    else:
                        close = difflib.get_close_matches(low_n, m_df['s_name'].tolist(), n=1, cutoff=0.6)
                        missing.append({"Original": raw_name, "Closest Match": close[0] if close else "None"})

            # Re-generate the full invoice data using consolidated totals
            consolidated_invoices = []
            for vendor, products in vendor_aggregation.items():
                items_list = []
                for p_name, p_data in products.items():
                    items_list.append(calculate_invoice_metrics(
                        p_name, p_data['qty'], p_data['pack'], p_data['price']
                    ))
                
                consolidated_invoices.append({
                    "vendor": vendor,
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "items": items_list
                })

            st.session_state.invoices = consolidated_invoices
            save_json(INVOICES_PATH, st.session_state.invoices)
            save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
            if missing: st.warning("Database Gaps Found"); st.table(pd.DataFrame(missing))
            st.success("Detailed Consolidated Invoices Generated!")
            st.rerun()

with tab5:
    st.header("Financial Invoices")
    if st.session_state.checkpoints:
        with st.expander("🔄 Revert to Checkpoint"):
            rev_idx = st.number_input("Iteration", min_value=1, value=len(st.session_state.checkpoints))
            if st.button("Apply Revert"):
                target = 0 if rev_idx > len(st.session_state.checkpoints) else rev_idx - 1
                cp = st.session_state.checkpoints[target]
                st.session_state.invoices = cp["data"]
                for i, s in enumerate(cp.get("order_statuses", [])):
                    if i < len(st.session_state.ordering_lists): st.session_state.ordering_lists[i]['status'] = s
                save_json(INVOICES_PATH, st.session_state.invoices)
                save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
                st.rerun()

    if not st.session_state.invoices: st.info("No invoices yet.")
    else:
        for inv in st.session_state.invoices:
            with st.expander(f"Invoice: {inv['vendor']} | {inv['date']}", expanded=True):
                df_inv = pd.DataFrame(inv['items'])
                st.dataframe(df_inv, hide_index=True)
                st.markdown("---")
                c1, c2, c3, c4 = st.columns(4)
                cost_raw, selling_t, profit_t = df_inv["Total Cost (RAW)"].sum(), df_inv["Total Selling"].sum(), df_inv["TOTAL PROFIT ($)"].sum()
                gst = cost_raw * 0.09
                with c1: st.write("**Purchase**"); st.write(f"SUB TOTAL: ${cost_raw:,.2f}"); st.write(f"**TOTAL: ${cost_raw:,.2f}**")
                with c2: st.write("**Cost (W/GST)**"); st.write(f"Total Cost: ${cost_raw:,.2f}"); st.write(f"9% GST: ${gst:,.2f}"); st.write(f"**TOTAL AMT: ${(cost_raw + gst):,.2f}**")
                with c3: st.write("**Sales**"); st.write(f"Total Selling: ${selling_t:,.2f}")
                with c4: st.write("**Profitability**"); st.write(f"Total Profit: ${profit_t:,.2f}"); p_over = (profit_t/(cost_raw+gst))*100 if (cost_raw+gst)>0 else 0; st.write(f"**Profit over Cost: {p_over:.2f}%**")
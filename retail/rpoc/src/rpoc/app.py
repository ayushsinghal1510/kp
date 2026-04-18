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
CSV_PATH        = 'assets/data.csv'
ORDER_LISTS_PATH= 'assets/ordering_lists.json'
PURCHASES_PATH  = 'assets/purchases.json'
CHECKPOINT_PATH = 'assets/checkpoints.json'
PO_COUNTER_PATH = 'assets/po_counter.json'

os.makedirs('assets', exist_ok=True)

# --- Master CSV Columns ---
GST_COLUMN_VARIANTS = [
    'Unit Cost (9%)\n(SGD - PC)',
    'Unit Cost (9.16%)\n(SGD - PC)',
]

MASTER_COLUMNS = [
    'No.', 'Product Name', 'Packing Size\n(PC)', 'Ctn Price\n(SGD)\n(W/O GST)',
    'Unit Price\n(SGD)\n(W/O GST)', 'Unit Cost \n(SGD - PC)\n(W/O GST)',
    'Unit Cost (9%)\n(SGD - PC)', 'Unit Cost (9.16%)\n(SGD - PC)',
    'TMG Selling Price', 'UNIT PROFIT ($)',
    'Profit Margin - % ', 'TMG\nPromotion\nPrice', 'Supplier'
]

def detect_gst_column(price_data_columns):
    for variant in GST_COLUMN_VARIANTS:
        if variant in price_data_columns:
            return variant
    return None

# ── Persistence ───────────────────────────────────────────────
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

def get_next_po_number():
    counter_data = load_json(PO_COUNTER_PATH)
    if not counter_data or not isinstance(counter_data, dict):
        counter_data = {"counter": 0}
    counter_data["counter"] += 1
    save_json(PO_COUNTER_PATH, counter_data)
    return f"PO-{counter_data['counter']:05d}"

def load_master_csv():
    if os.path.exists(CSV_PATH):
        df = pd.read_csv(CSV_PATH)
        for col in MASTER_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        return df
    return pd.DataFrame(columns=MASTER_COLUMNS)

def save_master_csv(df):
    df.to_csv(CSV_PATH, index=False)

# ── Helper: packing size lookup ───────────────────────────────
def get_packing_size(product_name, master_df):
    if master_df.empty or 'Product Name' not in master_df.columns:
        return 0.0
    col = 'Packing Size\n(PC)'
    match = master_df[
        master_df['Product Name'].str.strip().str.lower() == product_name.strip().lower()
    ]
    if not match.empty and col in match.columns:
        try:
            return float(match.iloc[0][col])
        except Exception:
            return 0.0
    return 0.0

# ── Excel upload processor ────────────────────────────────────
def process_uploaded_excel(uploaded_file):
    raw = pd.read_excel(uploaded_file, header=None)
    try:
        supplier_cell = str(raw.iloc[2, 1])
        if supplier_cell == 'nan':
            supplier_cell = str(raw.iloc[3, 1])
        supplier = supplier_cell.split(':', 1)[1].strip() if ':' in supplier_cell else supplier_cell.strip()
        if not supplier or supplier == 'nan':
            supplier = "Unknown"
    except Exception:
        supplier = "Unknown"

    price_data = pd.read_excel(uploaded_file, header=5)
    unnamed_cols = [c for c in price_data.columns if str(c).startswith('Unnamed:')]
    price_data.drop(columns=unnamed_cols, inplace=True, errors='ignore')
    price_data.dropna(how='all', inplace=True)

    def safe_get(df, col):
        return df[col] if col in df.columns else np.nan

    out = pd.DataFrame()
    out['No.']                                = safe_get(price_data, 'No.')
    out['Product Name']                       = safe_get(price_data, 'Product Name')
    out['Packing Size\n(PC)']                = safe_get(price_data, 'Packing Size\n(PC)')
    out['Ctn Price\n(SGD)\n(W/O GST)']       = safe_get(price_data, 'Ctn Price\n(SGD)\n(W/O GST)')
    out['Unit Price\n(SGD)\n(W/O GST)']      = safe_get(price_data, 'Unit Price\n(SGD)\n(W/O GST)')
    out['Unit Cost \n(SGD - PC)\n(W/O GST)'] = safe_get(price_data, 'Unit Cost \n(SGD - PC)\n(W/O GST)')

    detected_gst_col = detect_gst_column(price_data.columns.tolist())
    for gst_col in GST_COLUMN_VARIANTS:
        out[gst_col] = safe_get(price_data, gst_col) if gst_col == detected_gst_col else 0

    out['TMG Selling Price']    = safe_get(price_data, 'TMG Selling Price')
    out['UNIT PROFIT ($)']      = safe_get(price_data, 'UNIT PROFIT ($)')
    out['Profit Margin - % ']   = safe_get(price_data, 'Profit Margin - % ')
    out['TMG\nPromotion\nPrice']= safe_get(price_data, 'TMG Selling Price')
    out['Supplier']             = supplier

    out.dropna(subset=['Product Name'], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out, supplier

# ── Chat PDF helper ───────────────────────────────────────────
def create_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.multi_cell(0, 10, txt=text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output(dest='S').encode('latin-1')

# ── Safe value helper (prevents NaN/INF in xlsxwriter) ────────
def safe_num(v, default=0):
    """Return a safe numeric value for xlsxwriter — no NaN or inf."""
    if v is None:
        return default
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default

def safe_str(v, default=''):
    """Return a safe string, converting NaN/None to empty string."""
    if v is None:
        return default
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return default
    return str(v)

# =============================================================
# EXCEL EXPORT — Exact Tian Ma Group Holdings PO format
# =============================================================
def _get_gst_info(df_items):
    """Return (rate_float, col_key_in_items, label_str) for the active GST column."""
    c916 = 'Unit Cost (9.16%) (SGD - PC)'
    if c916 in df_items.columns and (df_items[c916].fillna(0) != 0).any():
        return 9.16, c916, '9.16%'
    return 9.0, 'Unit Cost (9%) (SGD - PC)', '9%'


def build_tmg_excel(vendor, date, po_number, df_items,
                    include_wogst=True, include_wgst=True, include_profit=True):
    """
    Generates an Excel PO in the exact Tian Ma Group Holdings style.
    Matches the reference image exactly — colours, column sizes, layout.
    """
    gst_rate, gst_key, gst_label = _get_gst_info(df_items)
    gst_mult = 1 + gst_rate / 100

    # Sanitise vendor/po_number so they're never NaN
    vendor    = safe_str(vendor, 'Unknown')
    po_number = safe_str(po_number, 'N/A')
    date      = safe_str(date, '')

    output = io.BytesIO()
    wb = pd.ExcelWriter(output, engine='xlsxwriter',
                        engine_kwargs={'options': {'nan_inf_to_errors': True}}).book
    ws = wb.add_worksheet('Purchase Order')

    # ── Colour constants ──────────────────────────────────────
    C_WHITE   = '#FFFFFF'
    C_LGREY   = '#D9D9D9'
    C_GREEN1  = '#92D050'   # bright lime green (header cells)
    C_GREEN2  = '#00B050'   # darker green (profit header)
    C_YELLOW  = '#FFFF00'
    C_BLACK   = '#000000'
    C_RED     = '#FF0000'

    # ── Format factory ────────────────────────────────────────
    def F(bold=False, bg=C_WHITE, fc=C_BLACK, border=1,
          align='center', valign='vcenter', num_fmt=None,
          sz=9, wrap=True, italic=False, border_color=None):
        d = dict(bold=bold, bg_color=bg, font_color=fc, border=border,
                 align=align, valign=valign, font_size=sz,
                 italic=italic, text_wrap=wrap)
        if num_fmt:
            d['num_format'] = num_fmt
        if border_color:
            d['border_color'] = border_color
        return wb.add_format(d)

    # ── Named formats (mirrors the image exactly) ─────────────
    f_title      = F(bold=True,  sz=16, border=0, align='center', fc=C_BLACK)
    f_addr       = F(sz=9,       border=0, align='center')
    f_date_lbl   = F(bold=True,  sz=10, border=0, align='right')
    f_date_val   = F(bold=False, sz=10, border=0, align='left')
    f_sup_lbl    = F(bold=True,  sz=10, border=1, align='left')
    f_sup_val    = F(sz=10,      border=1, align='left')
    f_rate_lbl   = F(bold=True,  sz=10, border=1, align='right')
    f_rate_val   = F(sz=10,      border=1, align='left')
    f_po_num     = F(bold=True,  sz=10, border=0, align='center')

    # Section banners
    f_banner_po  = F(bold=True,  sz=12, border=1, align='center', bg=C_WHITE)
    f_banner_gst = F(bold=True,  sz=12, border=1, align='center', bg=C_GREEN1)

    # Column headers — left (grey) and right (green)
    f_hdr_grey   = F(bold=True,  sz=8,  border=1, bg=C_LGREY,  align='center', wrap=True)
    f_hdr_g1     = F(bold=True,  sz=8,  border=1, bg=C_GREEN1, align='center', wrap=True)
    f_hdr_g2     = F(bold=True,  sz=8,  border=1, bg=C_GREEN2, align='center', wrap=True, fc=C_WHITE)

    # Data cells
    f_cell       = F(sz=8,  border=1, align='center')
    f_cell_l     = F(sz=8,  border=1, align='left')
    f_money4     = F(sz=8,  border=1, align='right',  num_fmt='$#,##0.0000')
    f_money2     = F(sz=8,  border=1, align='right',  num_fmt='$#,##0.00')
    f_pct        = F(sz=8,  border=1, align='center', num_fmt='0.00%')

    # Green-bg data cells (cost/profit columns)
    f_g1_m4      = F(sz=8,  border=1, bg=C_GREEN1, align='right',  num_fmt='$#,##0.0000')
    f_g1_m2      = F(sz=8,  border=1, bg=C_GREEN1, align='right',  num_fmt='$#,##0.00')
    f_g1_c       = F(sz=8,  border=1, bg=C_GREEN1, align='center')
    f_g1_pct     = F(sz=8,  border=1, bg=C_GREEN1, align='center', num_fmt='0.00%')
    f_g1_pct_txt = F(sz=8,  border=1, bg=C_GREEN1, align='center')

    # Summary label/value formats
    f_lbl_grey   = F(bold=True, sz=8, border=1, align='right',  bg=C_LGREY)
    f_lbl_g1     = F(bold=True, sz=8, border=1, align='right',  bg=C_GREEN1)
    f_lbl_wh     = F(bold=True, sz=8, border=1, align='right',  bg=C_WHITE)
    f_val_wh     = F(bold=True, sz=8, border=1, align='right',  bg=C_WHITE,  num_fmt='$#,##0.0000')
    f_val_wh2    = F(bold=True, sz=8, border=1, align='right',  bg=C_WHITE,  num_fmt='$#,##0.00')
    f_val_g1     = F(bold=True, sz=8, border=1, align='right',  bg=C_GREEN1, num_fmt='$#,##0.0000')
    f_val_g1_2   = F(bold=True, sz=8, border=1, align='right',  bg=C_GREEN1, num_fmt='$#,##0.00')
    f_val_g1_c   = F(bold=True, sz=8, border=1, align='center', bg=C_GREEN1)
    f_yellow_c   = F(bold=True, sz=8, border=1, align='center', bg=C_YELLOW)
    f_sig        = F(bold=True, sz=8, border=1, align='center')

    # ── Column blueprint: (key, header, width_chars, data_fmt, hdr_fmt) ──
    LEFT_COLS = [
        ('no',    'No.',                   4,   f_cell,   f_hdr_grey),
        ('name',  'Product Name',          28,  f_cell_l, f_hdr_grey),
        ('qty',   'Qty\n(CTN)',            7,   f_cell,   f_hdr_grey),
        ('pk',    'Packing\nSize\n(PC)',   7,   f_cell,   f_hdr_grey),
        ('tqty',  'Total\nOrdered\nQty',  9,   f_cell,   f_hdr_grey),
    ]
    WOGST_COLS = [
        ('ctn_p',  'Ctn Price\n(SGD)\n(W/O GST)',       13, f_money4, f_hdr_grey),
        ('unit_p', 'Unit Price\n(SGD)\n(W/O GST)',      13, f_money4, f_hdr_grey),
        ('total',  'Total',                              12, f_money2, f_hdr_grey),
        ('uc_wog', 'Unit Cost\n(SGD - PC)\n(W/O GST)',  13, f_money4, f_hdr_g1),
        ('raw',    'Total Cost\n(RAW)',                  13, f_money2, f_hdr_g1),
    ]
    WGST_COLS = [
        ('uc_gst', f'Unit Cost\n({gst_label})\n(SGD - PC)', 13, f_money4, f_hdr_g1),
        ('tc_gst', 'Total Cost\n(SGD)\n(W GST)',             13, f_money2, f_hdr_g1),
    ]
    PROFIT_COLS = [
        ('sell_pp', 'TMG\nSelling\nPrice',   12, f_g1_m4,     f_hdr_g2),
        ('tot_sel', 'Total\nSelling',         13, f_g1_m2,     f_hdr_g2),
        ('u_prof',  'UNIT\nPROFIT ($)',       12, f_g1_m4,     f_hdr_g2),
        ('t_prof',  'TOTAL\nPROFIT($)',       13, f_g1_m2,     f_hdr_g2),
        ('margin',  'Profit\nMargin - %',     11, f_g1_pct,    f_hdr_g2),
        ('promo',   'TMG\nPromotion\nPrice',  12, f_g1_m4,     f_hdr_g2),
    ]

    cols = list(LEFT_COLS)
    if include_wogst:  cols += WOGST_COLS
    if include_wgst:   cols += WGST_COLS
    if include_profit: cols += PROFIT_COLS
    n_cols = len(cols)
    col_keys = [c[0] for c in cols]

    def cix(k):
        return col_keys.index(k) if k in col_keys else None

    # ── Column widths & default row heights ───────────────────
    for ci, (_, _, w, _, _) in enumerate(cols):
        ws.set_column(ci, ci, w)
    ws.set_row(0, 28)   # title
    ws.set_row(1, 18)   # address
    ws.set_row(2, 18)   # date / supplier / rate  (split across 3 sub-rows 2-4)
    ws.set_row(3, 18)
    ws.set_row(4, 18)
    ws.set_row(5, 18)   # PO banner
    ws.set_row(6, 40)   # column headers

    # ── ROW 0: Company title ──────────────────────────────────
    # Title spans all but last ~4 cols; Date on the right
    title_end = max(n_cols - 5, n_cols // 2)
    ws.merge_range(0, 0, 0, title_end - 1, 'Tian Ma Group Holdings Pte Ltd', f_title)
    ws.merge_range(0, title_end, 0, n_cols - 1, '', f_date_lbl)

    # ── ROW 1: Address (left) ─────────────────────────────────
    ws.merge_range(1, 0, 1, title_end - 1,
                   '9 Changi South Street 3 #07-02/03 Singapore 486361', f_addr)
    # Date label+value on the right (rows 0-1 mimic the image layout)
    ws.merge_range(1, title_end, 1, n_cols - 1, f'Date:    {date}', f_date_lbl)

    # ── ROW 2: Supplier label | value | Rate label | value ────
    ws.write(2, 0, 'Supplier:', f_sup_lbl)
    # supplier value spans several columns
    sup_val_end = min(title_end - 3, n_cols - 1)
    if sup_val_end > 0:
        ws.merge_range(2, 1, 2, sup_val_end, vendor, f_sup_val)
    ws.merge_range(2, sup_val_end + 1, 2, n_cols - 1, 'Rate :    3.290', f_rate_lbl)

    # ── ROW 3: PO number ──────────────────────────────────────
    ws.merge_range(3, 0, 3, n_cols - 1, f'PO Number: {po_number}', f_po_num)

    # ── ROW 4: empty spacer row (as in the image) ─────────────
    ws.set_row(4, 6)

    # ── ROW 5: Section banners ────────────────────────────────
    left_section_end = len(LEFT_COLS) + (len(WOGST_COLS) if include_wogst else 0) - 1
    ws.merge_range(5, 0, 5, left_section_end, 'PURCHASE ORDER', f_banner_po)
    right_start = left_section_end + 1
    if right_start < n_cols:
        parts = []
        if include_wgst:   parts.append(f'Cost with Freight & {gst_label} GST')
        if include_profit: parts.append('Selling with GST')
        ws.merge_range(5, right_start, 5, n_cols - 1, ', '.join(parts), f_banner_gst)

    # ── ROW 6: Column headers ─────────────────────────────────
    wgst_keys   = {c[0] for c in WGST_COLS}
    profit_keys = {c[0] for c in PROFIT_COLS}

    for ci, (key, label, _, _, hfmt) in enumerate(cols):
        ws.write(6, ci, label, hfmt)

    # ── Data rows (start row 7) ───────────────────────────────
    DATA_START = 7

    def item_val(row, key):
        MAP = {
            'no':     ('No.',                            ''),
            'name':   ('Product Name',                   ''),
            'qty':    ('Qty (CTN)',                       ''),
            'pk':     ('Packing Size (PC)',               ''),
            'tqty':   ('Total Ordered Qty',               ''),
            'ctn_p':  ('Ctn Price (SGD) (W/O GST)',       0),
            'unit_p': ('Unit Price (SGD) (W/O GST)',      0),
            'total':  ('Total',                           0),
            'uc_wog': ('Unit Cost (SGD - PC) (W/O GST)', 0),
            'raw':    ('Total Cost (RAW)',                 0),
            'uc_gst': (gst_key,                           0),
            'tc_gst': ('Total Cost (SGD) (W GST)',        0),
            'sell_pp':('TMG Selling Price per piece',     0),
            'tot_sel':('Total Selling',                   0),
            'u_prof': ('UNIT PROFIT ($)',                 0),
            't_prof': ('TOTAL PROFIT ($)',                0),
            'margin': ('Profit Margin - %',               0),
            'promo':  ('TMG Promotion Price',             0),
        }
        col_name, default = MAP.get(key, ('', ''))
        v = row.get(col_name, default)
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return default
        if key == 'margin' and isinstance(v, (int, float)):
            return v / 100   # Excel % format expects fraction
        return v

    for ri, (_, row) in enumerate(df_items.iterrows()):
        r = DATA_START + ri
        ws.set_row(r, 16)
        for ci, (key, _, _, dfmt, _) in enumerate(cols):
            v = item_val(row, key)
            if v == '' or v is None:
                ws.write_blank(r, ci, None, dfmt)
            elif isinstance(v, (int, float)):
                ws.write_number(r, ci, safe_num(v), dfmt)
            else:
                ws.write(r, ci, v, dfmt)

    # ── Summary rows ──────────────────────────────────────────
    n_items  = len(df_items)
    # Leave one blank row between data and summary
    s0 = DATA_START + n_items + 1

    raw_sum  = safe_num(df_items['Total Cost (RAW)'].sum()         if 'Total Cost (RAW)'          in df_items.columns else 0)
    gst_amt  = round(raw_sum * (gst_rate / 100), 2)
    wgst_sum = safe_num(df_items['Total Cost (SGD) (W GST)'].sum() if 'Total Cost (SGD) (W GST)'  in df_items.columns else raw_sum * gst_mult)
    sell_sum = safe_num(df_items['Total Selling'].sum()             if 'Total Selling'              in df_items.columns else 0)
    prof_sum = safe_num(df_items['TOTAL PROFIT ($)'].sum()         if 'TOTAL PROFIT ($)'           in df_items.columns else 0)
    psp      = (prof_sum / sell_sum * 100) if sell_sum > 0 else 0

    # Freight is 0 (fixed)
    freight  = 0.0

    ws.set_row(s0,   16)
    ws.set_row(s0+1, 16)
    ws.set_row(s0+2, 16)

    # ── LEFT block (under PURCHASE ORDER) ────────────────────
    tc = cix('total')
    if tc is None:
        raw_c_end = cix('raw')
        tc = (raw_c_end - 1) if raw_c_end else len(LEFT_COLS) - 1

    if tc is not None and tc > 0:
        ws.merge_range(s0,   0, s0,   tc - 1, 'SUB TOTAL:',            f_lbl_grey)
        ws.write_number(s0,  tc,  raw_sum,                              f_val_wh2)
        ws.merge_range(s0+1, 0, s0+1, tc - 1, 'Freight (CNF) Charge:', f_lbl_grey)
        ws.write(s0+1, tc, 'NA',                                        f_yellow_c)
        ws.merge_range(s0+2, 0, s0+2, tc - 1, 'TOTAL AMT:',            f_lbl_grey)
        ws.write_number(s0+2, tc, raw_sum,                              f_val_wh2)

    # ── MIDDLE block (Cost W/GST) ─────────────────────────────
    raw_c  = cix('raw')
    tgst_c = cix('tc_gst')

    if raw_c is not None and include_wogst:
        # "Total Cost (SGD)" label spans raw + one more if available
        label_end = tgst_c - 1 if tgst_c is not None else raw_c
        val_col   = tgst_c     if tgst_c is not None else raw_c + 1

        if label_end >= raw_c:
            ws.merge_range(s0,   raw_c, s0,   label_end, 'Total Cost:\n(SGD)', f_lbl_g1)
            ws.merge_range(s0+1, raw_c, s0+1, label_end, f'{gst_label} GST',   f_lbl_g1)
            ws.merge_range(s0+2, raw_c, s0+2, label_end, 'TOTAL AMT:',         f_lbl_g1)
        else:
            ws.write(s0,   raw_c, 'Total Cost: (SGD)', f_lbl_g1)
            ws.write(s0+1, raw_c, f'{gst_label} GST',   f_lbl_g1)
            ws.write(s0+2, raw_c, 'TOTAL AMT:',         f_lbl_g1)

        if val_col < n_cols:
            ws.write_number(s0,   val_col, raw_sum,  f_val_g1_2)
            ws.write_number(s0+1, val_col, gst_amt,  f_val_g1_2)
            ws.write_number(s0+2, val_col, wgst_sum, f_val_g1_2)

        # Freight charge cell (0) in the GST column area
        if tgst_c is not None and tgst_c < n_cols:
            ws.write_number(s0+1, tgst_c, freight, f_g1_m2)

    # ── RIGHT block (Profit) ──────────────────────────────────
    ts_c = cix('tot_sel')
    tp_c = cix('t_prof')

    if ts_c is not None and include_profit:
        # "Total Selling (SGD)" — spans tot_sel + u_prof
        ts_end = (tp_c - 1) if tp_c is not None else ts_c
        if ts_end > ts_c:
            ws.merge_range(s0, ts_c, s0, ts_end, 'Total Selling:\n(SGD)', f_lbl_g1)
        else:
            ws.write(s0, ts_c, 'Total Selling: (SGD)', f_lbl_g1)
        # value goes in TOTAL PROFIT ($) column
        if tp_c is not None and tp_c < n_cols:
            ws.write_number(s0, tp_c, sell_sum, f_val_g1_2)

    if tp_c is not None and include_profit:
        margin_c = cix('margin')
        tp_end   = (margin_c - 1) if margin_c is not None else tp_c
        if tp_end > tp_c:
            ws.merge_range(s0+1, tp_c, s0+1, tp_end, 'Total Profit:', f_lbl_g1)
        else:
            ws.write(s0+1, tp_c, 'Total Profit:', f_lbl_g1)
        if margin_c is not None and margin_c < n_cols:
            ws.write_number(s0+1, margin_c, prof_sum, f_val_g1_2)

        # "Profit over SP" row
        promo_c = cix('promo')
        last_c  = (promo_c - 1) if promo_c is not None else tp_c
        if last_c > tp_c:
            ws.merge_range(s0+2, tp_c, s0+2, last_c, 'Profit over SP', f_lbl_g1)
        else:
            ws.write(s0+2, tp_c, 'Profit over SP', f_lbl_g1)
        # value
        end_col = promo_c if promo_c is not None else (n_cols - 1)
        if end_col < n_cols:
            ws.write(s0+2, end_col, f'{psp:.3f}%', f_val_g1_c)

    # ── Signature footer ──────────────────────────────────────
    f_row = s0 + 5
    ws.set_row(f_row, 20)
    sigs  = ['ORDER BY', 'CHECKED BY', 'SUBMITTED BY', 'ACKNOWLEDGE BY', 'PRICE CHECKED BY']
    chunk = max(1, n_cols // len(sigs))
    for si, lbl in enumerate(sigs):
        c0 = si * chunk
        c1 = min(c0 + chunk - 1 if si < len(sigs) - 1 else n_cols - 1, n_cols - 1)
        if c0 >= n_cols:
            break
        if c0 == c1:
            ws.write(f_row, c0, lbl, f_sig)
        else:
            ws.merge_range(f_row, c0, f_row, c1, lbl, f_sig)

    wb.close()
    return output.getvalue()


# =============================================================
# PDF EXPORT — auto-scaled to fit A4 landscape, no overflow
# =============================================================
def build_tmg_pdf(vendor, date, po_number, df_items,
                  include_wogst=True, include_wgst=True, include_profit=True):
    gst_rate, gst_key, gst_label = _get_gst_info(df_items)
    gst_mult = 1 + gst_rate / 100

    vendor    = safe_str(vendor, 'Unknown')
    po_number = safe_str(po_number, 'N/A')
    date      = safe_str(date, '')

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    PAGE_W = 277.0   # usable landscape A4 width (297 - 2×10mm margins)

    # ── Column blueprint ──────────────────────────────────────
    LEFT = [
        ('no',     'No.',           5,  'C'),
        ('name',   'Product Name',  38, 'L'),
        ('qty',    'Qty\n(CTN)',    9,  'C'),
        ('pk',     'Pack\nSize',    9,  'C'),
        ('tqty',   'Total\nQty',   9,  'C'),
    ]
    WOGST = [
        ('ctn_p',  'Ctn Price\nW/O GST',  16, 'R'),
        ('unit_p', 'Unit Price\nW/O GST', 16, 'R'),
        ('total',  'Total',               14, 'R'),
        ('uc_wog', 'Unit Cost\nW/O GST',  16, 'R'),
        ('raw',    'Total Cost\n(RAW)',    16, 'R'),
    ]
    WGST = [
        ('uc_gst', f'Unit Cost\n({gst_label})', 16, 'R'),
        ('tc_gst', 'Total Cost\nW/GST',          16, 'R'),
    ]
    PROFIT = [
        ('sell_pp','TMG\nSelling',   13, 'R'),
        ('tot_sel','Total\nSelling', 14, 'R'),
        ('u_prof', 'Unit\nProfit',   13, 'R'),
        ('t_prof', 'Total\nProfit',  14, 'R'),
        ('margin', 'Margin %',        9, 'C'),
        ('promo',  'Promo\nPrice',   13, 'R'),
    ]

    active = list(LEFT)
    if include_wogst:  active += WOGST
    if include_wgst:   active += WGST
    if include_profit: active += PROFIT

    # Scale so everything fits in PAGE_W
    raw_w = sum(c[2] for c in active)
    scale = PAGE_W / raw_w if raw_w > PAGE_W else 1.0
    col_defs = [(key, lbl, w * scale, aln) for key, lbl, w, aln in active]

    # ── Value extractor ───────────────────────────────────────
    def item_val(row, key):
        MAP = {
            'no':     ('No.',                            ''),
            'name':   ('Product Name',                   ''),
            'qty':    ('Qty (CTN)',                       ''),
            'pk':     ('Packing Size (PC)',               ''),
            'tqty':   ('Total Ordered Qty',               ''),
            'ctn_p':  ('Ctn Price (SGD) (W/O GST)',       0),
            'unit_p': ('Unit Price (SGD) (W/O GST)',      0),
            'total':  ('Total',                           0),
            'uc_wog': ('Unit Cost (SGD - PC) (W/O GST)', 0),
            'raw':    ('Total Cost (RAW)',                 0),
            'uc_gst': (gst_key,                           0),
            'tc_gst': ('Total Cost (SGD) (W GST)',        0),
            'sell_pp':('TMG Selling Price per piece',     0),
            'tot_sel':('Total Selling',                   0),
            'u_prof': ('UNIT PROFIT ($)',                 0),
            't_prof': ('TOTAL PROFIT ($)',                0),
            'margin': ('Profit Margin - %',               0),
            'promo':  ('TMG Promotion Price',             0),
        }
        col_name, default = MAP.get(key, ('', ''))
        v = row.get(col_name, default)
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return default
        return v

    def fmt_val(key, v):
        money4 = {'ctn_p','unit_p','uc_wog','uc_gst','sell_pp','u_prof','promo'}
        money2 = {'total','raw','tc_gst','tot_sel','t_prof'}
        if isinstance(v, (int, float)):
            if key in money4: return f'${v:,.4f}'
            if key in money2: return f'${v:,.2f}'
            if key == 'margin': return f'{v:.2f}%'
        return str(v) if v != '' else ''

    def set_fill(r, g, b):
        pdf.set_fill_color(r, g, b)

    # ── Page header ───────────────────────────────────────────
    pdf.set_font('Arial', 'B', 13)
    title_w = PAGE_W * 0.70
    pdf.cell(title_w, 7, 'Tian Ma Group Holdings Pte Ltd', align='C')
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(PAGE_W - title_w, 7, f'Date: {date}', align='R', ln=True)

    pdf.set_font('Arial', '', 8)
    pdf.cell(title_w, 5, '9 Changi South Street 3 #07-02/03 Singapore 486361', align='C')
    pdf.cell(PAGE_W - title_w, 5, 'Rate : 3.290', align='R', ln=True)
    pdf.ln(1)

    pdf.set_font('Arial', 'B', 9)
    hw = PAGE_W
    pdf.cell(hw * 0.50, 5, f'Supplier: {vendor}', border=1)
    pdf.cell(hw * 0.30, 5, f'PO#: {po_number}', border=1, align='C', ln=True)
    pdf.ln(1)

    # ── Section banners ───────────────────────────────────────
    left_w  = sum(c[2] for c in col_defs[:len(LEFT)])
    wogst_w = sum(c[2] for c in col_defs[len(LEFT):len(LEFT) + (len(WOGST) if include_wogst else 0)])
    right_w = sum(c[2] for c in col_defs[len(LEFT) + (len(WOGST) if include_wogst else 0):])

    pdf.set_font('Arial', 'B', 9)
    set_fill(255, 255, 255)
    pdf.cell(left_w + wogst_w, 6, 'PURCHASE ORDER', border=1, align='C', fill=True)
    if right_w > 0:
        set_fill(146, 208, 80)
        parts = []
        if include_wgst:   parts.append(f'Cost/Freight/{gst_label} GST')
        if include_profit: parts.append('Selling with GST')
        pdf.cell(right_w, 6, '  |  '.join(parts), border=1, align='C', fill=True)
    pdf.ln()
    set_fill(255, 255, 255)

    # ── Column headers ────────────────────────────────────────
    HDR_H = 8
    pdf.set_font('Arial', 'B', 6)
    wgst_keys   = {c[0] for c in WGST}
    profit_keys = {c[0] for c in PROFIT}

    for key, lbl, w, _ in col_defs:
        lbl_1 = lbl.replace('\n', ' ')
        if key in wgst_keys or key in profit_keys:
            set_fill(146, 208, 80); fill = True
        else:
            set_fill(217, 217, 217); fill = True
        pdf.cell(w, HDR_H, lbl_1, border=1, align='C', fill=fill)
    pdf.ln()
    set_fill(255, 255, 255)

    # ── Data rows ─────────────────────────────────────────────
    ROW_H = 6
    pdf.set_font('Arial', '', 6.5)
    for _, row in df_items.iterrows():
        for key, _, w, aln in col_defs:
            v   = item_val(row, key)
            txt = fmt_val(key, v)
            if key in wgst_keys or key in profit_keys:
                set_fill(230, 255, 210); fill = True
            else:
                fill = False
            pdf.cell(w, ROW_H, txt, border=1, align=aln, fill=fill)
        pdf.ln()
    set_fill(255, 255, 255)

    # ── Summary ───────────────────────────────────────────────
    pdf.ln(2)
    raw_sum  = safe_num(df_items['Total Cost (RAW)'].sum()         if 'Total Cost (RAW)'          in df_items.columns else 0)
    gst_amt  = round(raw_sum * (gst_rate / 100), 2)
    wgst_sum = safe_num(df_items['Total Cost (SGD) (W GST)'].sum() if 'Total Cost (SGD) (W GST)'  in df_items.columns else raw_sum * gst_mult)
    sell_sum = safe_num(df_items['Total Selling'].sum()             if 'Total Selling'              in df_items.columns else 0)
    prof_sum = safe_num(df_items['TOTAL PROFIT ($)'].sum()         if 'TOTAL PROFIT ($)'           in df_items.columns else 0)
    psp      = (prof_sum / sell_sum * 100) if sell_sum > 0 else 0

    pdf.set_font('Arial', 'B', 8)
    cw = PAGE_W / 4

    pdf.cell(cw, 6, f'SUB TOTAL: ${raw_sum:,.2f}',          border=1)
    pdf.cell(cw, 6, f'Total Cost (SGD): ${raw_sum:,.2f}'    if include_wgst else '',   border=1 if include_wgst else 0)
    pdf.cell(cw, 6, f'Total Selling: ${sell_sum:,.2f}'       if include_profit else '', border=1 if include_profit else 0)
    pdf.cell(cw, 6, f'Total Profit: ${prof_sum:,.2f}'        if include_profit else '', border=1 if include_profit else 0, ln=True)
    pdf.cell(cw, 6, 'Freight (CNF): $0.00',                 border=1)
    pdf.cell(cw, 6, f'{gst_label} GST: ${gst_amt:,.2f}'    if include_wgst else '',   border=1 if include_wgst else 0)
    pdf.cell(cw * 2, 6, f'Profit over SP: {psp:.3f}%'       if include_profit else '', border=1 if include_profit else 0, ln=True)
    pdf.cell(cw, 6, f'TOTAL AMT: ${raw_sum:,.2f}',          border=1)
    pdf.cell(cw, 6, f'TOTAL AMT (W/GST): ${wgst_sum:,.2f}' if include_wgst else '',   border=1 if include_wgst else 0)
    pdf.cell(cw * 2, 6, '',                                  border=0, ln=True)

    # ── Signature footer ──────────────────────────────────────
    pdf.ln(3)
    pdf.set_font('Arial', 'B', 7)
    sigs  = ['ORDER BY', 'CHECKED BY', 'SUBMITTED BY', 'ACKNOWLEDGE BY', 'PRICE CHECKED BY']
    sw    = PAGE_W / len(sigs)
    for lbl in sigs:
        pdf.cell(sw, 8, lbl, border=1, align='C')
    pdf.ln()

    return pdf.output(dest='S').encode('latin-1')


# =============================================================
# PURCHASE METRICS
# =============================================================
def calculate_purchase_metrics(product_name, qty_ctn, packing_size, ctn_price):
    qty_ctn, packing_size = float(qty_ctn), float(packing_size)
    ctn_price = float(ctn_price)
    total_qty    = qty_ctn * packing_size
    unit_p_raw   = ctn_price / packing_size if packing_size > 0 else 0
    total_raw    = qty_ctn * ctn_price
    markup       = random.uniform(0.25, 0.30)
    sell_p_pc    = unit_p_raw * (1 + markup)
    total_sell   = sell_p_pc * total_qty
    total_profit = total_sell - total_raw
    return {
        "Product Name":                   product_name,
        "Qty (CTN)":                      qty_ctn,
        "Packing Size (PC)":              packing_size,
        "Total Ordered Qty":              total_qty,
        "Ctn Price (SGD) (W/O GST)":      round(ctn_price, 2),
        "Unit Price (SGD) (W/O GST)":     round(unit_p_raw, 4),
        "Total":                          round(total_raw, 2),
        "Unit Cost (SGD - PC) (W/O GST)": round(unit_p_raw, 4),
        "Total Cost (RAW)":               round(total_raw, 2),
        "Unit Cost (9%) (SGD - PC)":      round(unit_p_raw * 1.09, 4),
        "Unit Cost (9.16%) (SGD - PC)":   0,
        "Ctn Price (9%) (SGD)":           round(ctn_price * 1.09, 2),
        "Total Cost (SGD) (W GST)":       round(total_raw * 1.09, 2),
        "TMG Selling Price per piece":    round(sell_p_pc, 4),
        "TMG Promotion Price":            round(sell_p_pc, 4),
        "Total Selling":                  round(total_sell, 2),
        "UNIT PROFIT ($)":                round(sell_p_pc - unit_p_raw, 4),
        "TOTAL PROFIT ($)":               round(total_profit, 2),
        "Profit Margin - %":              round((total_profit / total_sell) * 100, 2) if total_sell > 0 else 0
    }

def process_order_image(uploaded_file):
    base64_image = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    prompt = "Extract details from this Purchase Order into JSON format. Keys: supplier, purchase_order_date, orders (list of {product_name, quantity, packing_size})."
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
        "filename": uploaded_file.name, "name": f"Order_{datetime.now().strftime('%H%M%S')}",
        "supplier": data.get("supplier"), "purchase_order_date": data.get("purchase_order_date"),
        "orders": data.get("orders", []), "status": "pending", "timestamp": datetime.now().isoformat()
    }

def execute_code(code_str):
    output = io.StringIO()
    sys.stdout = output
    context = {"pd": pd, "np": np, "st": st, "df": st.session_state.df.copy()}
    try:
        exec(code_str, context, context)
        st.session_state.df = context["df"]
        save_master_csv(st.session_state.df)
        return True, output.getvalue(), None
    except Exception as e:
        return False, None, str(e)
    finally:
        sys.stdout = sys.__stdout__

def consolidate_selected_orders(selected_indices, ordering_lists, master_df):
    m_df = master_df.copy()
    m_df['s_name'] = m_df['Product Name'].str.lower().str.strip()
    agg = {}
    for idx in selected_indices:
        for item in ordering_lists[idx]['orders']:
            raw   = str(item['product_name']).strip()
            qty   = float(item.get('quantity', 0) or 0)
            psize = float(item.get('packing_size', 0) or 0)
            match = m_df[m_df['s_name'] == raw.lower()]
            if not match.empty:
                best  = match.sort_values('Ctn Price\n(SGD)\n(W/O GST)').iloc[0]
                dlr   = best['Supplier']
                price = float(best['Ctn Price\n(SGD)\n(W/O GST)'])
                if dlr not in agg: agg[dlr] = {}
                if raw not in agg[dlr]:
                    agg[dlr][raw] = {"q": qty, "pk": psize, "pr": price}
                else:
                    agg[dlr][raw]["q"] += qty
    return agg

# =============================================================
# Session state init
# =============================================================
if 'df'             not in st.session_state: st.session_state.df             = load_master_csv()
if 'chat_history'   not in st.session_state: st.session_state.chat_history   = []
if 'ordering_lists' not in st.session_state: st.session_state.ordering_lists = load_json(ORDER_LISTS_PATH)
if 'purchases'      not in st.session_state: st.session_state.purchases      = load_json(PURCHASES_PATH)
if 'checkpoints'    not in st.session_state: st.session_state.checkpoints    = load_json(CHECKPOINT_PATH)

# =============================================================
# TABS
# =============================================================
tabs = st.tabs(["📋 Master List", "🧠 Agentic Chatbot", "📝 Ordering Lists", "📦 Orders", "🛒 Purchase"])
tab1, tab2, tab3, tab4, tab5 = tabs

# ─────────────────────────────────────────────────────────────
# TAB 1 — MASTER LIST
# ─────────────────────────────────────────────────────────────
with tab1:
    st.header("Master List")
    st.subheader("📤 Upload Supplier Excel Files")
    excel_files = st.file_uploader(
        "Upload one or more supplier Excel PO files",
        type=['xlsx', 'xls'], accept_multiple_files=True, key="master_excel_upload"
    )

    if st.button("Process & Import Excel Files") and excel_files:
        imported_count = 0
        errors = []
        existing_df = st.session_state.df.copy()
        for f in excel_files:
            try:
                new_rows, supplier_name = process_uploaded_excel(f)
                if existing_df.empty:
                    existing_df = new_rows
                else:
                    PROMO_COL = 'TMG\nPromotion\nPrice'

                    def _is_blank(v):
                        """True when a value carries no real information."""
                        if v is None:
                            return True
                        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                            return True
                        if str(v).strip() in ('', 'nan', 'NaN', 'None'):
                            return True
                        return False

                    # Build lookup keys (product|supplier) on existing rows
                    existing_df['_key'] = (
                        existing_df['Product Name'].str.lower().str.strip() + '|' +
                        existing_df['Supplier'].fillna('').str.lower().str.strip()
                    )
                    new_rows['_key'] = (
                        new_rows['Product Name'].str.lower().str.strip() + '|' +
                        new_rows['Supplier'].fillna('').str.lower().str.strip()
                    )

                    for _, nr in new_rows.iterrows():
                        key  = nr['_key']
                        mask = existing_df['_key'] == key

                        if mask.any():
                            # ── Same product + same supplier → smart upsert ──────
                            # Only overwrite a field when the incoming value is real
                            # AND (the existing value is blank  OR  the column is not
                            # the manually-curated promo price that already has data).
                            for col in MASTER_COLUMNS:
                                if col not in nr.index:
                                    continue
                                new_val = nr[col]
                                if _is_blank(new_val):
                                    # Incoming has nothing useful — keep existing
                                    continue
                                if col == PROMO_COL:
                                    # Never overwrite a real promo price the user set
                                    ev = existing_df.loc[mask, col].values[0]
                                    if not _is_blank(ev) and ev != 0:
                                        continue
                                existing_df.loc[mask, col] = new_val
                        else:
                            # ── Different supplier (or brand-new product) → new row
                            existing_df = pd.concat(
                                [existing_df, nr.to_frame().T], ignore_index=True
                            )

                    existing_df.drop(columns=['_key'], inplace=True, errors='ignore')
                    new_rows.drop(columns=['_key'],    inplace=True, errors='ignore')

                imported_count += 1
                st.success(f"✅ Imported **{f.name}** — Supplier: **{supplier_name}** ({len(new_rows)} products)")
            except Exception as e:
                errors.append(f"{f.name}: {e}")

        if errors:
            for err in errors:
                st.error(f"❌ {err}")

        for col in MASTER_COLUMNS:
            if col not in existing_df.columns:
                existing_df[col] = np.nan
        existing_df = existing_df[MASTER_COLUMNS]
        st.session_state.df = existing_df
        save_master_csv(st.session_state.df)
        if imported_count:
            st.rerun()

    st.markdown("---")
    col_hdr, col_btn = st.columns([6, 1])
    col_hdr.subheader("📋 Current Master List")
    if col_btn.button("🔄 Refresh", use_container_width=True, help="Reload master list from disk"):
        st.session_state.df = load_master_csv()
        st.rerun()

    if st.session_state.df.empty:
        st.info("No data yet. Upload supplier Excel files above to populate the master list.")
    else:
        st.dataframe(st.session_state.df, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────
# TAB 2 — AGENTIC CHATBOT
# ─────────────────────────────────────────────────────────────
with tab2:
    for i, msg in enumerate(st.session_state.chat_history):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                st.download_button(label="📥 Download PDF", data=create_pdf(msg["content"]),
                                   file_name=f"res_{i}.pdf", key=f"chat_{i}")

    if prompt := st.chat_input("Ask the Data Agent..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        product_names   = st.session_state.df['Product Name'].dropna().tolist() if 'Product Name' in st.session_state.df.columns else []
        close_matches   = difflib.get_close_matches(prompt, product_names, n=5, cutoff=0.3)
        prompt_words    = [w for w in prompt.lower().split() if len(w) > 3]
        substr_matches  = [p for p in product_names if any(w in p.lower() for w in prompt_words)]
        candidate_names = list(dict.fromkeys(close_matches + substr_matches))[:10]

        fuzzy_hint = (
            f"IMPORTANT: Likely matching products: {candidate_names}. Use str.contains, never bare exact match."
            if candidate_names else
            "IMPORTANT: Use case-insensitive partial string matching (str.contains)."
        )

        pricing_chain_rules = """
PRICING CHAIN RULES (always apply when any price field changes):

Column names in df (exact, with newlines):
  'Ctn Price\\n(SGD)\\n(W/O GST)'            → carton price W/O GST
  'Unit Price\\n(SGD)\\n(W/O GST)'           → Ctn Price / Packing Size
  'Unit Cost \\n(SGD - PC)\\n(W/O GST)'      → same as Unit Price
  'Unit Cost (9%)\\n(SGD - PC)'              → Unit Cost W/O GST * 1.09  (if non-zero for this row)
  'Unit Cost (9.16%)\\n(SGD - PC)'           → Unit Cost W/O GST * 1.0916 (if non-zero for this row)
  'Packing Size\\n(PC)'                       → units per carton
  'TMG Selling Price'                          → selling price per piece
  'TMG\\nPromotion\\nPrice'                  → same as TMG Selling Price unless manually overridden
  'UNIT PROFIT ($)'                            → TMG Selling Price - Unit Cost W/O GST
  'Profit Margin - % '                         → (UNIT PROFIT / TMG Selling Price) * 100

CHAIN 1 — Ctn Price changes:
  unit_price = ctn_price / packing_size
  unit_cost_wogst = unit_price
  if df.loc[mask,'Unit Cost (9%)\\n(SGD - PC)'].values[0] != 0:
      df.loc[mask,'Unit Cost (9%)\\n(SGD - PC)'] = round(unit_cost_wogst*1.09,4)
  elif df.loc[mask,'Unit Cost (9.16%)\\n(SGD - PC)'].values[0] != 0:
      df.loc[mask,'Unit Cost (9.16%)\\n(SGD - PC)'] = round(unit_cost_wogst*1.0916,4)
  unit_profit = tmg_selling_price - unit_cost_wogst
  profit_margin = (unit_profit/tmg_selling_price)*100 if tmg_selling_price>0 else 0

CHAIN 2 — Profit Margin changes:
  tmg_selling_price = unit_cost_wogst / (1 - profit_margin/100)
  tmg_promotion_price = tmg_selling_price
  unit_profit = tmg_selling_price - unit_cost_wogst

CHAIN 3 — TMG Selling Price changes:
  tmg_promotion_price = tmg_selling_price
  unit_profit = tmg_selling_price - unit_cost_wogst
  profit_margin = (unit_profit/tmg_selling_price)*100 if tmg_selling_price>0 else 0

CHAIN 4 — Product Name change: name only, nothing else.

After any update: df.to_csv('assets/data.csv', index=False)
Print a plain-English summary of what changed.
"""

        retries, final_response = 0, None
        with st.chat_message("assistant"):
            with st.spinner("Agent is working..."):
                while retries < 3:
                    history_ctx = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[-5:]])
                    coder_prompt = (
                        f"You are a Python Data Agent managing a master product price list in 'df'.\n"
                        f"COLUMNS: {list(st.session_state.df.columns)}\n"
                        f"HISTORY: {history_ctx}\n"
                        f"USER TASK: {prompt}\n"
                        f"{fuzzy_hint}\n{pricing_chain_rules}\n"
                        f"Rules: use df.loc; follow chain rules; print plain-English summary. Return ONLY ```python blocks."
                    )
                    res = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "system", "content": coder_prompt}],
                        temperature=0
                    )
                    code_match = re.search(r"```python\n(.*?)\n```", res.choices[0].message.content, re.DOTALL)
                    if not code_match: retries += 1; continue
                    code = code_match.group(1)
                    run_ok, out, err = execute_code(code)

                    rev_prompt = (
                        f"User Task: {prompt}\nResult: {out if run_ok else err}\n\n"
                        f"Write 2-3 sentences in plain English. Say what changed in simple terms. "
                        f"No column names, no code. Start with 'SUCCESS:' if ok, 'RETRY: reason' only on crash."
                    )
                    rev_res = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=[{"role": "user", "content": rev_prompt}],
                        temperature=0
                    )
                    decision = rev_res.choices[0].message.content
                    if "RETRY" in decision:
                        retries += 1
                    else:
                        final_response = decision.replace("SUCCESS:", "").strip()
                        break

                if not final_response:
                    final_response = "I wasn't able to find what you were looking for. Could you double-check the product name or rephrase?"

            st.markdown(final_response)
            st.download_button(label="📥 Download PDF", data=create_pdf(final_response),
                               file_name=f"res_{len(st.session_state.chat_history)}.pdf",
                               key=f"chat_new_{len(st.session_state.chat_history)}")
            st.session_state.chat_history.append({"role": "assistant", "content": final_response})

# ─────────────────────────────────────────────────────────────
# TAB 3 — ORDERING LISTS
# ─────────────────────────────────────────────────────────────
with tab3:
    st.header("Ordering Lists")

    st.subheader("📤 Upload PO Images")
    ups = st.file_uploader("Upload PO Images", type=['jpg','png','jpeg'], accept_multiple_files=True)
    if st.button("Process Images") and ups:
        with st.spinner("AI Reading..."):
            for f in ups:
                st.session_state.ordering_lists.append(process_order_image(f))
            save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
            st.rerun()

    st.markdown("---")
    st.subheader("✍️ Create Ordering List Manually")

    all_product_names = (
        sorted(st.session_state.df['Product Name'].dropna().unique().tolist())
        if 'Product Name' in st.session_state.df.columns else []
    )
    manual_list_name  = st.text_input("Ordering List Name", placeholder="e.g. Weekly Order #1", key="manual_list_name")
    selected_products = st.multiselect("Select Products", options=all_product_names, key="manual_products")

    # Show preview with auto-filled packing size
    if selected_products:
        st.markdown("**Selected products — packing size auto-filled from master list:**")
        preview = [{"Product Name": p,
                    "Packing Size (auto)": get_packing_size(p, st.session_state.df)}
                   for p in selected_products]
        st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)

    if st.button("Create Manual Ordering List") and manual_list_name and selected_products:
        manual_orders = [
            {"product_name": p, "quantity": 0,
             "packing_size": get_packing_size(p, st.session_state.df)}
            for p in selected_products
        ]
        st.session_state.ordering_lists.append({
            "filename": "manual", "name": manual_list_name,
            "supplier": "Manual",
            "purchase_order_date": datetime.now().strftime("%Y-%m-%d"),
            "orders": manual_orders, "status": "pending",
            "timestamp": datetime.now().isoformat()
        })
        save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
        st.success(f"Created '{manual_list_name}' with {len(selected_products)} products.")
        st.rerun()

# ─────────────────────────────────────────────────────────────
# TAB 4 — ORDERS
# ─────────────────────────────────────────────────────────────
with tab4:
    st.header("Order Management")
    c1, c2 = st.columns(2)
    start = c1.date_input("Start Date", value=datetime.now())
    end   = c2.date_input("End Date",   value=datetime.now())
    visible  = [(i, o) for i, o in enumerate(st.session_state.ordering_lists)
                if start <= datetime.fromisoformat(o['timestamp']).date() <= end]
    selected = []

    all_product_names_tab4 = (
        sorted(st.session_state.df['Product Name'].dropna().unique().tolist())
        if 'Product Name' in st.session_state.df.columns else []
    )

    for idx, order in visible:
        col_s, col_info, col_v, col_e, col_d = st.columns([0.5, 3, 0.7, 0.7, 0.7])
        comp = order.get("status") == "completed"
        if comp:
            col_s.write("✅")
        elif col_s.checkbox("", key=f"s_{idx}"):
            selected.append(idx)
        col_info.markdown(
            f"**{order['name']}** | {order['supplier']} | "
            f":{'green' if comp else 'orange'}[{order.get('status','pending').upper()}]"
        )

        if col_v.button("View", key=f"v_{idx}"):
            @st.dialog("Order Details")
            def view_dialog(o, i):
                st.write(f"**Name:** {o['name']}")
                st.write(f"**Supplier:** {o['supplier']}")
                st.table(pd.DataFrame(o['orders']))
            view_dialog(order, idx)

        if col_e.button("Edit", key=f"e_{idx}"):
            @st.dialog("Edit Order", width="large")
            def edit_dialog(o, i):
                st.session_state.ordering_lists[i]['name']     = st.text_input("Order Name", o['name'], key=f"edit_name_{i}")
                st.session_state.ordering_lists[i]['supplier'] = st.text_input("Supplier", o.get('supplier',''), key=f"edit_sup_{i}")

                st.markdown("#### Edit Existing Products")
                updated_orders = []

                # Current product names already in the order
                current_product_names = [item.get('product_name', '') for item in o['orders']]

                for j, item in enumerate(list(o['orders'])):
                    st.markdown(f"**Product {j+1}**")
                    ec1, ec2, ec3, ec4 = st.columns([2, 1, 1, 0.5])

                    cur_prod = item.get('product_name', '')

                    # For editing existing items, only allow the same product (name is locked)
                    # but show it as text — user can change qty/packing only
                    ec1.text(f"📦 {cur_prod}")

                    # Auto-fill packing size: prefer saved value, fall back to master
                    auto_pk  = get_packing_size(cur_prod, st.session_state.df)
                    saved_pk = float(item.get('packing_size', 0) or 0)
                    pk_val   = saved_pk if saved_pk != 0 else auto_pk

                    new_qty  = ec2.number_input("Qty (CTN)",    value=float(item.get('quantity',0) or 0), min_value=0.0, key=f"edit_qty_{i}_{j}")
                    new_pk   = ec3.number_input("Packing Size", value=pk_val, min_value=0.0, key=f"edit_pk_{i}_{j}")
                    keep     = ec4.checkbox("Keep", value=True, key=f"edit_keep_{i}_{j}")
                    if keep:
                        updated_orders.append({"product_name": cur_prod, "quantity": new_qty, "packing_size": new_pk})

                st.markdown("---")
                st.markdown("#### ➕ Add New Products")

                # Exclude products already in the order from the available options
                already_in_order = set(item.get('product_name', '') for item in o['orders'])
                available_to_add = [p for p in all_product_names_tab4 if p not in already_in_order]

                if available_to_add:
                    new_products_to_add = st.multiselect(
                        "Select products to add (already-in-order products are excluded)",
                        options=available_to_add,
                        key=f"new_prod_multiselect_{i}"
                    )

                    for new_prod in new_products_to_add:
                        auto_pk_add = get_packing_size(new_prod, st.session_state.df)
                        na1, na2 = st.columns([2, 1])
                        na1.text(f"📦 {new_prod}  (Packing Size: {auto_pk_add})")
                        new_qty_add = na2.number_input(
                            f"Qty (CTN) for {new_prod}",
                            value=0.0, min_value=0.0,
                            key=f"new_qty_add_{i}_{new_prod}"
                        )
                        updated_orders.append({
                            "product_name": new_prod,
                            "quantity": new_qty_add,
                            "packing_size": auto_pk_add
                        })
                else:
                    st.info("All available products are already in this order.")

                if st.button("Save Changes", key=f"save_edit_{i}"):
                    st.session_state.ordering_lists[i]['orders'] = updated_orders
                    save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
                    st.success("Saved!")
                    st.rerun()

            edit_dialog(order, idx)

        if col_d.button("🗑️", key=f"del_{idx}"):
            st.session_state.ordering_lists.pop(idx)
            save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
            st.rerun()

    if st.button("Consolidate & Generate Purchases", type="primary") and selected:
        checkpoint_entry = {
            "timestamp": datetime.now().isoformat(),
            "data": json.loads(json.dumps(st.session_state.purchases, default=str)),
            "order_statuses": [{"index": i, "status": o['status']} for i, o in enumerate(st.session_state.ordering_lists)]
        }
        st.session_state.checkpoints.append(checkpoint_entry)
        save_json(CHECKPOINT_PATH, st.session_state.checkpoints)

        agg = consolidate_selected_orders(selected, st.session_state.ordering_lists, st.session_state.df)
        for idx in selected:
            st.session_state.ordering_lists[idx]['status'] = 'completed'

        new_purchases = []
        for v, p in agg.items():
            po_num = get_next_po_number()
            new_purchases.append({
                "vendor": v, "date": datetime.now().strftime("%d %m %Y"), "po_number": po_num,
                "items": [calculate_purchase_metrics(pn, d['q'], d['pk'], d['pr']) for pn, d in p.items()]
            })

        existing_vendors = {pur['vendor']: pur for pur in st.session_state.purchases}
        for new_pur in new_purchases:
            vendor = new_pur['vendor']
            if vendor in existing_vendors:
                existing_items = {item['Product Name']: item for item in existing_vendors[vendor]['items']}
                for new_item in new_pur['items']:
                    pname = new_item['Product Name']
                    if pname in existing_items:
                        combined_qty = existing_items[pname]['Qty (CTN)'] + new_item['Qty (CTN)']
                        existing_items[pname] = calculate_purchase_metrics(
                            pname, combined_qty, new_item['Packing Size (PC)'],
                            new_item['Ctn Price (SGD) (W/O GST)']
                        )
                    else:
                        existing_items[pname] = new_item
                existing_vendors[vendor]['items'] = list(existing_items.values())
            else:
                existing_vendors[vendor] = new_pur

        st.session_state.purchases = list(existing_vendors.values())
        save_json(PURCHASES_PATH, st.session_state.purchases)
        save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
        st.rerun()

# ─────────────────────────────────────────────────────────────
# TAB 5 — PURCHASE
# ─────────────────────────────────────────────────────────────
with tab5:
    st.header("Financial Purchases")

    if st.session_state.checkpoints:
        with st.expander("🔄 Revert to Checkpoint"):
            ncp = len(st.session_state.checkpoints)
            rev = st.number_input("Checkpoint #", min_value=1, max_value=ncp, value=ncp)
            if st.button("Apply Checkpoint"):
                cp = st.session_state.checkpoints[rev - 1]
                st.session_state.purchases = json.loads(json.dumps(cp["data"]))
                for entry in cp.get("order_statuses", []):
                    if isinstance(entry, dict):
                        ii, ss = entry.get("index"), entry.get("status")
                        if ii is not None and ii < len(st.session_state.ordering_lists):
                            st.session_state.ordering_lists[ii]['status'] = ss
                save_json(PURCHASES_PATH, st.session_state.purchases)
                save_json(ORDER_LISTS_PATH, st.session_state.ordering_lists)
                st.success(f"Reverted to checkpoint #{rev}")
                st.rerun()

    if not st.session_state.purchases:
        st.info("No data.")
    else:
        for pur in st.session_state.purchases:
            po_num = pur.get('po_number', 'N/A')
            with st.expander(f"Supplier: {pur['vendor']} | Date: {pur['date']} | PO#: {po_num}", expanded=True):
                df_p = pd.DataFrame(pur['items'])
                st.dataframe(df_p, hide_index=True)

                # ── Financial summary ─────────────────────────────────
                st.markdown("---")
                sc1, sc2, sc3, sc4 = st.columns(4)
                raw_sum  = df_p["Total Cost (RAW)"].sum() if "Total Cost (RAW)"  in df_p.columns else 0
                sell_sum = df_p["Total Selling"].sum()     if "Total Selling"      in df_p.columns else 0
                prof_sum = df_p["TOTAL PROFIT ($)"].sum()  if "TOTAL PROFIT ($)"  in df_p.columns else 0
                gst_sum  = raw_sum * 0.09
                with sc1:
                    st.write("**Purchase**")
                    st.write(f"SUB TOTAL: ${raw_sum:,.2f}")
                    st.write(f"TOTAL: ${raw_sum:,.2f}")
                with sc2:
                    st.write("**Cost (W/GST)**")
                    st.write(f"Total Cost: ${raw_sum:,.2f}")
                    st.write(f"9% GST: ${gst_sum:,.2f}")
                    st.write(f"**TOTAL AMT: ${(raw_sum + gst_sum):,.2f}**")
                with sc3:
                    st.write("**Sales**")
                    st.write(f"Total Selling: ${sell_sum:,.2f}")
                with sc4:
                    st.write("**Profitability**")
                    st.write(f"Total Profit: ${prof_sum:,.2f}")
                    pm = (prof_sum / (raw_sum + gst_sum)) * 100 if (raw_sum + gst_sum) > 0 else 0
                    st.write(f"Profit over Cost: {pm:.2f}%")

                # ── Download section ──────────────────────────────────
                st.markdown("---")
                st.markdown("#### 📥 Download Options")

                # Custom combination toggles
                st.markdown("**Select columns for Custom download:**")
                dc1, dc2, dc3 = st.columns(3)
                inc_wogst  = dc1.checkbox("Include W/O GST columns",  value=True, key=f"wogst_{po_num}")
                inc_wgst   = dc2.checkbox("Include W/ GST columns",   value=True, key=f"wgst_{po_num}")
                inc_profit = dc3.checkbox("Include Profit columns",   value=True, key=f"profit_{po_num}")

                # ── Excel downloads ───────────────────────────────────
                st.markdown("**📊 Excel:**")
                ex1, ex2, ex3, ex4 = st.columns(4)

                with ex1:
                    st.download_button(
                        "📊 Purchase Order\n(W/O GST)",
                        data=build_tmg_excel(pur['vendor'], pur['date'], po_num, df_p,
                                        include_wogst=True, include_wgst=False, include_profit=False),
                        file_name=f"PO_{po_num}_WOGST.xlsx",
                        key=f"ex_wogst_{po_num}"
                    )
                with ex2:
                    st.download_button(
                        "📊 Purchase Order\n(W/ GST)",
                        data=build_tmg_excel(pur['vendor'], pur['date'], po_num, df_p,
                                        include_wogst=True, include_wgst=True, include_profit=False),
                        file_name=f"PO_{po_num}_WGST.xlsx",
                        key=f"ex_wgst_{po_num}"
                    )
                with ex3:
                    st.download_button(
                        "📊 Profit Details",
                        data=build_tmg_excel(pur['vendor'], pur['date'], po_num, df_p,
                                        include_wogst=True, include_wgst=True, include_profit=True),
                        file_name=f"PO_{po_num}_Full.xlsx",
                        key=f"ex_profit_{po_num}"
                    )
                with ex4:
                    st.download_button(
                        "📊 Custom",
                        data=build_tmg_excel(pur['vendor'], pur['date'], po_num, df_p,
                                        include_wogst=inc_wogst, include_wgst=inc_wgst, include_profit=inc_profit),
                        file_name=f"PO_{po_num}_Custom.xlsx",
                        key=f"ex_custom_{po_num}"
                    )

                # ── PDF downloads ─────────────────────────────────────
                st.markdown("**📄 PDF:**")
                pd1, pd2, pd3, pd4 = st.columns(4)

                with pd1:
                    st.download_button(
                        "📄 Purchase Order\n(W/O GST)",
                        data=build_tmg_pdf(pur['vendor'], pur['date'], po_num, df_p,
                                      include_wogst=True, include_wgst=False, include_profit=False),
                        file_name=f"PO_{po_num}_WOGST.pdf",
                        key=f"pdf_wogst_{po_num}"
                    )
                with pd2:
                    st.download_button(
                        "📄 Purchase Order\n(W/ GST)",
                        data=build_tmg_pdf(pur['vendor'], pur['date'], po_num, df_p,
                                      include_wogst=True, include_wgst=True, include_profit=False),
                        file_name=f"PO_{po_num}_WGST.pdf",
                        key=f"pdf_wgst_{po_num}"
                    )
                with pd3:
                    st.download_button(
                        "📄 Profit Details",
                        data=build_tmg_pdf(pur['vendor'], pur['date'], po_num, df_p,
                                      include_wogst=True, include_wgst=True, include_profit=True),
                        file_name=f"PO_{po_num}_Full.pdf",
                        key=f"pdf_profit_{po_num}"
                    )
                with pd4:
                    st.download_button(
                        "📄 Custom",
                        data=build_tmg_pdf(pur['vendor'], pur['date'], po_num, df_p,
                                      include_wogst=inc_wogst, include_wgst=inc_wgst, include_profit=inc_profit),
                        file_name=f"PO_{po_num}_Custom.pdf",
                        key=f"pdf_custom_{po_num}"
                    )
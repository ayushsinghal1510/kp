from fpdf import FPDF

from .general_ import (
    _get_gst_info , 
    safe_num , 
    safe_str
)

import numpy as np

def create_pdf(text: str) -> bytes:
    
    pdf: FPDF = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.multi_cell(
        0, 10,
        txt=text.encode('latin-1', 'replace').decode('latin-1')
    )
    
    return pdf.output(dest='S').encode('latin-1')

from fpdf import FPDF
import numpy as np
import pandas as pd

def safe_str(val, default=""):
    return str(val) if pd.notna(val) else default

def safe_num(val, default=0.0):
    try:
        return float(val) if pd.notna(val) else default
    except (ValueError, TypeError):
        return default

from fpdf import FPDF
import numpy as np
import pandas as pd

def safe_str(val, default=""):
    return str(val) if pd.notna(val) else default

def safe_num(val, default=0.0):
    try:
        return float(val) if pd.notna(val) else default
    except (ValueError, TypeError):
        return default

def build_tmg_pdf(vendor, date, po_number, df_items, 
                  include_wogst=True, include_wgst=True, include_base=True, include_promo=True):
    
    gst_rate = df_items['GST'].iloc[0] if 'GST' in df_items.columns and not df_items['GST'].empty else 0
    gst_label = f"{int(gst_rate)}%" if gst_rate == int(gst_rate) else f"{gst_rate}%"

    vendor    = safe_str(vendor, 'Unknown')
    po_number = safe_str(po_number, 'N/A')
    date      = safe_str(date, '')

    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_page()
    PAGE_W = 277.0   

    # ── Column blueprint ──────────────────────────────────────
    LEFT = [
        ('no',     'No.',           5,  'C'),
        ('name',   'Product Name',  35, 'L'), 
        ('qty',    'Qty\n(CTN)',    10, 'C'),
        ('pk',     'Pack\nSize',    10, 'C'),
        ('tqty',   'Total\nQty',    10, 'C'),
    ]
    WOGST = [
        ('ctn_p',  'Ctn Price\nW/O GST',  15, 'R'),
        ('unit_p', 'Unit Price\nW/O GST', 15, 'R'),
        ('total',  'Total\nW/O GST',      15, 'R'),
    ]
    WGST = [
        ('ctn_gst', f'Ctn Price\n({gst_label})', 15, 'R'),
        ('uc_gst',  f'Unit Cost\n({gst_label})', 15, 'R'),
        ('tc_gst',  f'Total Cost\n({gst_label})',15, 'R'),
    ]
    BASE_PROF = [
        ('tmg_sell', 'TMG\nSell',       12, 'R'),
        ('tot_sell', 'Total\nSell Base',15, 'R'),
        ('base_p',   'Base\nProfit',    14, 'R'),
        ('base_m',   'Margin\n(%)',      12, 'C'),
    ]
    PROMO_PROF = [
        ('tmg_promo', 'Promo\nPrice',    12, 'R'),
        ('tot_promo', 'Total\nSell Disc',15, 'R'),
        ('promo_p',   'Promo\nProfit',   14, 'R'),
        ('promo_m',   'Margin\n(%)',      12, 'C'),
    ]

    active = list(LEFT)
    if include_wogst: active += WOGST
    if include_wgst:  active += WGST
    if include_base:  active += BASE_PROF
    if include_promo: active += PROMO_PROF

    raw_w = sum(c[2] for c in active)
    scale = PAGE_W / raw_w if raw_w > PAGE_W else 1.0
    if raw_w < PAGE_W: scale = PAGE_W / raw_w 
    col_defs = [(key, lbl, w * scale, aln) for key, lbl, w, aln in active]

    def item_val(row, key):
        MAP = {
            'no':      ('No.', ''),
            'name':    ('Product Name', ''),
            'qty':     ('Qty', 0),
            'pk':      ('Packing Size', 0),
            'tqty':    ('Total Ordered Qty', 0),
            'ctn_p':   ('Ctn Price WOGST', 0),
            'unit_p':  ('Unit Price WOGST', 0),
            'total':   ('Total WOGST', 0),
            'ctn_gst': ('Ctn Price WGST', 0),
            'uc_gst':  ('Unit Cost WGST', 0),
            'tc_gst':  ('Total Cost WGST', 0),
            'tmg_sell':('TMG Selling Price', 0),
            'tot_sell':('Total Selling Base', 0),
            'base_p':  ('Profit', 0),
            'base_m':  ('Profit Margin (Percentage)', 0),
            'tmg_promo':('TMG Promotion Price', 0),
            'tot_promo':('Total Selling Promotion', 0),
            'promo_p': ('Profit after discount', 0),
            'promo_m': ('Profit Margin after discount (Percentage)', 0),
        }
        col_name, default = MAP.get(key, ('', ''))
        v = row.get(col_name, default)
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return default
        return v

    def fmt_val(key, v):
        money4 = {'ctn_p', 'unit_p', 'ctn_gst', 'uc_gst', 'tmg_sell', 'tmg_promo'}
        money2 = {'total', 'tc_gst', 'tot_sell', 'base_p', 'tot_promo', 'promo_p'}
        pct    = {'base_m', 'promo_m'}
        if isinstance(v, (int, float)):
            if key in money4: return f'${v:,.4f}'
            if key in money2: return f'${v:,.2f}'
            if key in pct:    return f'{v:.2f}%'
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
    pdf.cell(PAGE_W - title_w, 5, '', align='R', ln=True) 
    pdf.ln(1)

    pdf.set_font('Arial', 'B', 9)
    hw = PAGE_W
    pdf.cell(hw * 0.50, 5, f'Supplier: {vendor}', border=1)
    pdf.cell(hw * 0.30, 5, f'PO#: {po_number}', border=1, align='C', ln=True)
    pdf.ln(1)

    # ── Section banners ───────────────────────────────────────
    left_w  = sum(c[2] for c in col_defs[:len(LEFT)])
    wogst_w = sum(c[2] for c in col_defs[len(LEFT):len(LEFT) + (len(WOGST) if include_wogst else 0)])
    
    pdf.set_font('Arial', 'B', 7)
    set_fill(255, 255, 255)
    pdf.cell(left_w + wogst_w, 6, 'PURCHASE ORDER', border=1, align='C', fill=True)
    
    wgst_start = len(LEFT) + (len(WOGST) if include_wogst else 0)
    
    for section_flag, section_cols, lbl, color in [
        (include_wgst, WGST, f'Cost ({gst_label} GST)', (146, 208, 80)),
        (include_base, BASE_PROF, 'Base Profit', (180, 220, 255)),
        (include_promo, PROMO_PROF, 'Discount Profit', (255, 200, 150))
    ]:
        if section_flag:
            w = sum(c[2] for c in col_defs[wgst_start : wgst_start+len(section_cols)])
            set_fill(*color)
            pdf.cell(w, 6, lbl, border=1, align='C', fill=True)
            wgst_start += len(section_cols)
            
    pdf.ln()
    set_fill(255, 255, 255)

    # ── Column headers ────────────────────────────────────────
    HDR_H = 8
    pdf.set_font('Arial', 'B', 6)
    
    wgst_keys = {c[0] for c in WGST}
    base_keys = {c[0] for c in BASE_PROF}
    promo_keys = {c[0] for c in PROMO_PROF}

    for key, lbl, w, _ in col_defs:
        lbl_1 = lbl.replace('\n', ' ')
        if key in wgst_keys: set_fill(146, 208, 80)
        elif key in base_keys: set_fill(180, 220, 255)
        elif key in promo_keys: set_fill(255, 200, 150)
        else: set_fill(217, 217, 217)
        pdf.cell(w, HDR_H, lbl_1, border=1, align='C', fill=True)
    pdf.ln()

    # ── Data rows ─────────────────────────────────────────────
    ROW_H = 6
    pdf.set_font('Arial', '', 6)
    for _, row in df_items.iterrows():
        for key, _, w, aln in col_defs:
            v   = item_val(row, key)
            txt = fmt_val(key, v)
            
            if key in wgst_keys: set_fill(230, 255, 210); fill = True
            elif key in base_keys: set_fill(235, 245, 255); fill = True
            elif key in promo_keys: set_fill(255, 240, 230); fill = True
            else: fill = False
            
            pdf.cell(w, ROW_H, txt, border=1, align=aln, fill=fill)
        pdf.ln()

    # ── Summary Block ─────────────────────────────────────────
    raw_sum = safe_num(df_items["Total WOGST"].sum() if "Total WOGST" in df_items.columns else 0)
    wgst_sum = safe_num(df_items["Total Cost WGST"].sum() if "Total Cost WGST" in df_items.columns else 0)
    gst_amt = wgst_sum - raw_sum  

    sell_base_sum = safe_num(df_items["Total Selling Base"].sum() if "Total Selling Base" in df_items.columns else 0)
    sell_promo_sum = safe_num(df_items["Total Selling Promotion"].sum() if "Total Selling Promotion" in df_items.columns else 0)
    
    base_profit_sum = safe_num(df_items["Profit"].sum() if "Profit" in df_items.columns else 0)
    promo_profit_sum = safe_num(df_items["Profit after discount"].sum() if "Profit after discount" in df_items.columns else 0)

    base_margin_overall = (base_profit_sum / sell_base_sum * 100) if sell_base_sum > 0 else (-100.0 if wgst_sum > 0 else 0.0)
    promo_margin_overall = (promo_profit_sum / sell_promo_sum * 100) if sell_promo_sum > 0 else (-100.0 if wgst_sum > 0 else 0.0)

    pdf.ln(2)
    pdf.set_font('Arial', 'B', 7)
    
    cw_count = 1 + (1 if include_wgst else 0) + (1 if include_base else 0) + (1 if include_promo else 0)
    cw = PAGE_W / cw_count
    
    # ROW 1
    set_fill(217, 217, 217)
    pdf.cell(cw, 6, f'SUB TOTAL: ${raw_sum:,.2f}', border=1, align='C', fill=True)
    if include_wgst:
        set_fill(146, 208, 80)
        pdf.cell(cw, 6, f'Total Cost: ${raw_sum:,.2f}', border=1, align='C', fill=True)
    if include_base:
        set_fill(180, 220, 255)
        pdf.cell(cw, 6, f'Total Selling: ${sell_base_sum:,.2f}', border=1, align='C', fill=True)
    if include_promo:
        set_fill(255, 200, 150)
        pdf.cell(cw, 6, f'Promo Selling: ${sell_promo_sum:,.2f}', border=1, align='C', fill=True)
    pdf.ln()

    # ROW 2
    set_fill(217, 217, 217)
    pdf.cell(cw, 6, f'Freight (CNF): $0.00', border=1, align='C', fill=True)
    if include_wgst:
        set_fill(146, 208, 80)
        pdf.cell(cw, 6, f'{gst_label} GST: ${gst_amt:,.2f}', border=1, align='C', fill=True)
    if include_base:
        set_fill(180, 220, 255)
        pdf.cell(cw, 6, f'Total Profit: ${base_profit_sum:,.2f}', border=1, align='C', fill=True)
    if include_promo:
        set_fill(255, 200, 150)
        pdf.cell(cw, 6, f'Promo Profit: ${promo_profit_sum:,.2f}', border=1, align='C', fill=True)
    pdf.ln()

    # ROW 3
    set_fill(217, 217, 217)
    pdf.cell(cw, 6, f'TOTAL AMT (W/O GST): ${raw_sum:,.2f}', border=1, align='C', fill=True)
    if include_wgst:
        set_fill(146, 208, 80)
        pdf.cell(cw, 6, f'TOTAL AMT (W/GST): ${wgst_sum:,.2f}', border=1, align='C', fill=True)
    if include_base:
        set_fill(180, 220, 255)
        pdf.cell(cw, 6, f'Margin: {base_margin_overall:.2f}%', border=1, align='C', fill=True)
    if include_promo:
        set_fill(255, 200, 150)
        pdf.cell(cw, 6, f'Margin: {promo_margin_overall:.2f}%', border=1, align='C', fill=True)
    pdf.ln()

    # ── Signature Footer ──────────────────────────────────────
    pdf.ln(5)
    pdf.set_font('Arial', 'B', 7)
    set_fill(255, 255, 255)
    sigs  = ['ORDER BY', 'CHECKED BY', 'SUBMITTED BY', 'ACKNOWLEDGE BY', 'PRICE CHECKED BY']
    sw    = PAGE_W / len(sigs)
    for lbl in sigs:
        pdf.cell(sw, 8, lbl, border=1, align='C')
    pdf.ln()

    return pdf.output(dest='S').encode('latin-1')
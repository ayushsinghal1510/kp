from io import BytesIO
from pandas import ExcelWriter
import numpy as np


from .services_ import safe_str , safe_num

from io import BytesIO
from pandas import ExcelWriter
import numpy as np

from io import BytesIO
from pandas import ExcelWriter
import numpy as np
import pandas as pd

from io import BytesIO
from pandas import ExcelWriter
import numpy as np
import pandas as pd

def safe_str(val, default=""):
    return str(val) if pd.notna(val) else default

def safe_num(val, default=0.0):
    try:
        return float(val) if pd.notna(val) else default
    except (ValueError, TypeError):
        return default

def build_tmg_excel(vendor, date, po_number, df_items, 
                    include_wogst=True, include_wgst=True, include_base=True, include_promo=True):
    
    gst_rate = df_items['GST'].iloc[0] if 'GST' in df_items.columns and not df_items['GST'].empty else 0
    gst_label = f"{int(gst_rate)}%" if gst_rate == int(gst_rate) else f"{gst_rate}%"

    vendor    = safe_str(vendor, 'Unknown')
    po_number = safe_str(po_number, 'N/A')
    date      = safe_str(date, '')

    output = BytesIO()
    wb = ExcelWriter(output, engine='xlsxwriter', engine_kwargs={'options': {'nan_inf_to_errors': True}}).book
    ws = wb.add_worksheet('Purchase Order')

    # ── Colours ────────────────────────────
    C_WHITE   = '#FFFFFF'
    C_LGREY   = '#D9D9D9'
    C_GREEN1  = '#92D050'   # Cost WGST
    C_BLUE    = '#B4DCFF'   # Base Profit
    C_ORANGE  = '#FFC896'   # Discount Profit
    C_BLACK   = '#000000'

    def F(bold=False, bg=C_WHITE, fc=C_BLACK, border=1, align='center', num_fmt=None, sz=8, wrap=True):
        d = dict(bold=bold, bg_color=bg, font_color=fc, border=border, align=align, valign='vcenter', font_size=sz, text_wrap=wrap)
        if num_fmt: d['num_format'] = num_fmt
        return wb.add_format(d)

    # ── Formats ────────────────────────────
    f_title      = F(bold=True, sz=16, border=0, align='center')
    f_addr       = F(border=0)
    f_date_lbl   = F(bold=True, sz=10, border=0, align='right')
    f_sup_lbl    = F(bold=True, sz=10, align='left')
    f_sup_val    = F(sz=10, align='left')
    
    f_hdr_grey   = F(bold=True, bg=C_LGREY)
    f_hdr_g1     = F(bold=True, bg=C_GREEN1)
    f_hdr_blue   = F(bold=True, bg=C_BLUE)
    f_hdr_org    = F(bold=True, bg=C_ORANGE)

    f_cell       = F()
    f_cell_l     = F(align='left')
    
    def get_fmt(bg_color, num_fmt=None):
        return F(bg=bg_color, num_fmt=num_fmt, align='right' if num_fmt else 'center')

    # ── Column blueprint ──────────────────────────────────────
    LEFT_COLS = [
        ('no',    'No.',                  4,  f_cell,   f_hdr_grey),
        ('name',  'Product Name',         30, f_cell_l, f_hdr_grey),
        ('qty',   'Qty\n(CTN)',           8,  f_cell,   f_hdr_grey),
        ('pk',    'Pack\nSize',           8,  f_cell,   f_hdr_grey),
        ('tqty',  'Total\nQty',           9,  f_cell,   f_hdr_grey),
    ]
    WOGST_COLS = [
        ('ctn_p',  'Ctn Price\n(W/O GST)', 12, get_fmt(C_WHITE, '$#,##0.0000'), f_hdr_grey),
        ('unit_p', 'Unit Price\n(W/O GST)',12, get_fmt(C_WHITE, '$#,##0.0000'), f_hdr_grey),
        ('total',  'Total\n(W/O GST)',     12, get_fmt(C_WHITE, '$#,##0.00'), f_hdr_grey),
    ]
    WGST_COLS = [
        ('ctn_gst', f'Ctn Price\n({gst_label} GST)', 12, get_fmt(C_GREEN1, '$#,##0.0000'), f_hdr_g1),
        ('uc_gst',  f'Unit Cost\n({gst_label} GST)', 12, get_fmt(C_GREEN1, '$#,##0.0000'), f_hdr_g1),
        ('tc_gst',  f'Total Cost\n({gst_label} GST)',12, get_fmt(C_GREEN1, '$#,##0.00'), f_hdr_g1),
    ]
    BASE_COLS = [
        ('tmg_sell', 'TMG\nSell',       11, get_fmt(C_BLUE, '$#,##0.0000'), f_hdr_blue),
        ('tot_sell', 'Total\nSell Base',12, get_fmt(C_BLUE, '$#,##0.00'), f_hdr_blue),
        ('base_p',   'Base\nProfit',    12, get_fmt(C_BLUE, '$#,##0.00'), f_hdr_blue),
        ('base_m',   'Margin\n(%)',     10, get_fmt(C_BLUE, '0.00%'), f_hdr_blue),
    ]
    PROMO_COLS = [
        ('tmg_promo', 'Promo\nPrice',    11, get_fmt(C_ORANGE, '$#,##0.0000'), f_hdr_org),
        ('tot_promo', 'Total\nSell Disc',12, get_fmt(C_ORANGE, '$#,##0.00'), f_hdr_org),
        ('promo_p',   'Promo\nProfit',   12, get_fmt(C_ORANGE, '$#,##0.00'), f_hdr_org),
        ('promo_m',   'Margin\n(%)',     10, get_fmt(C_ORANGE, '0.00%'), f_hdr_org),
    ]

    cols = list(LEFT_COLS)
    if include_wogst: cols += WOGST_COLS
    if include_wgst:  cols += WGST_COLS
    if include_base:  cols += BASE_COLS
    if include_promo: cols += PROMO_COLS
    n_cols = len(cols)
    col_keys = [c[0] for c in cols]

    def cix(k):
        return col_keys.index(k) if k in col_keys else None

    for ci, (_, _, w, _, _) in enumerate(cols):
        ws.set_column(ci, ci, w)
    
    ws.set_row(0, 28)
    ws.set_row(1, 18)
    ws.set_row(2, 18)
    ws.set_row(3, 18)
    ws.set_row(4, 6)
    ws.set_row(5, 18)
    ws.set_row(6, 40)

    # ── Header Block ──────────────────────────────────────────
    title_end = max(n_cols - 4, n_cols // 2)
    ws.merge_range(0, 0, 0, title_end - 1, 'Tian Ma Group Holdings Pte Ltd', f_title)
    ws.merge_range(0, title_end, 0, n_cols - 1, '', f_date_lbl)
    ws.merge_range(1, 0, 1, title_end - 1, '9 Changi South Street 3 #07-02/03 Singapore 486361', f_addr)
    ws.merge_range(1, title_end, 1, n_cols - 1, f'Date:    {date}', f_date_lbl)
    
    ws.write(2, 0, 'Supplier:', f_sup_lbl)
    sup_val_end = min(title_end, n_cols - 1)
    if sup_val_end > 0:
        ws.merge_range(2, 1, 2, sup_val_end, vendor, f_sup_val)
        
    ws.merge_range(3, 0, 3, n_cols - 1, f'PO Number: {po_number}', F(bold=True, sz=10, border=0, align='center'))

    # ── Section banners ───────────────────────────────────────
    l_end = len(LEFT_COLS) + (len(WOGST_COLS) if include_wogst else 0) - 1
    ws.merge_range(5, 0, 5, l_end, 'PURCHASE ORDER', F(bold=True, sz=12, bg=C_WHITE))
    
    curr_col = l_end + 1
    for flag, section, lbl, color in [
        (include_wgst, WGST_COLS, f'Cost ({gst_label} GST)', C_GREEN1),
        (include_base, BASE_COLS, 'Base Profit', C_BLUE),
        (include_promo, PROMO_COLS, 'Discount Profit', C_ORANGE)
    ]:
        if flag:
            ws.merge_range(5, curr_col, 5, curr_col + len(section) - 1, lbl, F(bold=True, sz=11, bg=color))
            curr_col += len(section)

    # ── Column headers & Data ─────────────────────────────────
    for ci, (key, label, _, _, hfmt) in enumerate(cols):
        ws.write(6, ci, label, hfmt)

    DATA_START = 7
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
        
        # Excel requires percentages as fractions (e.g. 50% = 0.5)
        if key in ['base_m', 'promo_m'] and isinstance(v, (int, float)):
            return v / 100.0
            
        return default if isinstance(v, float) and (np.isnan(v) or np.isinf(v)) else v

    for ri, (_, row) in enumerate(df_items.iterrows()):
        r = DATA_START + ri
        ws.set_row(r, 16)
        for ci, (key, _, _, dfmt, _) in enumerate(cols):
            v = item_val(row, key)
            if v == '' or v is None:
                ws.write_blank(r, ci, None, dfmt)
            elif isinstance(v, (int, float)):
                ws.write_number(r, ci, v, dfmt)
            else:
                ws.write(r, ci, v, dfmt)

    # ── Summary Block ─────────────────────────────────────────
    raw_sum = safe_num(df_items["Total WOGST"].sum() if "Total WOGST" in df_items.columns else 0)
    wgst_sum = safe_num(df_items["Total Cost WGST"].sum() if "Total Cost WGST" in df_items.columns else 0)
    gst_amt = wgst_sum - raw_sum  

    sell_base_sum = safe_num(df_items["Total Selling Base"].sum() if "Total Selling Base" in df_items.columns else 0)
    sell_promo_sum = safe_num(df_items["Total Selling Promotion"].sum() if "Total Selling Promotion" in df_items.columns else 0)
    
    base_profit_sum = safe_num(df_items["Profit"].sum() if "Profit" in df_items.columns else 0)
    promo_profit_sum = safe_num(df_items["Profit after discount"].sum() if "Profit after discount" in df_items.columns else 0)

    base_margin_overall = (base_profit_sum / sell_base_sum) if sell_base_sum > 0 else (-1.0 if wgst_sum > 0 else 0.0)
    promo_margin_overall = (promo_profit_sum / sell_promo_sum) if sell_promo_sum > 0 else (-1.0 if wgst_sum > 0 else 0.0)

    s0 = DATA_START + len(df_items) + 1
    ws.set_row(s0, 16); ws.set_row(s0+1, 16); ws.set_row(s0+2, 16)

    # Summary Block (W/O GST)
    tc = cix('total')
    if tc is not None:
        f_lbl_grey = F(bold=True, sz=8, border=1, align='right', bg=C_LGREY)
        f_val_wh2 = F(bold=True, sz=8, border=1, align='right', bg=C_WHITE, num_fmt='$#,##0.00')

        ws.merge_range(s0, 0, s0, tc - 1, 'SUB TOTAL:', f_lbl_grey)
        ws.write_number(s0, tc, raw_sum, f_val_wh2)
        
        ws.merge_range(s0+1, 0, s0+1, tc - 1, 'Freight (CNF):', f_lbl_grey)
        ws.write_number(s0+1, tc, 0.0, f_val_wh2)
        
        ws.merge_range(s0+2, 0, s0+2, tc - 1, 'TOTAL AMT (W/O GST):', f_lbl_grey)
        ws.write_number(s0+2, tc, raw_sum, f_val_wh2)

    # Summary Block (W/ GST)
    tgst_c = cix('tc_gst')
    if tgst_c is not None:
        start_merge = (tc + 1) if tc is not None else 0
        lbl_end = tgst_c - 1
        f_lbl_g1 = F(bold=True, sz=8, border=1, align='right', bg=C_GREEN1)
        f_val_g1_2 = F(bold=True, sz=8, border=1, align='right', bg=C_GREEN1, num_fmt='$#,##0.00')

        if start_merge <= lbl_end:
            ws.merge_range(s0, start_merge, s0, lbl_end, 'Total Cost (SGD):', f_lbl_g1)
            ws.write_number(s0, tgst_c, raw_sum, f_val_g1_2)

            ws.merge_range(s0+1, start_merge, s0+1, lbl_end, f'{gst_label} GST:', f_lbl_g1)
            ws.write_number(s0+1, tgst_c, gst_amt, f_val_g1_2)

            ws.merge_range(s0+2, start_merge, s0+2, lbl_end, 'TOTAL AMT (W/GST):', f_lbl_g1)
            ws.write_number(s0+2, tgst_c, wgst_sum, f_val_g1_2)

    # Summary Block (Base Profit)
    tbase_c = cix('base_p')
    if tbase_c is not None:
        start_merge = (tgst_c + 1) if tgst_c is not None else ((tc + 1) if tc is not None else 0)
        lbl_end = tbase_c - 1
        f_lbl_blue = F(bold=True, sz=8, border=1, align='right', bg=C_BLUE)
        
        if start_merge <= lbl_end:
            ws.merge_range(s0, start_merge, s0, lbl_end, 'Total Selling:', f_lbl_blue)
            ws.write_number(s0, tbase_c, sell_base_sum, F(bold=True, sz=8, border=1, align='right', bg=C_BLUE, num_fmt='$#,##0.00'))

            ws.merge_range(s0+1, start_merge, s0+1, lbl_end, 'Total Profit:', f_lbl_blue)
            ws.write_number(s0+1, tbase_c, base_profit_sum, F(bold=True, sz=8, border=1, align='right', bg=C_BLUE, num_fmt='$#,##0.00'))

            ws.merge_range(s0+2, start_merge, s0+2, lbl_end, 'Profit Margin:', f_lbl_blue)
            margin_col = cix('base_m')
            target_col = margin_col if margin_col is not None else tbase_c
            if margin_col is not None and margin_col != tbase_c:
                ws.write_blank(s0+2, tbase_c, None, f_lbl_blue)
            ws.write_number(s0+2, target_col, base_margin_overall, F(bold=True, sz=8, border=1, align='center', bg=C_BLUE, num_fmt='0.00%'))

    # Summary Block (Promo Profit)
    tpromo_c = cix('promo_p')
    if tpromo_c is not None:
        start_merge = (cix('base_m') if cix('base_m') else tbase_c) + 1 if tbase_c is not None else ((tgst_c + 1) if tgst_c is not None else 0)
        lbl_end = tpromo_c - 1
        f_lbl_org = F(bold=True, sz=8, border=1, align='right', bg=C_ORANGE)
        
        if start_merge <= lbl_end:
            ws.merge_range(s0, start_merge, s0, lbl_end, 'Promo Selling:', f_lbl_org)
            ws.write_number(s0, tpromo_c, sell_promo_sum, F(bold=True, sz=8, border=1, align='right', bg=C_ORANGE, num_fmt='$#,##0.00'))

            ws.merge_range(s0+1, start_merge, s0+1, lbl_end, 'Promo Profit:', f_lbl_org)
            ws.write_number(s0+1, tpromo_c, promo_profit_sum, F(bold=True, sz=8, border=1, align='right', bg=C_ORANGE, num_fmt='$#,##0.00'))

            ws.merge_range(s0+2, start_merge, s0+2, lbl_end, 'Promo Margin:', f_lbl_org)
            margin_col = cix('promo_m')
            target_col = margin_col if margin_col is not None else tpromo_c
            if margin_col is not None and margin_col != tpromo_c:
                ws.write_blank(s0+2, tpromo_c, None, f_lbl_org)
            ws.write_number(s0+2, target_col, promo_margin_overall, F(bold=True, sz=8, border=1, align='center', bg=C_ORANGE, num_fmt='0.00%'))

    # ── Signature footer ──────────────────────────────────────
    f_row = s0 + 4
    ws.set_row(f_row, 20)
    sigs  = ['ORDER BY', 'CHECKED BY', 'SUBMITTED BY', 'ACKNOWLEDGE BY', 'PRICE CHECKED BY']
    chunk = max(1, n_cols // len(sigs))
    f_sig = F(bold=True, sz=8, border=1, align='center')
    
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
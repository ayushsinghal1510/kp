import json
import numpy as np
import pandas as pd
from polars import DataFrame



def detect_gst_column(price_data_columns):
    for variant in GST_COLUMN_VARIANTS:
        if variant in price_data_columns:
            return variant
    return None

def _is_blank(v : str | None | float) -> bool : 

    if v is None : 
        return True

    if isinstance(v , float) and (np.isnan(v) or np.isinf(v)) : 
        return True

    if str(v).strip() in ('' , 'nan' , 'NaN' , 'None') : 
        return True

    return False

def generate_key(row) : 

    prod = str(row.get('Product Name' , 'Unknown')).lower().strip()
    supp = str(row.get('Supplier' , 'Unknown')).lower().strip()

    return f'{prod}|{supp}'

# ── Persistence ───────────────────────────────────────────────


def load_csv(csv_path : str) -> DataFrame : 
    return pd.read_csv(csv_path)

def save_csv(df : DataFrame , csv_path : str) -> None : 
    df.to_csv(csv_path , index = False)

# ── Helper: packing size lookup ───────────────────────────────





# ── Safe value helper (prevents NaN/INF in xlsxwriter) ────────


# =============================================================
# EXCEL EXPORT — Exact Tian Ma Group Holdings PO format
# =============================================================





# =============================================================
# PDF EXPORT — auto-scaled to fit A4 landscape, no overflow
# =============================================================


# =============================================================
# PURCHASE METRICS
# =============================================================


def get_active_gst_details(df):
    """Returns (rate, column_name, label)"""
    if 'Unit Cost (9.16%)\n(SGD - PC)' in df.columns and df['Unit Cost (9.16%)\n(SGD - PC)'].sum() > 0:
        return 9.16, 'Unit Cost (9.16%)\n(SGD - PC)', '9.16%'
    return 9.0, 'Unit Cost (9%)\n(SGD - PC)', '9%'
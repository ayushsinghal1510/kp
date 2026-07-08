import re
import sys
import difflib

import polars as pl
import pandas as pd
import numpy as np
import streamlit as st
from fpdf import FPDF

from io import StringIO


def fuzzy_filter(
    frame : pl.DataFrame ,
    column : str ,
    query : str ,
    cutoff : float = 0.6
) -> pl.DataFrame :
    """Return the rows of `frame` whose `column` fuzzily matches `query`.

    Tolerant of casing, whitespace, extra words between tokens, and small
    misspellings. Every whitespace-separated token in `query` must appear in the
    cell value either as a substring OR as a close (edit-distance) match to one
    of the cell's words. This handles both multi-word product names
    (e.g. 'cadbury chocolate almond' -> 'CADBURY CHOCOLATE 120GM X 24 ... ALMOND')
    and misspelled suppliers (e.g. 'bhavana' -> 'BHAVNA PTE LTD').
    """

    if column not in frame.columns :
        return frame.clear()

    q_tokens : list[str] = [t for t in re.split(r'\s+' , str(query).lower().strip()) if t]

    if not q_tokens :
        return frame

    values : list = frame[column].to_list()

    keep : list[bool] = []

    for value in values :

        text : str = ('' if value is None else str(value)).lower().strip()
        words : list[str] = re.split(r'\s+' , text)

        matched_all : bool = True

        for token in q_tokens :

            if token in text :
                continue

            if difflib.get_close_matches(token , words , n = 1 , cutoff = cutoff) :
                continue

            matched_all = False
            break

        keep.append(matched_all)

    return frame.filter(pl.Series(keep))


def execute_code(code_str : str) -> tuple[bool , str | None , str | None] :

    output : StringIO = StringIO()
    sys.stdout = output

    context = {
        'pl' : pl ,
        'pd' : pd ,
        'np' : np ,
        'st' : st ,
        'df' : st.session_state.df ,
        'fuzzy_filter' : fuzzy_filter
    }

    try : 

        exec(code_str , context , context)

        st.session_state.df = context['df']

        st.session_state.df.write_csv(st.session_state.config['main']['path']['csv'])

        return True , output.getvalue() , None

    except Exception as e : 
        return False , None , str(e)

    finally : 
        sys.stdout = sys.__stdout__

def create_pdf(text: str) -> bytes:
    
    pdf: FPDF = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.multi_cell(
        0, 10,
        txt=text.encode('latin-1', 'replace').decode('latin-1')
    )
    
    return pdf.output(dest='S').encode('latin-1')
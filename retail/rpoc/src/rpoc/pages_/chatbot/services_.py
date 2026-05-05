import sys

import polars as pl
import pandas as pd 
import numpy as np
import streamlit as st 
from fpdf import FPDF

from io import StringIO

def execute_code(code_str : str) -> tuple[bool , str | None , str | None] : 

    output : StringIO = StringIO()
    sys.stdout = output

    context = {
        'pl' : pl , 
        'pd' : pd , 
        'np' : np , 
        'st' : st , 
        'df' : st.session_state.df 
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
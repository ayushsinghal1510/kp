import base64
from io import StringIO
import json
import sys

import pandas as pd

from fpdf import FPDF
from groq import Groq
from datetime import datetime

def load_json(path : str) -> list : 

    with open(path) as json_file : 
        return json.load(json_file)

def save_json(path : str , data : list | dict) -> None : 

    with open(path , 'w') as json_file : 
        json.dump(data , json_file , indent = 4)

def create_pdf(text : str , config : dict) -> FPDF : 

    pdf : FPDF = FPDF()
    pdf.add_page()

    pdf.set_font(config['font'] , size = config['size'])

    pdf.multi_cell(
        0 , 10 , 
        txt = text.encode('latin-1' , 'replace').decode('latin-1')
    )

    return pdf.output(dest = 'S').encode('latin-1')

def process_order_image(
    uploaded_file , 
    prompt : str , 
    groq_client : Groq , 
    config : dict
) -> dict : 

    base64_image : str = base64.b64encode(uploaded_file.getvalue()).decode('utf-8')
    
    completion = groq_client.chat.completions.create(
        model = config['model'] , 
        messages = [
            {
                'role' : 'system' , 
                'content' : prompt
            } , 
            {
                'role' : 'user' , 
                'content' : [
                    {
                        'type' : 'image_url' , 
                        'image_url' : {'url' : f'data:image/jpeg;base64,{base64_image}'}
                    }
                ]
            }
        ] , 
        response_format = config['response-format']
    )

    data = json.loads(completion.choices[0].message.content)

    return {
        'filename' : uploaded_file.name , 
        'name' : f'Order_{datetime.now().strftime('%H%M%S')}' , 
        'supplier' : data.get('supplier') , 
        'purchase_order_date' : data.get('purchase_order_date') , 
        'orders' : data.get('orders' , []) , 
        'status' : 'pending' , 
        'timestamp' : datetime.now().isoformat()
    }

def execute_code(
    code_str : str , 
    st
) -> tuple[bool , str | None , str | None] : 

    output : StringIO = StringIO()

    sys.stdout = output

    context = {
        'pd' : pd , 
        'st' : st , 
        'df' : st.session_state.df.copy()
    }

    try : 

        exec(code_str , context , context)

        st.session_state.df = context['df']

        # st.session_state.df.to_csv(CSV_PATH, index=False)

        return True , output.getvalue() , None

    except Exception as e : 
        return False , None , str(e)

    finally : 
        sys.stdout = sys.__stdout__
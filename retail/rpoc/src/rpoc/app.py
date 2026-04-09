import streamlit as st
import pandas as pd
from groq import Groq
import io
import sys
import re
import os

from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key = os.environ['GROQ_API_KEY'])

st.set_page_config(layout = "wide")

CSV_PATH = 'assets/data.csv'

if 'df' not in st.session_state:
    if os.path.exists(CSV_PATH):
        st.session_state.df = pd.read_csv(CSV_PATH)
    else:
        # Fallback if file is missing
        st.error("CSV not found at assets/data.csv")
        st.stop()

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

def execute_code(code_str):
    output = io.StringIO()
    sys.stdout = output
    # We use a shared dictionary for globals and locals to handle reassignments like 'df = ...'
    context = {
        "pd": pd,
        "st": st,
        "df": st.session_state.df.copy() # Use a copy to work on
    }
    try:
        exec(code_str, context, context)
        # Force the potentially reassigned 'df' back into session state
        st.session_state.df = context["df"]
        result = output.getvalue()
        return True, result, None
    except Exception as e:
        return False, None, str(e)
    finally:
        sys.stdout = sys.__stdout__

# --- UI ---
tab1, tab2 = st.tabs(["📊 Data View", "🧠 Agentic Chatbot"])

with st.sidebar:
    st.header("Settings")
    if st.button("💾 Save Changes to CSV"):
        try:
            # Overwrite the file with current session state
            st.session_state.df.to_csv(CSV_PATH, index=False)
            st.success(f"File saved successfully!")
        except Exception as e:
            st.error(f"Error saving file: {e}")

with tab1:
    st.dataframe(st.session_state.df, use_container_width=True, hide_index=True)

with tab2:
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ex: 'Add a product Mars Bar' or 'Increase margin of X'"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        retries = 0
        success = False
        status = st.status("Agent is working...", expanded=True)
        
        while retries < 3:
            history_context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[-5:]])
            
            coder_prompt = f"""
            You are a Python Data Agent managing 'df'.
            COLUMNS: {list(st.session_state.df.columns)}
            HISTORY: {history_context}
            
            TASK: {prompt}
            
            CRITICAL RULES:
            1. For updates, use df.loc[df['Product Name'] == '...', 'Column'] = value.
            2. If 'Profit Margin' or 'Vendor Price' is updated, you MUST also recalculate and update 'Final Price' in the same code.
            3. For deletions, use df = df[df['Product Name'] != '...'].
            4. For additions, use pd.concat.
            5. Return ONLY ```python blocks.
            """
            
            res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": coder_prompt}],
                temperature=0
            )
            
            code_match = re.search(r"```python\n(.*?)\n```", res.choices[0].message.content, re.DOTALL)
            if not code_match:
                retries += 1
                continue
            
            code = code_match.group(1)
            status.write("Executing logic...")
            
            run_ok, out, err = execute_code(code)
            
            review_prompt = f"""
            User Task: {prompt}
            Code Ran: {code}
            Result: {out if run_ok else err}
            
            Provide a FRIENDLY, NON-TECHNICAL response.
            - NO technical jargon (code, df, etc).
            - If it's an update/add/delete, confirm it's done.
            - If success: "SUCCESS: [Answer]"
            - If failed: "RETRY: [Reason]"
            """
            
            rev_res = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": review_prompt}],
                temperature=0
            )
            
            decision = rev_res.choices[0].message.content
            
            if "RETRY" in decision:
                retries += 1
                status.warning(f"Retrying... {decision}")
            else:
                final_msg = decision.replace("SUCCESS:", "").strip()
                success = True
                break
        
        status.update(label="Complete!", state="complete", expanded=False)
        
        if success:
            with st.chat_message("assistant"):
                st.markdown(final_msg)
            st.session_state.chat_history.append({"role": "assistant", "content": final_msg})
            st.rerun()
        else:
            st.error("Technical difficulties. Try being more specific.")
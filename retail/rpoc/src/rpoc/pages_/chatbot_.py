import re
import difflib
import streamlit as st

from rpoc.services import (
    create_pdf ,  
    execute_code
)

for index , msg in enumerate(st.session_state.history) : 

    with st.chat_message(msg["role"]) : 

        st.markdown(msg["content"])

        if msg["role"] == "assistant" : 

            st.download_button(
                **st.session_state.chatbot_config['message-pdf-download'] , 
                data = create_pdf(msg["content"]) ,  
                file_name = f"res_{index}.pdf" ,  
                key = f"chat_{index}"
            )

if prompt := st.chat_input("Ask the Data Agent...") : 

    st.session_state.history.append(
        {
            "role" : "user" , 
            "content" : prompt
        }
    )

    with st.chat_message("user") : 
        st.markdown(prompt)

    raw_names = st.session_state.df['Product Name'].to_list() if 'Product Name' in st.session_state.df.columns else []
    product_names = [p for p in raw_names if isinstance(p, str)]
    
    close_matches = difflib.get_close_matches(
        prompt , 
        product_names , 
        n = 5 , 
        cutoff = 0.3
    )

    prompt_words = [w for w in prompt.lower().split() if len(w) > 3]
    substr_matches = [p for p in product_names if any(w in p.lower() for w in prompt_words)]
    candidate_names = list(dict.fromkeys(close_matches + substr_matches))[:10]

    fuzzy_hint = (
        f"IMPORTANT: Likely matching products: {candidate_names}. Use pl.col('Product Name').str.contains(...)."
        if candidate_names else "Use case-insensitive partial string matching."
    )

    retries , final_response = 0 , None

    with st.chat_message("assistant") : 

        

        status_placeholder = st.empty()

        with st.spinner("Agent is working...") : 

            final_response = None
            retries = 0

            while retries < 3 : 

                status_placeholder.write(f"Thinking... (Attempt {retries + 1}/3)")

                history_ctx = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.history[-5:]])

                res = st.session_state.groq_client.chat.completions.create(
                    messages = [
                        {
                            "role" : "system" , 
                            "content" : st.session_state.prompts['coder'].format(
                                columns = list(st.session_state.df.columns) , 
                                history = history_ctx , 
                                prompt = prompt ,
                                fuzzy_hint = fuzzy_hint , 
                                chain_rules = st.session_state.prompts['chain-rules']
                            )
                        }
                    ] , 
                    **st.session_state.chatbot_config['coder-model']
                )

                code_match = re.search(
                    r"```python\n(.*?)\n```" , 
                    res.choices[0].message.content , 
                    re.DOTALL
                )

                if not code_match : 
                    retries += 1
                    continue


                code = code_match.group(1)

                # st.code(code)

                run_ok , out , err = execute_code(code) 

                # st.warning(out)
                # st.warning(err)

                if not run_ok:
                    status_placeholder.warning(f"Code Error on attempt {retries+1}. Retrying...")
                
                rev_res = st.session_state.groq_client.chat.completions.create(
                    messages = [
                        {
                            "role" : "user" , 
                            "content" : st.session_state.prompts['review'].format(
                                prompt = prompt , 
                                result = out if run_ok else err
                            )
                        }
                    ] , 
                    **st.session_state.chatbot_config['rev-model']
                )
                
                decision = rev_res.choices[0].message.content

                if "RETRY" in decision : 
                    retries += 1

                else : 

                    final_response = decision.replace("SUCCESS:" , "").strip()

                    break

            status_placeholder.empty()

            if not final_response : 
                final_response = "I couldn't update the data. Please check the product name."

        st.markdown(final_response)

        st.download_button(
            **st.session_state.chatbot_config['message-pdf-download'],
            # label = 'Download PDF' , 
            data=create_pdf(final_response),
            file_name=f"response.pdf",
            key=f'download_{hash(final_response)}'  # Unique key per message
        )

        st.session_state.history.append(
            {
                "role" : "assistant" , 
                "content" : final_response
            }
        )

        # st.rerun()
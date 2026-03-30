import streamlit as st
import requests
import yaml

with open('config.yml') as config_file : 
    config : dict = yaml.safe_load(config_file)

jwe_input = st.text_input('JWE TOKEN')

if st.button("Send to API") : 

    if jwe_input : 

        headers = {"token" : jwe_input.strip()}

        try : 

            with st.spinner("Processing...") : 
                response = requests.post(config['url'] , headers = headers)
            
            if response.status_code == 200 : 
                st.success("Successfully sent!")
                st.json(response.json())

            else : 

                st.error(f"Error: {response.status_code}")
                st.write(response.text)
                
        except Exception as e : 
            st.error(f"Connection failed: {e}")

    else : 
        st.warning("Please enter a token first.")
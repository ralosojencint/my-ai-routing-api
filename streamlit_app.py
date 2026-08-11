import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
# Import the official Google GenAI SDK toolset
from google import genai

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱")

st.title("📱 Mobile AI Multitask Agent")
st.write("Type commands in plain text. Your interface handles the processing automatically!")

user_input = st.text_input("Your Command", placeholder="e.g., read https://example.com or ask a question")
execute_btn = st.button("Execute Action", type="primary")

def core_engine(text_input):
    text_lower = text_input.lower().strip()
    
    # Task 1: Math Automation Engine
    if "calculate" in text_lower or "math" in text_lower:
        numbers = [int(s) for s in text_lower.split() if s.isdigit()]
        if len(numbers) >= 2: return f"💡 AI Math Result:\n{numbers} + {numbers} = {numbers + numbers}"
        return "💡 AI Math Error:\nPlease provide two numbers."
        
    # Task 2: Live Web Scraper Engine
    elif "read" in text_lower or "http" in text_lower:
        words = text_lower.split()
        url = next((w for w in words if w.startswith("http")), None)
        if not url: return "💡 AI Web Error:\nPlease provide a full link starting with http."
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read()
            page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
            return f"💡 AI Web Scraper Result:\n\n\"{page_text[:400]}...\""
        except Exception as e: return f"💡 AI Web Error:\nCould not read link: {str(e)}"
        
    # Task 3: Official Active SDK Connection
    else:
        try:
            # Pull key securely out of Streamlit's secrets manager vault
            api_key_str = st.secrets["GEMINI_KEY"]
            
            # Start official Google Client with your key credentials
            client = genai.Client(api_key=api_key_str)
            
            # FIXED MODEL: Calling the correct current active flagship version
            response = client.models.generate_content(
                model='gemini-2.0-flash',
                contents=text_input,
            )
            return f"🧠 Gemini AI Brain Response:\n\n{response.text}"
        except Exception as e:
            return f"💡 AI Brain Connection Notification:\n\nSystem parsing active. Please wait 10 seconds and tap execute once more! Details: {str(e)}"

if execute_btn and user_input:
    with st.spinner("AI Processing..."):
        result = core_engine(user_input)
        st.text_area("AI System Response", value=result, height=300)

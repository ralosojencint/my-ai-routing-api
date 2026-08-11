import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱")

st.title("📱 Mobile AI Multitask Agent")
st.write("Type commands in plain text. Your interface handles the processing automatically!")

user_input = st.text_input("Your Command", placeholder="e.g., read https://example.com or ask a question")
execute_btn = st.button("Execute Action", type="primary")

def core_engine(text_input):
    text_lower = text_input.lower()
    
    # Task 1: Math Automation Engine
    if "calculate" in text_lower or "math" in text_lower:
        numbers = [int(s) for s in text_lower.split() if s.isdigit()]
        if len(numbers) >= 2: return f"💡 AI Math Result:\n{numbers} + {numbers} = {numbers + numbers}"
        return "💡 AI Math Error:\nPlease provide two numbers."
        
    # Task 2: Live Web Scraper Engine
    elif "read" in text_lower or "http" in text_lower:
        words = text_lower.split()
        url = next((w for w in words if w.startswith("http")), None)
        if not url: return "💡 AI Web Error:\nPlease provide a full link."
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read()
            page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
            return f"💡 AI Web Scraper Result:\n\n\"{page_text[:400]}...\""
        except Exception as e: return f"💡 AI Web Error:\nCould not read link: {str(e)}"
        
    # Task 3: Secure Google Gemini Language Model Connection
    else:
        try:
            # Safely pulls the key from your hidden app settings vault
            gemini_key = st.secrets["GEMINI_KEY"]
            
            url = f"https://googleapis.com{gemini_key}"
            payload = {"contents": [{"parts": [{"text": text_input}]}]}
            data = json.dumps(payload).encode("utf-8")
            
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            response = urllib.request.urlopen(req).read().decode("utf-8")
            res_json = json.loads(response)
            
            ai_text = res_json['candidates']['content']['parts']['text']
            return f"🧠 Gemini AI Brain Response:\n\n{ai_text}"
        except Exception as e:
            return f"💡 AI Brain Configuration Required:\n\nPlease add your key named 'GEMINI_KEY' into the Streamlit Secrets Vault! Details: {str(e)}"

if execute_btn and user_input:
    result = core_engine(user_input)
    st.text_area("AI System Response", value=result, height=250)
    

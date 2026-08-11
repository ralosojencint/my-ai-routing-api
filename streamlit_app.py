import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
# Import the secure login manager library
import streamlit_authenticator as stauth

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱")

# 1. DEFINE YOUR PAYING CUSTOMERS (Username, Name, and Hashed Password)
# For testing, the username is "admin" and the password is "password123"
credentials = {
    "usernames": {
        "admin": {
            "name": "Premium User",
            "password": "b'\\xa4\\xb1\\xaa\\x1e\\xbe\\xc2\\xec\\x0b\\xab\\xdf\\xa4v\\xf0\\xe8\\xee`c\\xbe\\x80A\\x02\\xbe\\xa9\\x9c\\x02\\x16&\\xbd_\\x08\\xc5\\x03'" # Pre-hashed password
        }
    }
}

# 2. Initialize the Login Interface Window
authenticator = stauth.Authenticate(
    credentials,
    "ai_agent_cookie",
    "abcdef",
    cookie_expiry_days=30
)

# Render the Login Input Form on your screen
name, authentication_status, username = authenticator.login("Login to Premium AI Agent", "main")

# 3. IF THE USER IS NOT LOGGED IN, BLOCK THE APPLICATION
if authentication_status == False:
    st.error("Username/password is incorrect")
elif authentication_status == None:
    st.warning("Please enter your premium username and password to unlock the AI tool.")

# 4. IF LOGGED IN, SHOW YOUR APP WORKSPACE HOOD
elif authentication_status:
    # Show a personalized welcome bar and a logout button
    st.write(f"Welcome back, **{name}**!")
    authenticator.logout("Log Out", "sidebar")
    
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
                api_key_str = st.secrets["GEMINI_KEY"]
                client = genai.Client(api_key=api_key_str)
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=text_input,
                )
                return f"🧠 Gemini AI Brain Response:\n\n{response.text}"
            except Exception as e:
                return f"💡 AI Brain Connection Notification:\n\nProcessing error loop. Details: {str(e)}"

    if execute_btn and user_input:
        with st.spinner("AI Processing..."):
            result = core_engine(user_input)
            st.text_area("AI System Response", value=result, height=300)

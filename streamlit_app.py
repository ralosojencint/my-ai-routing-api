import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
import streamlit_authenticator as stauth
from datetime import date

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱")

# 1. DEFINE YOUR TIERS AND USER ACCOUNT CREDENTIALS
# We can mark profiles as "free" or "premium" right in their database dictionary block
config = {
    "credentials": {
        "usernames": {
            "free_user": {
                "name": "Free Tier Account",
                "password": "freeuser123",
                "tier": "free"
            },
            "admin": {
                "name": "Premium User",
                "password": "password123",
                "tier": "premium"
            }
        }
    },
    "cookie": {
        "name": "ai_agent_cookie",
        "key": "abcdefabcdefabcdef",
        "expiry_days": 30
    }
}

# Define your free usage maximum cap parameter
FREE_DAILY_LIMIT = 3

# 2. Initialize the Login Interface Framework
authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"]
)

try:
    authenticator.login()
except Exception:
    pass

# 3. VERIFY LOGIN AT WORKSPACE LAYER
if st.session_state.get("authentication_status") == False:
    st.error("Username/password is incorrect")
elif st.session_state.get("authentication_status") == None:
    st.warning("Please enter your username and password to unlock the AI tool.")

# 4. IF VALIDATED, INITIALIZE TRACKING ENVIRONMENT
elif st.session_state.get("authentication_status"):
    current_user = st.session_state["username"]
    user_tier = config["credentials"]["usernames"][current_user].get("tier", "free")
    
    st.write(f"Logged in as: **{st.session_state['name']}** | Status Tier: `{user_tier.upper()}`")
    authenticator.logout("Log Out", "sidebar")
    
    # Initialize a secure browser session dictionary database tracker to count user clicks
    if "usage_tracker" not in st.session_state:
        st.session_state["usage_tracker"] = {}
        
    if current_user not in st.session_state["usage_tracker"]:
        st.session_state["usage_tracker"][current_user] = 0
        
    user_clicks = st.session_state["usage_tracker"][current_user]
    
    st.title("📱 Mobile AI Multitask Agent")
    st.write("Type commands in plain text. Your interface handles the processing automatically!")

    # 5. LIMIT GATE CONTROLLER ENGINE
    # If the user is on the free plan and has consumed their clicks, enforce the lock
    if user_tier == "free" and user_clicks >= FREE_DAILY_LIMIT:
        st.error(f"🛑 You have reached your Free Tier limit of {FREE_DAILY_LIMIT} requests for today!")
        st.info("💡 **Want unlimited computing access?** Upgrade to our Premium Plan for just $9.99/month to remove all restriction blocks instantly.")
        # Insert your Lemon Squeezy or checkout payment hyperlink text directly below:
        st.markdown("[👉 Click Here to Upgrade to Premium Membership](https://lemonsqueezy.com)")
    else:
        # Otherwise, keep the text field unlocked and open for operations
        if user_tier == "free":
            st.caption(f"📊 Usage Meter: Consumed {user_clicks} of your {FREE_DAILY_LIMIT} free daily requests.")
            
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
                
            # Task 3: Official Active SDK Connection (Gemini 3 Family)
            else:
                try:
                    api_key_str = st.secrets["GEMINI_KEY"]
                    client = genai.Client(api_key=api_key_str)
                    response = client.models.generate_content(
                        model='gemini-3.5-flash',
                        contents=text_input,
                    )
                    return f"🧠 Gemini AI Brain Response:\n\n{response.text}"
                except Exception as e:
                    return f"💡 AI Brain Connection Notification:\n\nProcessing system error. Details: {str(e)}"

        if execute_btn and user_input:
            # Advance the request database value by +1 for the authenticated user session profile
            st.session_state["usage_tracker"][current_user] += 1
            
            with st.spinner("AI Processing..."):
                result = core_engine(user_input)
                st.text_area("AI System Response", value=result, height=300)
                # Instantly force a layout refresh to accurately update the limit meter rendering layout
                st.rerun()

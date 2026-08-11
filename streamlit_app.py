import streamlit as st, urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Configure luxury full-width layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS layout overrides to force a true horizontal mobile pill bar container shape
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 30px !important; margin-bottom: 20px !important;}

/* Elegant custom message speech bubbles formatting */
.chat-bubble { padding: 12px 16px; border-radius: 20px; margin-bottom: 12px; max-width: 85%; font-family: 'Inter', sans-serif; font-size: 15px; line-height: 1.5; }
.user-msg { background-color: #2e3244; color: #f3f4f6; margin-left: auto; border-bottom-right-radius: 4px; }
.ai-msg { background-color: #1e202a; color: #f3f4f6; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #2e3244; }
.msg-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

/* Keeps scrolling space optimized above the sticky bottom capsule dock */
.chat-container { margin-bottom: 110px; display: flex; flex-direction: column; }

/* FORCING NATIVE CONTROLS ONTO 1 SINGLE HORIZONTAL PILL DOCK CAPSULE */
form[data-testid="stForm"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    background-color: #1e202a !important;
    border-radius: 35px !important;
    border: 1px solid #2e3244 !important;
    padding: 6px 12px !important;
    gap: 10px !important;
    width: 100% !important;
    position: fixed !important;
    bottom: 20px !important; /* Locks capsule row flat to the bottom of the screen */
    left: 50% !important;
    transform: translateX(-50%) !important;
    max-width: 90% !important;
    z-index: 99999 !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}

/* Ensuring all internal sub-containers strip margins and sit inline flat */
form[data-testid="stForm"] > div { width: auto !important; padding: 0 !important; margin: 0 !important; display: flex !important; align-items: center !important; }
form[data-testid="stForm"] > div:nth-child(2) { flex-grow: 2 !important; width: 100% !important; }

/* Removing clunky borders around the text bar */
div.stTextInput { width: 100% !important; padding: 0 !important; margin: 0 !important; }
div.stTextInput > div > div > input {
    background-color: transparent !important;
    color: white !important;
    border: none !important;
    padding-left: 5px !important;
    height: 44px !important;
    font-size: 15px !important;
    outline: none !important;
}
div.stTextInput > div > div { border: none !important; background-color: transparent !important; box-shadow: none !important; }

/* Turning the file upload box into a clean grey circular plus icon inside the bar */
div[data-testid="stFileUploader"] { max-width: 38px !important; margin: 0 !important; padding: 0 !important; }
div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
div[data-testid="stFileUploaderDropzone"] button {
    background-color: #2e3244 !important;
    color: #9ca3af !important;
    border-radius: 50% !important;
    height: 36px !important;
    width: 36px !important;
    min-width: 36px !important;
    font-size: 20px !important;
    font-weight: bold !important;
    padding: 0 !important;
    padding-bottom: 2px !important;
    border: none !important;
}
div[data-testid="stFileUploaderDropzone"] span, div[data-testid="stFileUploaderDropzone"] div { display: none !important; }

/* Custom blue circle submit capsule button formatting inside the bar */
form[data-testid="stForm"] button[type="submit"] {
    background-color: #2563eb !important;
    color: white !important;
    border-radius: 50% !important;
    height: 36px !important;
    width: 36px !important;
    min-width: 36px !important;
    border: none !important;
    font-size: 16px !important;
    font-weight: bold !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
}
form[data-testid="stForm"] button[type="submit"]:hover { background-color: #1d4ed8 !important; }
</style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state: st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state: st.session_state["is_premium"] = False
if "chat_history" not in st.session_state: st.session_state["chat_history"] = []

with st.sidebar:
    st.markdown("### 👑 Member Directory")
    if not st.session_state["is_premium"]:
        pass_input = st.text_input("Enter Passcode Key", type="password")
        if pass_input == "premium123": st.session_state["is_premium"] = True; st.rerun()
    else: st.success("👑 Premium Active")
    if st.button("🗑️ Clear Chat History"):
        st.session_state["chat_history"] = []
        st.rerun()

st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= 3:
    st.error("🛑 Limit Reached. Upgrade to Premium for unlimited access.")
else:
    # 🎯 PRINT RUNNING TALK HISTORIES ONTO SCREEN CANVAS
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            st.markdown(f'<div style="text-align: right;"><div class="msg-label">You</div></div><div class="chat-bubble user-msg">{msg["text"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="text-align: left;"><div class="msg-label">Nexus</div></div><div class="chat-bubble ai-msg">{msg["text"]}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================================================
    # 📱 THE NATIVE HORIZONTAL PILL BAR CAPSULE (Plus, Text Bar, Blue Button ALL COMPRESSED INLINE)
    # ========================================================================================
    with st.form(key="nexus_unbreakable_capsule_bar", clear_on_submit=True):
        uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        user_input = st.text_input("", placeholder="Send", label_visibility="collapsed")
        execute_btn = st.form_submit_button(label="↑")

    # ==========================================
    # 🧠 BACKEND MULTI-TURN CHAT CONTEXT ROUTER (Deadlock Removed)
    # ==========================================
    if execute_btn and user_input:
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        
        st.session_state["chat_history"].append({"role": "user", "text": user_input})
        
        client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
        TEXT_MODEL = 'gemini-1.5-flash'
        
        try:
            formatted_contents = []
            for msg in st.session_state["chat_history"]:
                role_str = "user" if msg["role"] == "user" else "model"
                formatted_contents.append(types.Content(role=role_str, parts=[types.Part.from_text(text=msg["text"])]))
            
            response = client.models.generate_content(model=TEXT_MODEL, contents=formatted_contents)
            st.session_state["chat_history"].append({"role": "model", "text": response.text})
        except Exception as e:
            st.session_state["chat_history"].append({"role": "model", "text": f"❌ Error: {str(e)}"})
            
        st.rerun()

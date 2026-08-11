import streamlit as st
import urllib.request, json
from bs4 import BeautifulSoup
from groq import Groq

# Configure luxury centered full-width mobile view
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual luxury executive dark theme configuration
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: sans-serif; text-align: center; margin-top: 20px !important;}

/* Formatting custom speech bubbles so they behave like a real human messenger application */
.chat-bubble { padding: 12px 16px; border-radius: 20px; margin-bottom: 12px; max-width: 85%; font-family: sans-serif; font-size: 15px; line-height: 1.5; color: #f3f4f6; }
.user-msg { background-color: #2e3244; margin-left: auto; border-bottom-right-radius: 4px; }
.ai-msg { background-color: #1e202a; color: #f3f4f6; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #2e3244; }
.msg-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; }
.chat-container { margin-bottom: 120px; display: flex; flex-direction: column; }

/* Formatting the custom Popover to look like an elegant tiny circular grey '+' drawer button */
div[data-testid="stPopover"] > button {
    background-color: #1e202a !important; color: #9ca3af !important; border: 1px solid #2e3244 !important;
    border-radius: 50% !important; height: 38px !important; width: 38px !important; min-width: 38px !important;
    font-size: 20px !important; font-weight: bold !important; display: flex !important; align-items: center !important; justify-content: center !important; padding: 0 !important; padding-bottom: 2px !important;
}

/* Custom styling to turn the sticky search button to a bright blue circle matching your reference layout */
.stChatInput button { background-color: #2563eb !important; color: white !important; border-radius: 50% !important; }
.stChatInput textarea { color: white !important; font-size: 15px !important; }
</style>
""", unsafe_allow_html=True)

# Initialize conversational memory tracking arrays
if "chat_history" not in st.session_state: st.session_state["chat_history"] = []

with st.sidebar:
    st.markdown("### 👑 Operations")
    if st.button("🗑️ Clear Chat Thread Memory"):
        st.session_state["chat_history"] = []
        st.rerun()

st.title("✨ Nexus")

# Stream running conversational timeline directly onto the screen layout canvas
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state["chat_history"]:
    label_str = "You" if msg["role"] == "user" else "Nexus"
    class_str = "user-msg" if msg["role"] == "user" else "ai-msg"
    align_str = "right" if msg["role"] == "user" else "left"
    st.markdown(f'<div style="text-align: {align_str};"><div class="msg-label">{label_str}</div></div><div class="chat-bubble {class_str}">{msg["text"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Clean utility asset drawer popover circle link
with st.popover("+"):
    st.info("📎 Llama 3.3 70B runs on Groq as a pure text-intelligence pipeline.")

# Native chat input locks a horizontal pill shape search bar to the absolute bottom row automatically
user_input = st.chat_input("Send")

# ==========================================
# 🧠 BACKEND GROQ LLAMA 3.3 CONTEXT ROUTER
# ==========================================
if user_input:
    # Append the incoming user prompt query straight to history memory state keys
    st.session_state["chat_history"].append({"role": "user", "text": user_input})
    
    try:
        # Access your background Streamlit Secrets vault for your Groq API Token
        api_key_str = st.secrets["GROQ_API_KEY"]
        client = Groq(api_key=api_key_str)
        
        # Build out structural multi-turn messaging context payloads
        formatted_messages = []
        for msg in st.session_state["chat_history"]:
            formatted_messages.append({"role": msg["role"], "content": msg["text"]})
            
        # Execute absolute low-latency compute call directly through Groq core framework endpoints
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=formatted_messages
        )
        
        ai_response_text = completion.choices[0].message.content
        st.session_state["chat_history"].append({"role": "assistant", "text": ai_response_text})
        
    except Exception as e:
        st.session_state["chat_history"].append({"role": "assistant", "text": f"❌ Groq API Pipeline Error: {str(e)}"})
        
    st.rerun()

import streamlit as st
from google import genai
from google.genai import types

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
    uploaded_image = st.file_uploader("📎 Attach Image Asset to Prompt Track", type=["png", "jpg", "jpeg"])

# Native chat input locks a horizontal pill shape search bar to the absolute bottom row automatically
user_input = st.chat_input("Send")

# ==========================================
# 🧠 BACKEND MULTI-TURN MEMORY ROUTER LOOPS
# ==========================================
if user_input:
    st.session_state["chat_history"].append({"role": "user", "text": user_input})
    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
    
    # 🎯 THE ABSOLUTE DEFINITIVE FIX: Using the Interactions API model path required by Google's modern SDK
    TEXT_MODEL = 'gemini-interactions-flash'
    
    try:
        # Bundle conversational memory turns back to the structural context array
        formatted_contents = []
        for msg in st.session_state["chat_history"]:
            role_str = "user" if msg["role"] == "user" else "model"
            formatted_contents.append(types.Content(role=role_str, parts=[types.Part.from_text(text=msg["text"])]))
        
        # Real Hardware Image Multi-turn Reader Sync Bridge
        if uploaded_image:
            image_bytes = uploaded_image.read()
            response = client.models.generate_content(
                model=TEXT_MODEL, 
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), user_input]
            )
        else:
            response = client.models.generate_content(model=TEXT_MODEL, contents=formatted_contents)
            
        # Save the final text output response right back into history speech bubbles
        st.session_state["chat_history"].append({"role": "model", "text": response.text})
    except Exception as e:
        st.session_state["chat_history"].append({"role": "model", "text": f"❌ Core Link Error: {str(e)}"})
        
    st.rerun()

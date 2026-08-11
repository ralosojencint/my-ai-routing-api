import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: sans-serif; text-align: center; margin-top: 30px !important;}
[data-testid="stHorizontalBlock"] {
    display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important;
    background-color: #1e202a !important; border-radius: 35px !important; border: 1px solid #2e3244 !important; padding: 4px 14px !important; gap: 8px !important; width: 100% !important;
    position: fixed !important; bottom: 20px !important; left: 50% !important; transform: translateX(-50%) !important; max-width: 90% !important; z-index: 99999 !important;
}
[data-testid="stHorizontalBlock"] > div { width: auto !important; padding: 0 !important; margin: 0 !important; }
[data-testid="stHorizontalBlock"] > div:nth-child(2) { flex-grow: 2 !important; width: 100% !important; }
div[data-testid="stFileUploader"] { max-width: 38px !important; }
div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
div[data-testid="stFileUploaderDropzone"] button { background-color: #2e3244 !important; color: #9ca3af !important; border-radius: 50% !important; height: 36px !important; width: 36px !important; min-width: 36px !important; font-size: 20px !important; font-weight: bold; padding: 0; padding-bottom: 2px !important; border: none !important; }
div[data-testid="stFileUploaderDropzone"] span, div[data-testid="stFileUploaderDropzone"] div { display: none !important; }
div.stTextInput > div > div > input { background-color: transparent !important; color: white !important; border: none !important; padding-left: 2px !important; height: 38px !important; font-size: 14px !important; }
div.stTextInput > div > div { border: none !important; background-color: transparent !important; box-shadow: none !important; }
.send-btn-box button { background-color: #2563eb !important; color: white !important; border-radius: 50% !important; height: 36px !important; width: 36px !important; min-width: 36px !important; border: none !important; font-size: 16px !important; font-weight: bold !important; display: flex !important; align-items: center !important; justify-content: center !important; padding: 0 !important; }
.chat-bubble { padding: 12px 16px; border-radius: 20px; margin-bottom: 12px; max-width: 85%; font-family: sans-serif; font-size: 15px; line-height: 1.5; color: #f3f4f6; }
.user-msg { background-color: #2e3244; margin-left: auto; border-bottom-right-radius: 4px; }
.ai-msg { background-color: #1e202a; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #2e3244; }
.msg-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; }
.chat-container { margin-bottom: 110px; display: flex; flex-direction: column; }
</style>
""", unsafe_allow_html=True)

if "chat_history" not in st.session_state: st.session_state["chat_history"] = []

with st.sidebar:
    st.markdown("### 👑 Operations")
    if st.button("🗑️ Clear Conversational Memory"):
        st.session_state["chat_history"] = []
        st.rerun()

st.title("✨ Nexus")

# Render multi-turn speech bubbles to screen canvas
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state["chat_history"]:
    label_str = "You" if msg["role"] == "user" else "Nexus"
    class_str = "user-msg" if msg["role"] == "user" else "ai-msg"
    align_str = "right" if msg["role"] == "user" else "left"
    st.markdown(f'<div style="text-align: {align_str};"><div class="msg-label">{label_str}</div></div><div class="chat-bubble {class_str}">{msg["text"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Unbreakable Single Row Capsule Layout Block
pill_cols = st.columns(3)
with pill_cols[0]:
    uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
with pill_cols[1]:
    user_input = st.text_input("", placeholder="Send", label_visibility="collapsed")
with pill_cols[2]:
    st.markdown('<div class="send-btn-box">', unsafe_allow_html=True)
    execute_btn = st.button("↑")
    st.markdown('</div>', unsafe_allow_html=True)

# Deep Multi-Turn Context Processing
if execute_btn:
    u_valid = 'uploaded_image' in locals() and uploaded_image is not None
    if not user_input and not u_valid:
        st.warning("⚠️ Please enter a text message or attach an image asset.")
    else:
        if user_input:
            st.session_state["chat_history"].append({"role": "user", "text": user_input})
        elif u_valid:
            st.session_state["chat_history"].append({"role": "user", "text": "Describe uploaded photo asset."})
            
        client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
        TEXT_MODEL = 'gemini-1.5-flash'
        
        try:
            formatted_contents = []
            for msg in st.session_state["chat_history"]:
                role_str = "user" if msg["role"] == "user" else "model"
                formatted_contents.append(types.Content(role=role_str, parts=[types.Part.from_text(text=msg["text"])]))
            
            if u_valid:
                image_bytes = uploaded_image.read()
                response = client.models.generate_content(model=TEXT_MODEL, contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), user_input if user_input else "Describe this image asset in deep detail."])
            else:
                response = client.models.generate_content(model=TEXT_MODEL, contents=formatted_contents)
                
            st.session_state["chat_history"].append({"role": "model", "text": response.text})
        except Exception as e:
            st.session_state["chat_history"].append({"role": "model", "text": f"❌ Error: {str(e)}"})
        st.rerun()

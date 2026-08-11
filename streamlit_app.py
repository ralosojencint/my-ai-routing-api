import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: sans-serif; text-align: center; margin-top: 30px !important;}
div[data-testid="stTextInput"], div[data-testid="stCheckbox"], form[data-testid="stForm"] { display: none !important; }

/* Custom Chat Speech Bubbles Layout */
.chat-bubble { padding: 12px 16px; border-radius: 20px; margin-bottom: 12px; max-width: 85%; font-family: sans-serif; font-size: 15px; line-height: 1.5; color: #f3f4f6; }
.user-msg { background-color: #2e3244; margin-left: auto; border-bottom-right-radius: 4px; }
.ai-msg { background-color: #1e202a; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #2e3244; }
.msg-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; }
.chat-container { margin-bottom: 110px; display: flex; flex-direction: column; }
</style>
""", unsafe_allow_html=True)

if "chat_history" not in st.session_state: st.session_state["chat_history"] = []

with st.sidebar:
    st.markdown("### 👑 Memory Controls")
    if st.button("🗑️ Clear Conversational Memory"):
        st.session_state["chat_history"] = []
        st.rerun()

st.title("✨ Nexus")

# 🎯 RENDER CONVERSATION HISTORY TO SCREEN CANVAS
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state["chat_history"]:
    label_str = "You" if msg["role"] == "user" else "Nexus"
    class_str = "user-msg" if msg["role"] == "user" else "ai-msg"
    align_str = "right" if msg["role"] == "user" else "left"
    st.markdown(f'<div style="text-align: {align_str};"><div class="msg-label">{label_str}</div></div><div class="chat-bubble {class_str}">{msg["text"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# 📱 100% UNBREAKABLE NATIVE PILL BAR (Bypasses Frame Sandboxing Issues)
st.html("""
<div style="background-color:#0d0e12; padding:10px; font-family:sans-serif; width:100%; box-sizing:border-box; position:fixed; bottom:20px; left:0; right:0; z-index:999999;">
    <form id="pill_chat_form" style="display:flex; align-items:center; background-color:#1e202a; border-radius:30px; border:1px solid #2e3244; padding:6px 12px; gap:10px; max-width:500px; margin:0 auto; width:90%;">
        <button type="button" onclick="alert('Image handler activated.')" style="background-color:#2e3244; color:#9ca3af; border:none; border-radius:50%; width:36px; height:36px; min-width:36px; font-size:20px; font-weight:bold; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; outline:none;">+</button>
        <input type="text" id="pill_prompt_input" placeholder="Send" style="background-color:transparent; color:white; border:none; width:100%; height:36px; font-size:15px; outline:none; padding:0 4px;">
        <button type="submit" style="background-color:#2563eb; color:white; border:none; border-radius:50%; width:36px; height:36px; min-width:36px; font-size:18px; font-weight:bold; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; outline:none;">↑</button>
    </form>
</div>
<script>
document.getElementById('pill_chat_form').addEventListener('submit', function(e) {
    e.preventDefault();
    var val = document.getElementById('pill_prompt_input').value.trim();
    if(val) {
        window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'native_sync_input', value: val}, '*');
        document.getElementById('pill_prompt_input').value = "";
    }
});
</script>
""")

# Un-sandboxed background listeners
user_input = st.text_input("", key="native_sync_input")

# ==========================================
# 🧠 BACKEND MULTI-TURN CONVERSATION ENGINE
# ==========================================
if user_input:
    # Save current user query into thread array
    st.session_state["chat_history"].append({"role": "user", "text": user_input})
    
    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
    TEXT_MODEL = 'gemini-1.5-flash'
    
    try:
        # Reformat full running conversation context into Google thread objects
        formatted_contents = []
        for msg in st.session_state["chat_history"]:
            role_str = "user" if msg["role"] == "user" else "model"
            formatted_contents.append(types.Content(role=role_str, parts=[types.Part.from_text(text=msg["text"])]))
        
        # Send complete timeline memory context down the pipeline
        response = client.models.generate_content(model=TEXT_MODEL, contents=formatted_contents)
        st.session_state["chat_history"].append({"role": "model", "text": response.text})
    except Exception as e:
        st.session_state["chat_history"].append({"role": "model", "text": f"❌ Error: {str(e)}"})
    
    st.rerun()

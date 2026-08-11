import streamlit as st, urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Configure luxury full-width layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 30px !important; margin-bottom: 20px !important;}
div[data-testid="stTextInput"], div[data-testid="stCheckbox"], form[data-testid="stForm"] { display: none !important; }

/* Elegant custom message speech bubbles formatting */
.chat-bubble { padding: 12px 16px; border-radius: 20px; margin-bottom: 12px; max-width: 85%; font-family: 'Inter', sans-serif; font-size: 15px; line-height: 1.5; }
.user-msg { background-color: #2e3244; color: #f3f4f6; margin-left: auto; border-bottom-right-radius: 4px; }
.ai-msg { background-color: #1e202a; color: #f3f4f6; margin-right: auto; border-bottom-left-radius: 4px; border: 1px solid #2e3244; }
.msg-label { font-size: 11px; color: #9ca3af; margin-bottom: 4px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }

/* Keeps scrolling space optimized above the sticky bottom capsule dock */
.chat-container { margin-bottom: 110px; display: flex; flex-direction: column; }
</style>
""", unsafe_allow_html=True)

# 🧠 INITIALIZE PERSISTENT CHAT HISTORY TRACKERS
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
    # 🎯 PRINT RUNNING TALK History Array
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for msg in st.session_state["chat_history"]:
        if msg["role"] == "user":
            st.markdown(f'<div style="text-align: right;"><div class="msg-label">You</div></div><div class="chat-bubble user-msg">{msg["text"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="text-align: left;"><div class="msg-label">Nexus</div></div><div class="chat-bubble ai-msg">{msg["text"]}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 📱 UNBREAKABLE PIXEL-PERFECT HORIZONTAL CAPSULE BAR
    st.html("""
    <div style="background-color:#0d0e12; padding:10px; font-family:sans-serif; width:100%; box-sizing:border-box; position:fixed; bottom:20px; left:0; right:0; z-index:999999;">
        <form id="pill_chat_form" style="display:flex; align-items:center; background-color:#1e202a; border-radius:30px; border:1px solid #2e3244; padding:6px 12px; gap:10px; max-width:500px; margin:0 auto; width:90%;">
            <button type="button" onclick="alert('Image handler ready.')" style="background-color:#2e3244; color:#9ca3af; border:none; border-radius:50%; width:36px; height:36px; min-width:36px; font-size:20px; font-weight:bold; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; outline:none;">+</button>
            <input type="text" id="pill_prompt_input" placeholder="Send" style="background-color:transparent; color:white; border:none; width:100%; height:36px; font-size:15px; outline:none; padding:0 4px;">
            <button type="submit" style="background-color:#2563eb; color:white; border:none; border-radius:50%; width:36px; height:36px; min-width:36px; font-size:18px; font-weight:bold; cursor:pointer; display:flex; align-items:center; justify-content:center; padding:0; outline:none;">↑</button>
        </form>
    </div>
    <script>
    document.getElementById('pill_chat_form').addEventListener('submit', function(e) {
        e.preventDefault();
        var val = document.getElementById('pill_prompt_input').value.trim();
        if(val) {
            window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'unbreakable_direct_input', value: val}, '*');
            document.getElementById('pill_prompt_input').value = "";
        }
    });
    </script>
    """)
    
    # Secure native background value track synchronization capture field parameters
    user_input = st.text_input("", key="unbreakable_direct_input")

    # ==========================================
    # 🧠 BACKEND MULTI-TURN CHAT CONTEXT ROUTER (Deadlock Cleared)
    # ==========================================
    if user_input:
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        
        # Append input right into memory state history layers
        st.session_state["chat_history"].append({"role": "user", "text": user_input})
        
        client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
        TEXT_MODEL = 'gemini-1.5-flash'
        
        try:
            # Reformat full running thread history context array targets
            formatted_contents = []
            for msg in st.session_state["chat_history"]:
                role_str = "user" if msg["role"] == "user" else "model"
                formatted_contents.append(types.Content(role=role_str, parts=[types.Part.from_text(text=msg["text"])]))
            
            response = client.models.generate_content(model=TEXT_MODEL, contents=formatted_contents)
            st.session_state["chat_history"].append({"role": "model", "text": response.text})
        except Exception as e:
            st.session_state["chat_history"].append({"role": "model", "text": f"❌ Error: {str(e)}"})
            
        # Clear out input cache explicitly using a state rewrite hook to safely stop loop re-runs
        st.empty()
        st.rerun()

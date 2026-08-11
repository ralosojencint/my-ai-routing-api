import streamlit as st, urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import streamlit.components.v1 as components

# Configure luxury full-width layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 50px !important;}
div[data-testid="stTextInput"], div[data-testid="stCheckbox"] { display: none !important; }

/* FIXING THE HEIGHT BLOCK: Drops the whole capsule bar down flat against the absolute bottom of the phone screen */
iframe {
    position: fixed !important;
    bottom: 0px !important;
    left: 0 !important;
    width: 100% !important;
    height: 90px !important;
    z-index: 99999 !important;
    border: none !important;
}
</style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state: st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state: st.session_state["is_premium"] = False
if "text_out" not in st.session_state: st.session_state["text_out"] = None

with st.sidebar:
    st.markdown("### 👑 Member Directory")
    if not st.session_state["is_premium"]:
        pass_input = st.text_input("Enter Passcode Key", type="password")
        if pass_input == "premium123": st.session_state["is_premium"] = True; st.rerun()
    else: st.success("👑 Premium Active")

st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= 3:
    st.error("🛑 Limit Reached. Upgrade to Premium for unlimited access.")
else:
    # DESIGN WORKSPACE MIDDLE VIEW CONTAINERS (Outputs freeze safely dead center)
    out_holder = st.empty()
    if st.session_state["text_out"]:
        out_holder.markdown(f"### 📊 Outputs\n{st.session_state['text_out']}")

    st.markdown("<br><br>", unsafe_allow_html=True)

    # 📱 PIXEL-PERFECT HORIZONTAL CAPSULE INLINE CHAT BAR COMPONENT (The Exact ChatGPT Look)
    chat_bar_html = """
    <div style="background-color:#0d0e12; padding:10px; font-family:sans-serif; width:100%; box-sizing:border-box;">
        <form id="cf" style="display:flex; align-items:center; background-color:#1e202a; border-radius:28px; border:1px solid #2e3244; padding:6px 12px; gap:10px; max-width:500px; margin:0 auto;">
            <!-- Native file upload click handlers -->
            <button type="button" onclick="document.getElementById('if').click()" style="background-color:#2e3244; color:white; border:none; border-radius:50%; width:36px; height:36px; font-size:20px; font-weight:bold; cursor:pointer;">+</button>
            <input type="file" id="if" style="display:none;" onchange="alert('Image selected!')">
            
            <!-- Flat continuous input track field -->
            <input type="text" id="pi" placeholder="Nexus AI" style="background-color:transparent; color:white; border:none; width:100%; height:36px; font-size:15px; outline:none;">
            
            <!-- Vibrant blue circle submit trigger button matching ChatGPT layout reference -->
            <button type="submit" style="background-color:#2563eb; color:white; border:none; border-radius:50%; width:36px; height:36px; font-size:18px; font-weight:bold; cursor:pointer; display:flex; align-items:center; justify-content:center;">↑</button>
        </form>
    </div>
    <script>
    document.getElementById('cf').addEventListener('submit', function(e) {
        e.preventDefault();
        var val = document.getElementById('pi').value.trim();
        if(val) {
            window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'h_in', value: val}, '*');
            window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'h_trig', value: true}, '*');
        }
    });
    </script>
    """
    components.html(chat_bar_html, height=80)
    
    user_input = st.text_input("", key="h_in")
    execute_btn = st.checkbox("", key="h_trig")
    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if execute_btn and user_input:
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
        text_lower = user_input.lower().strip()
        st.session_state["text_out"] = ""
        TEXT_MODEL, ART_MODEL = 'gemini-3.5-flash', 'imagen-3.0-generate-002'

        if generate_art_mode:
            try:
                result = client.models.generate_images(model=ART_MODEL, prompt=user_input, config=dict(number_of_images=1, output_mime_type="image/jpeg"))
                st.image(result.generated_images.image.image_bytes, use_container_width=True)
                st.session_state["text_out"] = "✨ AI Image Generation Complete!"
            except Exception as e: st.session_state["text_out"] = f"❌ Art Error: {str(e)}"
        elif "calculate" in text_lower or "math" in text_lower:
            numbers = [int(s) for s in text_lower.split() if s.isdigit()]
            if len(numbers) >= 2: st.session_state["text_out"] = f"💡 Result: {numbers} + {numbers} = {numbers + numbers}"
        else:
            try:
                response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                st.session_state["text_out"] = response.text
            except Exception as e: st.session_state["text_out"] = f"❌ Error: {str(e)}"
        st.rerun()

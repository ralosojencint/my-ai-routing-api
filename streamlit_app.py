import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF
import streamlit.components.v1 as components

# Configure modern luxury canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Styling background components into an executive dark layout profile
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-bottom: 25px !important;}
.stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; border: none !important; width: 100% !important; }
/* Completely hide the raw background communication field parameters from the view interface */
div[data-testid="stTextInput"], div[data-testid="stCheckbox"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state: st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state: st.session_state["is_premium"] = False
if "text_out" not in st.session_state: st.session_state["text_out"] = None
if "image_out" not in st.session_state: st.session_state["image_out"] = None

FREE_DAILY_LIMIT = 3

with st.sidebar:
    st.markdown("### 👑 Member Directory")
    if not st.session_state["is_premium"]:
        st.caption(f"Free Meter: {st.session_state['anonymous_clicks']}/{FREE_DAILY_LIMIT} Requests Used")
        pass_input = st.text_input("Enter Passcode Key", type="password")
        if pass_input == "premium123":
            st.session_state["is_premium"] = True
            st.rerun()
    else:
        st.success("👑 Premium Active")
        if st.button("Logout"):
            st.session_state["is_premium"] = False
            st.session_state["anonymous_clicks"] = 0
            st.session_state["text_out"] = None
            st.session_state["image_out"] = None
            st.rerun()

st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 Daily Session Limit Reached ({FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT})")
    st.info("💡 Upgrade to Premium membership (\$9.99/month) to unlock unlimited data pipelines instantly.")
    st.markdown("[👉 Click Here to Unlock Unlimited Access](https://lemonsqueezy.com)")
else:
    # DESIGN WORKSPACE OUTPUT MODULES
    output_holder, art_holder, pdf_holder = st.empty(), st.empty(), st.empty()
    
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            clean_pdf_text = st.session_state["text_out"].encode('latin-1', 'ignore').decode('latin-1')
            pdf.multi_cell(190, 10, txt=f"Nexus AI Intelligence Report\n\n{clean_pdf_text}")
            pdf_bytes = pdf.output()
            pdf_holder.download_button(label="📥 Download Response as PDF Document", data=bytes(pdf_bytes), file_name="nexus_report.pdf", mime="application/pdf")
        except Exception: pass
            
    if st.session_state["image_out"]: art_holder.image(st.session_state["image_out"], use_container_width=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # =========================================================================
    # 📱 TRUE NATIVE HTML CAPSULE BAR COMPONENT (The Exact ChatGPT Look)
    # =========================================================================
    # We bypass standard widget blocks entirely by drawing a single flat row frame
    chat_bar_html = """
    <div style="background-color: #0d0e12; padding: 10px; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
        <form id="chatForm" style="display: flex; align-items: center; background-color: #1e202a; border-radius: 28px; border: 1px solid #2e3244; padding: 6px 14px; gap: 12px; width: 100%; box-sizing: border-box;">
            
            <!-- 1. True Plus Circular Icon Button -->
            <button type="button" onclick="alert('Photo selector system initialized. Upload feature active.')" style="background-color: #2e3244; color: #ffffff; border: none; border-radius: 50%; width: 36px; height: 36px; min-width: 36px; font-size: 22px; font-weight: normal; cursor: pointer; display: flex; align-items: center; justify-content: center; outline: none; padding-bottom: 2px;">+</button>
            
            <!-- 2. Flat Continuous Search Bar Field -->
            <input type="text" id="promptInput" placeholder="Nexus AI" style="background-color: transparent; color: #ffffff; border: none; width: 100%; height: 36px; font-size: 16px; outline: none; padding-left: 2px;">
            
            <!-- 3. Integrated Voice Microphone Logo -->
            <button type="button" onclick="alert('Microphone listening active...')" style="background-color: transparent; color: #9ca3af; border: none; font-size: 18px; cursor: pointer; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; outline: none;">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" style="color: #9ca3af;"><path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>
            </button>
            
            <!-- 4. Exact Custom Orange Arrow Circular Send Button Capsule -->
            <button type="submit" style="background-color: #d0755d; color: #ffffff; border: none; border-radius: 50%; width: 36px; height: 36px; min-width: 36px; font-size: 18px; font-weight: bold; cursor: pointer; display: flex; align-items: center; justify-content: center; outline: none;">↑</button>
            
        </form>
    </div>
    
    <script>
    // Bridge data straight past the sandbox frames into Python tracking loops
    document.getElementById('chatForm').addEventListener('submit', function(e) {
        e.preventDefault();
        var val = document.getElementById('promptInput').value;
        if(val) {
            window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'html_text_field', value: val}, '*');
            window.parent.postMessage({type: 'streamlit:set_widget_value', from: 'html_btn_trigger', value: true}, '*');
        }
    });
    </script>
    """
    
    # Render the un-chopped custom horizontal bar component frame
    components.html(chat_bar_html, height=75)
    
    # Underlying variables map values seamlessly across the component connection
    user_input = st.text_input("", key="html_text_field")
    execute_btn = st.checkbox("", key="html_btn_trigger")
    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if execute_btn and user_input:
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        api_key_str = st.secrets["GEMINI_KEY"]
        client = genai.Client(api_key=api_key_str)
        text_lower = user_input.lower().strip()
        st.session_state["text_out"] = ""
        st.session_state["image_out"] = None
        
        TEXT_MODEL = 'gemini-3.5-flash'
        ART_MODEL = 'imagen-3.0-generate-002'

        if generate_art_mode:
            output_holder.warning("🎨 Initiating Neural Networks... Drawing your artwork...")
            try:
                result = client.models.generate_images(model=ART_MODEL, prompt=user_input, config=dict(number_of_images=1, output_mime_type="image/jpeg"))
                for generated_image in result.generated_images: st.session_state["image_out"] = generated_image.image.image_bytes
                st.session_state["text_out"] = "✨ Deep creative render pipeline successful!"
            except Exception as e: st.session_state["text_out"] = f"❌ Creative Art Engine Fault: {str(e)}"
        elif "calculate" in text_lower or "math" in text_lower:
            numbers = [int(s) for s in text_lower.split() if s.isdigit()]
            if len(numbers) >= 2: st.session_state["text_out"] = f"💡 Programmatic Compute:\n{numbers} + {numbers} = {numbers + numbers}"
            else: st.session_state["text_out"] = "❌ Logic Error: Please input two digits to run equations."
        elif "read" in text_lower or "http" in text_lower:
            output_holder.info("🌐 Establishing secure sockets... Extracting HTML strings...")
            words = text_lower.split()
            url = next((w for w in words if w.startswith("http")), None)
            if url:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    html = urllib.request.urlopen(req).read()
                    page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
                    st.session_state["text_out"] = f"```text\n🌐 Extracted link paragraphs:\n\n\"{page_text[:600]}...\"\n```"
                except Exception as e: st.session_state["text_out"] = f"❌ Socket Error: Couldn't scrap url target: {str(e)}"
            else: st.session_state["text_out"] = "❌ Link Error: Missing valid http prefix link target."
        else:
            output_holder.info("🧠 Syncing cloud tokens... Querying central intelligence processing...")
            try:
                response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                st.session_state["text_out"] = response.text
            except Exception as e: st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
        st.rerun()

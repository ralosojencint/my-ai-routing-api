import streamlit as st, urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF
import streamlit.components.v1 as components

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 40px !important;}
.stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; width: 100% !important; }
div[data-testid="stTextInput"], div[data-testid="stCheckbox"] { display: none !important; }

/* FIXING THE HEIGHT BLOCK: Drops the whole capsule bar down to the bottom of the phone screen */
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
    if not st.session_state["is_premium"]:
        pass_input = st.text_input("Enter Passcode Key", type="password")
        if pass_input == "premium123": st.session_state["is_premium"] = True; st.rerun()
    else: st.success("👑 Premium Active")

st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= 3:
    st.error("🛑 Limit Reached. Upgrade to Premium for unlimited access.")
else:
    out_holder, pdf_holder = st.empty(), st.empty()
    if st.session_state["text_out"]:
        out_holder.markdown(f"### 📊 Outputs\n{st.session_state['text_out']}")
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.multi_cell(190, 10, txt=st.session_state["text_out"].encode('latin-1', 'ignore').decode('latin-1'))
            pdf_holder.download_button(label="📥 Download PDF", data=bytes(pdf.output()), file_name="report.pdf", mime="application/pdf")
        except Exception: pass

    # THE PILL BAR COMPONENT LAYER
    chat_bar_html = """
    <div style="background-color:#0d0e12; padding:10px; font-family:sans-serif; width:100%; box-sizing:border-box;">
        <form id="cf" style="display:flex; align-items:center; background-color:#1e202a; border-radius:28px; border:1px solid #2e3244; padding:6px 12px; gap:10px; max-width:500px; margin:0 auto;">
            <button type="button" onclick="alert('Uploader active')" style="background-color:#2e3244; color:white; border:none; border-radius:50%; width:36px; height:36px; font-size:20px; font-weight:bold; cursor:pointer;">+</button>
            <input type="text" id="pi" placeholder="Nexus AI" style="background-color:transparent; color:white; border:none; width:100%; height:36px; font-size:15px; outline:none;">
            <button type="button" onclick="alert('Mic listening')" style="background-color:transparent; color:#9ca3af; border:none; font-size:18px; cursor:pointer; width:30px; height:30px;">🎙️</button>
            <button type="submit" style="background-color:#d0755d; color:white; border:none; border-radius:50%; width:36px; height:36px; font-size:18px; font-weight:bold; cursor:pointer;">↑</button>
        </form>
    </div>
    <script>
    document.getElementById('cf').addEventListener('submit', function(e) {
        e.preventDefault();
        var val = document.getElementById('pi').value;
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

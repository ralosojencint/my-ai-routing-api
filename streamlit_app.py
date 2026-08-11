import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
# Import the lightweight mobile-friendly PDF printing machine library
from fpdf import FPDF

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to force an absolute compact ChatGPT/Claude mobile pill bar
st.markdown("""
    <style>
    .stApp { background-color: #0d0e12; }
    h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-bottom: 2px !important;}
    
    /* Strict Horizontal Flex bar to snap all components side-by-side */
    .unified-pill-bar {
        display: flex !important;
        align-items: center !important;
        background-color: #1e202a !important;
        border-radius: 30px !important;
        border: 1px solid #2e3244 !important;
        padding: 4px 10px !important;
        gap: 8px !important;
        width: 100% !important;
    }
    
    /* Stripping away standard input spacing boxes */
    div.stTextInput { width: 100% !important; padding: 0 !important; margin: 0 !important; }
    div.stTextInput > div > div > input {
        background-color: transparent !important;
        color: #ffffff !important;
        border: none !important;
        padding-left: 6px !important;
        height: 40px !important;
        font-size: 14px !important;
    }
    div.stTextInput > div > div { border: none !important; background-color: transparent !important; }
    
    /* Transforming the upload file block into a neat circle plus button */
    div[data-testid="stFileUploader"] { max-width: 40px !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
    div[data-testid="stFileUploaderDropzone"] button { background-color: #2e3244 !important; color: white !important; border-radius: 50% !important; height: 38px !important; width: 38px !important; min-width: 38px !important; font-size: 18px !important; font-weight: bold !important; padding: 0 !important; border: none !important; }
    div[data-testid="stFileUploaderDropzone"] span { display: none !important; }
    
    /* Scaling down the voice recording mic widget to sit inside our inline row */
    div[data-testid="stAudioInput"] { max-width: 40px !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stAudioInput"] button { background-color: #2e3244 !important; border-radius: 50% !important; height: 38px !important; width: 38px !important; border: none !important; }
    
    /* The custom orange send button arrow capsule configuration */
    .send-btn-box button {
        background-color: #d0755d !important;
        color: white !important;
        border-radius: 50% !important;
        height: 38px !important;
        width: 38px !important;
        min-width: 38px !important;
        border: none !important;
        font-size: 16px !important;
        font-weight: bold !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
    }
    .send-btn-box button:hover { background-color: #be654e !important; }
    
    /* Styling the PDF premium action link download button card layout */
    .stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; border: none !important; margin-top: 15px !important; }
    .stDownloadButton>button:hover { background-color: #059669 !important; }
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
    # =============================================================
    # 🎯 THE MIDDLE OUTPUT LAYER (Brought directly to center view)
    # =============================================================
    output_holder = st.empty()
    art_holder = st.empty()
    pdf_holder = st.empty()
    
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
        
        # --- AUTOMATED PDF CONVERTER LOGIC ENGINE ---
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            # Encode response text to match clean standard PDF page dimensions safely
            clean_pdf_text = st.session_state["text_out"].encode('latin-1', 'ignore').decode('latin-1')
            pdf.multi_cell(190, 10, txt=f"Nexus AI Intelligence Report\n\n{clean_pdf_text}")
            pdf_bytes = pdf.output()
            
            # Render a beautiful download button directly in the center output area
            pdf_holder.download_button(
                label="📥 Download This Response as PDF Document",
                data=bytes(pdf_bytes),
                file_name="nexus_ai_report.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            pass
            
    if st.session_state["image_out"]:
        art_holder.image(st.session_state["image_out"], use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # =============================================================
    # 📱 THE COMPACT HORIZONTAL INTEGRATED PILL BAR CONTAINER
    # =============================================================
    # Stacking components inline within a matrix block layout row to collapse all features horizontally
    bar_cols = st.columns([1, 6, 1, 1], gap="small")
    
    with bar_cols[0]:
        uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        
    with bar_cols[1]:
        # BRAND NAME CHANGE: Search text header removed, inner placeholder changed to "Nexus AI"
        user_input = st.text_input("", placeholder="Nexus AI", label_visibility="collapsed")
        
    with bar_cols[2]:
        audio_file = st.audio_input("", label_visibility="collapsed")
        
    with bar_cols[3]:
        st.markdown('<div class="send-btn-box">', unsafe_allow_html=True)
        execute_btn = st.button("↑")
        st.markdown('</div>', unsafe_allow_html=True)

    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")
    if audio_file and not user_input: user_input = "Transcribe and evaluate this voice message request completely."

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if execute_btn:
        if not user_input and not uploaded_image and not audio_file:
            st.warning("⚠️ Please provide an instruction text string, voice audio, or photo asset link to execute.")
        else:
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

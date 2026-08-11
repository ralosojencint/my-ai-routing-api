import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF

# Configure clean layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to upgrade the interface UI and inject icons inside the bar
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 50px !important; margin-bottom: 25px !important;}
.stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; border: none !important; width: 100% !important; }
.stDownloadButton>button:hover { background-color: #059669 !important; }

/* HARD-FORCING NATIVE CONTROLS ONTO 1 SINGLE HORIZONTAL CHAT PILL LINE */
.stChatInput {
    background-color: #1e202a !important;
    border-radius: 30px !important;
    border: 1px solid #2e3244 !important;
    padding: 2px 4px 2px 45px !important; /* Left padding creates space for the plus button */
    position: relative !important;
}
.stChatInput div { background-color: transparent !important; border: none !important; }
.stChatInput textarea { color: white !important; font-size: 15px !important; padding-right: 40px !important; }

/* Styling the orange up-arrow submit trigger capsule */
.stChatInput button {
    background-color: #d0755d !important;
    color: white !important;
    border-radius: 50% !important;
}
.stChatInput button:hover { background-color: #be654e !important; }

/* Injecting the clean custom HTML Plus Upload Button directly into the search bar track */
.plus-uploader-box {
    position: absolute !important;
    left: 12px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    z-index: 9999 !important;
}
div[data-testid="stFileUploader"] { max-width: 36px !important; margin: 0 !important; padding: 0 !important; }
div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
div[data-testid="stFileUploaderDropzone"] button { 
    background-color: #2e3244 !important; 
    color: white !important; 
    border-radius: 50% !important; 
    height: 32px !important; 
    width: 32px !important; 
    min-width: 32px !important; 
    font-size: 18px !important; 
    font-weight: bold !important;
    padding: 0 !important;
    border: none !important;
}
div[data-testid="stFileUploaderDropzone"] span { display: none !important; }

/* Injecting the clean custom Voice mic overlay inside the far right track */
.mic-wrapper-box {
    position: absolute !important;
    right: 55px !important;
    top: 50% !important;
    transform: translateY(-50%) !important;
    z-index: 9999 !important;
}
div[data-testid="stAudioInput"] { max-width: 36px !important; margin: 0 !important; padding: 0 !important; }
div[data-testid="stAudioInput"] button { background-color: transparent !important; border: none !important; color: #9ca3af !important; height: 32px !important; width: 32px !important; }
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
    # TARGET VIEW MIDDLE ROW CONTAINERS
    output_holder = st.empty()
    art_holder = st.empty()
    pdf_holder = st.empty()
    
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

    # =========================================================================
    # 📱 THE HIGH-END INTEGRATED MOBILE BAR (Icons Positioned Safely Inside)
    # =========================================================================
    # 1. Overlaying the Plus Circle Icon at the far left edge of the search bar
    st.markdown('<div class="plus-uploader-box">', unsafe_allow_html=True)
    uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)
    
    # 2. Overlaying the Microphone Recording module right next to the send button arrow
    st.markdown('<div class="mic-wrapper-box">', unsafe_allow_html=True)
    audio_file = st.audio_input("", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    # 3. The primary unbreakable text capsule track
    user_input = st.chat_input("Nexus AI")
    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")
    
    if audio_file and not user_input:
        user_input = "Transcribe and analyze this voice note statement completely."

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if user_input:
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        api_key_str = st.secrets["GEMINI_KEY"]
        client = genai.Client(api_key=api_key_str)
        text_lower = user_input.lower().strip()
        st.session_state["text_out"] = ""
        st.session_state["image_out"] = None
        
        # FIXING THE MODEL: Swapping to Google's universally supported production path
        TEXT_MODEL = 'gemini-2.0-flash'
        ART_MODEL = 'imagen-3.0-generate-002'

        if generate_art_mode:
            try:
                result = client.models.generate_images(model=ART_MODEL, prompt=user_input, config=dict(number_of_images=1, output_mime_type="image/jpeg"))
                for g_img in result.generated_images: st.session_state["image_out"] = g_img.image.image_bytes
                st.session_state["text_out"] = "✨ Deep creative render pipeline successful!"
            except Exception as e: st.session_state["text_out"] = f"❌ Creative Art Engine Fault: {str(e)}"
        elif "calculate" in text_lower or "math" in text_lower:
            numbers = [int(s) for s in text_lower.split() if s.isdigit()]
            if len(numbers) >= 2: st.session_state["text_out"] = f"💡 Programmatic Compute:\n{numbers} + {numbers} = {numbers + numbers}"
            else: st.session_state["text_out"] = "❌ Logic Error: Please input two digits to run equations."
        elif "read" in text_lower or "http" in text_lower:
            words = text_lower.split()
            url = next((w for w in words if w.startswith("http")), None)
            if url:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    html = urllib.request.urlopen(req).read()
                    page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
                    st.session_state["text_out"] = f"🌐 Extracted link paragraphs:\n\n\"{page_text[:600]}...\""
                except Exception as e: st.session_state["text_out"] = f"❌ Socket Error: {str(e)}"
            else: st.session_state["text_out"] = "❌ Link Error: Missing valid http prefix link target."
        else:
            try:
                if uploaded_image:
                    image_bytes = uploaded_image.read()
                    prompt_to_use = user_input if user_input else "Describe this image asset in deep detail."
                    response = client.models.generate_content(model=TEXT_MODEL, contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use])
                else:
                    response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                st.session_state["text_out"] = response.text
            except Exception as e: st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
        st.rerun()

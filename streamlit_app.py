import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF

# Configure luxury full-width layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to force the plus menu and mic inline inside the search capsule
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 50px !important; margin-bottom: 25px !important;}
.stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; border: none !important; width: 100% !important; }
.stDownloadButton>button:hover { background-color: #059669 !important; }

/* HARD-FORCING EVERY CONTROL ONTO 1 SINGLE HORIZONTAL CHAT PILL LINE */
.stChatInput {
    background-color: #1e202a !important;
    border-radius: 30px !important;
    border: 1px solid #2e3244 !important;
    padding: 2px 45px 2px 50px !important; /* Left padding moves text right for Plus, right padding makes room for Mic */
    position: relative !important;
}
.stChatInput div { background-color: transparent !important; border: none !important; }
.stChatInput textarea { color: white !important; font-size: 15px !important; }

/* Styling the orange up-arrow submit trigger capsule */
.stChatInput button {
    background-color: #d0755d !important;
    color: white !important;
    border-radius: 50% !important;
}
.stChatInput button:hover { background-color: #be654e !important; }

/* ABSOLUTE OVERLAY POSITIONING: Pinning the Plus Button INSIDE the search bar track */
div[data-testid="stPopover"] {
    position: absolute !important;
    left: 8px !important;
    bottom: 6px !important;
    z-index: 999999 !important;
}

/* Forcing the popover trigger to turn into a tight clean plus sign circular button */
div[data-testid="stPopover"] > button {
    background-color: #2e3244 !important;
    color: #9ca3af !important;
    border: none !important;
    border-radius: 50% !important;
    height: 36px !important;
    width: 36px !important;
    min-width: 36px !important;
    font-size: 20px !important;
    font-weight: bold !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
    padding-bottom: 3px !important;
}

/* ABSOLUTE OVERLAY POSITIONING: Pinning the Mic Button INSIDE the right side of the search bar track */
.mic-wrapper-overlay {
    position: absolute !important;
    right: 52px !important;
    bottom: 6px !important;
    z-index: 999999 !important;
}
div[data-testid="stAudioInput"] { max-width: 36px !important; margin: 0 !important; padding: 0 !important; }
div[data-testid="stAudioInput"] button { 
    background-color: transparent !important; 
    border: none !important; 
    color: #9ca3af !important; 
    height: 36px !important; 
    width: 36px !important; 
}
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
            
    if st.session_state["image_out"]: st.image(st.session_state["image_out"], use_container_width=True)

    # 1. Built-in Popover asset drawer (Pinned to the inside left)
    with st.popover("+"):
        uploaded_image = st.file_uploader("📎 Upload Image to Analyze", type=["png", "jpg", "jpeg"])
        generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # 2. Built-in Mic Voice Input element overlay (Pinned to the inside right)
    st.markdown('<div class="mic-wrapper-overlay">', unsafe_allow_html=True)
    audio_file = st.audio_input("", label_visibility="collapsed")
    st.markdown('</div>', unsafe_allow_html=True)

    # 3. Native chat_input instantly locks a perfect, flat text row capsule bar to the bottom of the screen
    user_input = st.chat_input("Nexus AI")

    # If the user speaks a message without typing, route the voice stream
    if audio_file and not user_input:
        user_input = "Analyze and answer this voice message record request completely."

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if user_input:
        u_valid = 'uploaded_image' in locals() and uploaded_image is not None
        a_valid = 'audio_file' in locals() and audio_file is not None
        art_valid = 'generate_art_mode' in locals() and generate_art_mode
        
        if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
        api_key_str = st.secrets["GEMINI_KEY"]
        client = genai.Client(api_key=api_key_str)
        text_lower = user_input.lower().strip()
        st.session_state["text_out"] = ""
        st.session_state["image_out"] = None
        
        TEXT_MODEL = 'gemini-3.5-flash'
        ART_MODEL = 'imagen-3.0-generate-002'

        if art_valid:
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
                if u_valid:
                    image_bytes = uploaded_image.read()
                    prompt_to_use = user_input if user_input else "Describe this image asset in deep detail."
                    response = client.models.generate_content(model=TEXT_MODEL, contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use])
                elif a_valid:
                    audio_bytes = audio_file.read()
                    response = client.models.generate_content(model=TEXT_MODEL, contents=[types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"), "Transcribe and answer this audio message."])
                else:
                    response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                st.session_state["text_out"] = response.text
            except Exception as e: st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
        st.rerun()

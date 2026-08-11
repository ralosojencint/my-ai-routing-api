import streamlit as st
import urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 40px !important; margin-bottom: 25px !important;}
.stDownloadButton>button { background-color: #10b981 !important; color: white !important; border-radius: 12px !important; font-weight: bold !important; height: 42px !important; border: none !important; width: 100% !important; }
[data-testid="stHorizontalBlock"] {
    display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important; align-items: center !important;
    background-color: #1e202a !important; border-radius: 30px !important; border: 1px solid #2e3244 !important; padding: 4px 14px !important; gap: 8px !important; width: 100% !important;
    position: fixed !important; bottom: 20px !important; left: 50% !important; transform: translateX(-50%) !important; max-width: 90% !important; z-index: 99999 !important;
}
[data-testid="stHorizontalBlock"] > div { width: auto !important; padding: 0 !important; margin: 0 !important; }
[data-testid="stHorizontalBlock"] > div:nth-child(2) { flex-grow: 2 !important; width: 100% !important; }
div[data-testid="stPopover"] > button { background-color: #2e3244 !important; color: white !important; border: none !important; border-radius: 50% !important; height: 38px !important; width: 38px !important; min-width: 38px !important; font-size: 20px !important; font-weight: bold; display: flex !important; align-items: center !important; justify-content: center !important; }
div.stTextInput > div > div > input { background-color: transparent !important; color: white !important; border: none !important; padding-left: 2px !important; height: 38px !important; font-size: 14px !important; }
div.stTextInput > div > div { border: none !important; background-color: transparent !important; box-shadow: none !important; }
.send-btn-box button { background-color: #d0755d !important; color: white !important; border-radius: 50% !important; height: 38px !important; width: 38px !important; min-width: 38px !important; border: none !important; font-size: 16px !important; font-weight: bold !important; display: flex !important; align-items: center !important; justify-content: center !important; }
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

    bar_cols = st.columns(3)
    with bar_cols:
        with st.popover("+"):
            uploaded_image = st.file_uploader("📎 Upload Image to Analyze", type=["png", "jpg", "jpeg"])
            audio_file = st.audio_input("🎤 Record Voice Input")
            generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")
    with bar_cols:
        user_input = st.text_input("", placeholder="Nexus AI", label_visibility="collapsed")
    with bar_cols:
        st.markdown('<div class="send-btn-box">', unsafe_allow_html=True)
        execute_btn = st.button("↑")
        st.markdown('</div>', unsafe_allow_html=True)

    if execute_btn:
        u_valid = 'uploaded_image' in locals() and uploaded_image is not None
        a_valid = 'audio_file' in locals() and audio_file is not None
        art_valid = 'generate_art_mode' in locals() and generate_art_mode
        
        if not user_input and not u_valid and not a_valid:
            st.warning("⚠️ Please provide an instruction text string or choose a file asset link to execute.")
        else:
            if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
            api_key_str = st.secrets["GEMINI_KEY"]
            client = genai.Client(api_key=api_key_str)
            text_lower = user_input.lower().strip() if user_input else ""
            st.session_state["text_out"] = ""
            st.session_state["image_out"] = None
            
            # FIXED KEY ENGINES: Permanently locking in Gemini 3.5 Flash Flagship
            TEXT_MODEL = 'gemini-3.5-flash'
            ART_MODEL = 'imagen-3.0-generate-002'

            if art_valid and user_input:
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

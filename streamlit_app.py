import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
from fpdf import FPDF

# Configure clean layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to upgrade the interface UI to a luxury dark theme profile
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
    padding: 2px 4px !important;
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

    # =========================================================================
    # 📱 THE COMPACT INTERFACE (All Clunky Middle Box Rectangles Are Deleted!)
    # =========================================================================
    # The unbreakable bottom chat capsule bar
    user_input = st.chat_input("Nexus AI")

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
        
        TEXT_MODEL = 'gemini-2.5-flash'

        if "calculate" in text_lower or "math" in text_lower:
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
                response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                st.session_state["text_out"] = response.text
            except Exception as e: st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
        st.rerun()

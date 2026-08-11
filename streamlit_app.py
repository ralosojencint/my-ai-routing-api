import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to force an absolute compact ChatGPT/Claude mobile pill bar
st.markdown("""
    <style>
    .stApp { background-color: #0d0e12; }
    h1, h3 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-bottom: 2px !important;}
    
    /* Transforming input fields into clean capsule shapes */
    div.stTextInput > div > div > input {
        background-color: #1e202a !important;
        color: #ffffff !important;
        border-radius: 25px !important;
        border: 1px solid #2e3244 !important;
        padding-left: 20px !important;
        height: 48px !important;
        font-size: 14px !important;
    }
    div.stTextInput > div > div { border: none !important; background-color: transparent !important; }
    
    /* Making upload look clean and minimalist */
    div[data-testid="stFileUploader"] { margin-top: 0px !important; padding: 0 !important; }
    div[data-testid="stFileUploaderDropzone"] { padding: 4px !important; background-color: transparent !important; border: none !important; }
    div[data-testid="stFileUploaderDropzone"] button { 
        background-color: #2e3244 !important; 
        color: white !important; 
        border-radius: 20px !important; 
        height: 40px !important; 
        font-size: 14px !important;
        font-weight: bold !important;
    }
    
    /* Custom Orange Arrow Send Button Structure */
    .send-btn-box button {
        background-color: #d0755d !important;
        color: white !important;
        border-radius: 50% !important;
        height: 44px !important;
        width: 44px !important;
        min-width: 44px !important;
        border: none !important;
        font-size: 18px !important;
        font-weight: bold !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
    }
    .send-btn-box button:hover { background-color: #be654e !important; }
    </style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state:
    st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False
if "text_out" not in st.session_state:
    st.session_state["text_out"] = None
if "image_out" not in st.session_state:
    st.session_state["image_out"] = None

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
    # 🎯 THE MIDDLE OUTPUT LAYER (Locks outputs in center view)
    # =============================================================
    output_holder = st.empty()
    art_holder = st.empty()
    
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
    if st.session_state["image_out"]:
        art_holder.image(st.session_state["image_out"], use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # =============================================================
    # 📱 EXECUTIVE INTERACTIVE CONTROL GRID CONTAINER (True Multi-Control Dashboard)
    # =============================================================
    # Stacking components inside a clean, balanced layout container block to maximize phone viewport tracking
    st.markdown("### 🛠️ Nexus Control Hub")
    
    user_input = st.text_input(
        "", 
        placeholder="Ask anything, paste links, or generate AI art...",
        label_visibility="collapsed"
    )
    
    # Clean secondary interactive option cards stacked below the central input bar
    col_left, col_mid, col_right = st.columns([1.5, 1.5, 1])
    
    with col_left:
        # Changes file upload button text indicator string to a clean premium identifier tag
        uploaded_image = st.file_uploader("+ Attach File", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
    with col_mid:
        # Integrates voice mic stream input tool right next to file attachments
        audio_file = st.audio_input("🎤 Record Voice", label_visibility="collapsed")
    with col_right:
        # Compact orange circle wrapper enclosing the up arrow execution button
        st.markdown('<div class="send-btn-box">', unsafe_allow_html=True)
        execute_btn = st.button("↑")
        st.markdown('</div>', unsafe_allow_html=True)

    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # If user uses the voice recorder option, automatically configure prompt logic structures
    if audio_file and not user_input:
        user_input = "Transcribe and evaluate this voice message request completely."

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS (Fixed Syntax Errors)
    # ==========================================
    if execute_btn:
        if not user_input and not uploaded_image and not audio_file:
            st.warning("⚠️ Please provide an instruction text string, voice audio, or photo asset link to execute.")
        else:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
                
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
                    result = client.models.generate_images(
                        model=ART_MODEL, prompt=user_input,
                        config=dict(number_of_images=1, output_mime_type="image/jpeg")
                    )
                    for generated_image in result.generated_images:
                        st.session_state["image_out"] = generated_image.image.image_bytes
                    st.session_state["text_out"] = "✨ Deep creative render pipeline successful!"
                except Exception as e:
                    st.session_state["text_out"] = f"❌ Creative Art Engine Fault: {str(e)}"

            elif "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2:
                    st.session_state["text_out"] = f"```text\n💡 Programmatic Compute:\n{numbers} + {numbers} = {numbers + numbers}\n```"
                else:
                    st.session_state["text_out"] = "❌ Logic Error: Please input two digits to run equations."

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
                    except Exception as e:
                        st.session_state["text_out"] = f"❌ Socket Error: Couldn't scrap url target: {str(e)}"
                else:
                    st.session_state["text_out"] = "❌ Link Error: Missing valid http prefix link target."

            else:
                output_holder.info("🧠 Syncing cloud tokens... Querying central intelligence processing...")
                try:
                    if uploaded_image:
                        image_bytes = uploaded_image.read()
                        prompt_to_use = user_input if user_input else "Describe this image asset in deep detail."
                        response = client.models.generate_content(
                            model=TEXT_MODEL,
                            contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use]
                        )
                    elif audio_file:
                        audio_bytes = audio_file.read()
                        response = client.models.generate_content(
                            model=TEXT_MODEL,

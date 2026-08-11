import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to force an absolute compact ChatGPT/Claude mobile bar
st.markdown("""
    <style>
    .stApp { background-color: #0d0e12; }
    h1, h3 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-bottom: 2px !important;}
    
    /* Strict Horizontal Flex Layout to snap all controls onto 1 flat line */
    .chat-container-dock {
        display: flex !important;
        align-items: center !important;
        background-color: #1e202a !important;
        border-radius: 28px !important;
        border: 1px solid #2e3244 !important;
        padding: 4px 8px !important;
        width: 100% !important;
        gap: 6px !important;
    }
    
    /* Shrinking default form paddings to prevent vertical line breaking stretching */
    div.stTextInput { width: 100% !important; padding: 0 !important; margin: 0 !important; }
    div.stTextInput > div > div > input {
        background-color: transparent !important;
        color: #ffffff !important;
        border: none !important;
        padding-left: 4px !important;
        height: 38px !important;
        font-size: 14px !important;
    }
    div.stTextInput > div > div { border: none !important; background-color: transparent !important; }
    
    /* Compact Circular Plus Upload Button Formatting */
    div[data-testid="stFileUploader"] { width: auto !important; max-width: 42px !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
    div[data-testid="stFileUploaderDropzone"] button { 
        background-color: #2e3244 !important; 
        color: #ffffff !important; 
        border-radius: 50% !important; 
        height: 36px !important; 
        width: 36px !important; 
        min-width: 36px !important; 
        font-size: 18px !important;
        font-weight: bold !important;
        padding: 0 !important;
        border: none !important;
    }
    div[data-testid="stFileUploaderDropzone"] button::after { content: "" !important; }
    div[data-testid="stFileUploaderDropzone"] span { display: none !important; }
    
    /* Custom Orange Arrow Send Button Structure */
    .send-btn-box button {
        background-color: #d0755d !important;
        color: white !important;
        border-radius: 50% !important;
        height: 36px !important;
        width: 36px !important;
        min-width: 36px !important;
        border: none !important;
        font-size: 18px !important;
        font-weight: bold !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0 !important;
        margin: 0 !important;
    }
    .send-btn-box button:hover { background-color: #be654e !important; }
    
    /* Audio controller placement tracks */
    div[data-testid="stAudioInput"] { width: auto !important; max-width: 42px !important; margin: 0 !important; padding: 0 !important; }
    div[data-testid="stAudioInput"] button { background-color: #2e3244 !important; border-radius: 50% !important; height: 36px !important; width: 36px !important; border: none !important; }
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
    # 🎯 THE MIDDLE OUTPUT LAYER
    # =============================================================
    output_holder = st.empty()
    art_holder = st.empty()
    
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
    if st.session_state["image_out"]:
        art_holder.image(st.session_state["image_out"], use_container_width=True)

    # =============================================================
    # 📱 HORIZONTAL CAPSULE COMPACT UTILITY DOCKBAR
    # =============================================================
    # Combining Streamlit fields linearly inside a continuous micro column layout grid matrix
    container_cols = st.columns([1, 6, 1, 1], gap="small")
    
    with container_cols[0]:
        # Custom button overrides render this label-less uploader widget into a crisp grey "+" circle icon 
        uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        
    with container_cols[1]:
        user_input = st.text_input(
            "", 
            placeholder="Chat with Nexus...",
            label_visibility="collapsed"
        )
        
    with container_cols[2]:
        # Injecting native voice input microphone module directly inside the input sequence tracks
        audio_file = st.audio_input("", label_visibility="collapsed")
        
    with container_cols[3]:
        # Wrapping send trigger into a custom scoped target block class to force style into the orange up-arrow layout profile
        st.markdown('<div class="send-btn-box">', unsafe_allow_html=True)
        execute_btn = st.button("↑")
        st.markdown('</div>', unsafe_allow_html=True)

    # Optional functional mode controller toggle right beneath the capsule dock bar
    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # Processing prompt overrides if voice recorder captures audio statements 
    if audio_file and not user_input:
        user_input = "Transcribe and analyze this captured voice file structure segment commands."

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
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

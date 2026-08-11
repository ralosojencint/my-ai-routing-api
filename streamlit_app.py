import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Modern luxury layout setup
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Executive UI Customization Layer to enforce a true single-row chat layout
st.markdown("""
    <style>
    .stApp { background-color: #0d0e12; }
    h1, h3 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; }
    
    /* Creating a true horizontal flex bar container for the input elements */
    [data-testid="stHorizontalBlock"] {
        background-color: #1e202a !important;
        border-radius: 30px !important;
        border: 1px solid #2e3244 !important;
        padding: 6px 12px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: space-between !important;
    }
    
    /* Clean unbordered formatting for input within the container capsule */
    div.stTextInput > div > div > input {
        background-color: transparent !important;
        color: #ffffff !important;
        border: none !important;
        padding-left: 10px !important;
        height: 44px !important;
    }
    div.stTextInput > div > div { border: none !important; background-color: transparent !important; }
    
    /* Transforming the action button into a neat circular chat icon trigger */
    .stButton>button {
        background-color: #2563eb !important;
        color: white !important;
        border-radius: 50% !important;
        font-weight: bold !important;
        height: 44px !important;
        width: 44px !important;
        min-width: 44px !important;
        border: none !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .stButton>button:hover { background-color: #1d4ed8 !important; }
    
    /* Minimizing the file uploader widget to look like a small upload paperclip */
    div[data-testid="stFileUploader"] { margin-top: 0px !important; padding: 0 !important; }
    div[data-testid="stFileUploaderDropzone"] { padding: 4px !important; background-color: transparent !important; border: none !important; }
    div[data-testid="stFileUploaderDropzone"] button { background-color: #2e3244 !important; color: white !important; border-radius: 20px !important; height: 36px !important; font-size: 12px !important; }
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

# BRAND UPGRADE: PREMIUM WORD AND SUBTITLE TEXT ARE ENTIRELY REMOVED
st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 Daily Session Limit Reached ({FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT})")
    st.info("💡 Upgrade to Premium membership (\$9.99/month) to unlock unlimited data pipelines instantly.")
    st.markdown("[👉 Click Here to Unlock Unlimited Access](https://lemonsqueezy.com)")
else:
    st.markdown("<br>", unsafe_allow_html=True)

    # =============================================================
    # 🎯 THE MIDDLE OUTPUT WINDOWS
    # =============================================================
    output_holder = st.empty()
    art_holder = st.empty()
    
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
    if st.session_state["image_out"]:
        art_holder.image(st.session_state["image_out"], use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # =============================================================
    # 📱 TRUE COMBINED ONE-ROW CHAT BAR (Exactly Like ChatGPT)
    # =============================================================
    # Splitting into a highly weighted row matrix to force items side-by-side
    col_input, col_upload, col_btn = st.columns([6, 3, 1])
    
    with col_input:
        user_input = st.text_input(
            "", 
            placeholder="Ask anything, paste links, or paint art...",
            label_visibility="collapsed"
        )
        
    with col_upload:
        uploaded_image = st.file_uploader("", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        
    with col_btn:
        execute_btn = st.button("🚀")

    # Mode checkbox sitting neatly right beneath the capsule bar
    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if execute_btn:
        if not user_input and not uploaded_image:
            st.warning("⚠️ Please provide an instruction text string or photo asset link to execute.")
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
                        st.session_state["text_out"] = f"❌ Socket Error: Couldn't scrap url target. {str(e)}"

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
                    else:
                        response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                    
                    st.session_state["text_out"] = f"\n\n{response.text}"
                except Exception as e:
                    st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
            
            st.rerun()

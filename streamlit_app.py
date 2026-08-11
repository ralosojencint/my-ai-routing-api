import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Modern luxury layout setup
st.set_page_config(page_title="NexusAI Premium Suite", page_icon="✨", layout="centered")

# Executive UI Customization Layer to style the sleek capsule toolbar
st.markdown("""
    <style>
    .stApp { background-color: #0d0e12; }
    h1, h3 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; }
    .stCaption { text-align: center; color: #9ca3af !important; }
    
    /* Transforming input fields into clean luxury dark capsules */
    div.stTextInput > div > div > input {
        background-color: #1e202a !important;
        color: #ffffff !important;
        border-radius: 25px !important;
        border: 1px solid #2e3244 !important;
        padding-left: 20px !important;
        height: 52px !important;
    }
    
    /* Styling the multitask launch button */
    .stButton>button {
        background-color: #2563eb !important;
        color: white !important;
        border-radius: 25px !important;
        font-weight: bold !important;
        height: 52px !important;
        border: none !important;
        width: 100% !important;
    }
    .stButton>button:hover { background-color: #1d4ed8 !important; }
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

# SECURE ACCESSIBILITY SIDEBAR
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

st.title("✨ NexusAI Premium Suite")
st.caption("Advanced multi-engine framework running unified scraping, text intelligence, and image generation pipelines.")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 Daily Session Limit Reached ({FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT})")
    st.info("💡 Upgrade to Premium membership (\$9.99/month) to unlock unlimited data pipelines instantly.")
    st.markdown("[👉 Click Here to Unlock Unlimited Access](https://lemonsqueezy.com)")
else:
    st.markdown("<br>", unsafe_allow_html=True)

    # =============================================================
    # 🎯 THE MIDDLE OUTPUT CODES (Pinned dynamically to the center)
    # =============================================================
    output_holder = st.empty()
    art_holder = st.empty()
    
    # Persistent render loop keeping outputs frozen dead center on screen refresh loops
    if st.session_state["text_out"]:
        output_holder.markdown(f"### 📊 Live System Engine Outputs\n{st.session_state['text_out']}")
    if st.session_state["image_out"]:
        art_holder.image(st.session_state["image_out"], use_container_width=True)

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("---")

    # =============================================================
    # 📱 UNIFIED CAPSULE BAR DESIGN (ChatGPT-Style Composite layout)
    # =============================================================
    col1, col2 = st.columns([4, 1])
    
    with col1:
        # Combined prompt field handling questions, artwork creation prompts, and web links
        user_input = st.text_input(
            "", 
            placeholder="Ask anything, paste http://... links, or generate AI art...",
            label_visibility="collapsed"
        )
        
    with col2:
        # High performance trigger button styled like a modern chat send icon link
        execute_btn = col2.button("🚀")

    # Clean utility toggles tucked neatly right beneath the main interface capsule bar
    expander_col1, expander_col2 = st.columns(2)
    with expander_col1:
        uploaded_image = st.file_uploader("📎 Attach Photo to Analyze", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
    with expander_col2:
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
            
            # Wiping old session traces
            st.session_state["text_out"] = ""
            st.session_state["image_out"] = None
            
            TEXT_MODEL = 'gemini-3.5-flash'
            ART_MODEL = 'imagen-3.0-generate-002'

            # ROUTE A: NEURAL AI ART EXPERIMENT WING
            if generate_art_mode:
                output_holder.warning("🎨 Initiating Imagen Neural Networks... Drawing your artwork canvas...")
                try:
                    result = client.models.generate_images(
                        model=ART_MODEL, prompt=user_input,
                        config=dict(number_of_images=1, output_mime_type="image/jpeg")
                    )
                    for generated_image in result.generated_images:
                        st.session_state["image_out"] = generated_image.image.image_bytes
                    st.session_state["text_out"] = "✨ Deep creative render pipeline operation successful!"
                except Exception as e:
                    st.session_state["text_out"] = f"❌ Creative Art Engine Fault: {str(e)}"

            # ROUTE B: PROGRAMMATIC MATHEMATICAL NUMBERS
            elif "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2:
                    st.session_state["text_out"] = f"```text\n💡 Programmatic Compute:\n{numbers} + {numbers} = {numbers + numbers}\n```"
                else:
                    st.session_state["text_out"] = "❌ Logic Error: Please input two digits to run equations."

            # ROUTE C: AUTONOMOUS WEB SCRAPER SCRIPT
            elif "read" in text_lower or "http" in text_lower:
                output_holder.info("🌐 Establishing secure sockets... Extracting remote HTML strings...")
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

            # ROUTE D: IMAGE ANALYSIS AND TEXT REASONING HUB
            else:
                output_holder.info("🧠 Syncing cloud tokens... Querying central intelligence processing arrays...")
                try:
                    # Check if a multimodal image reader parsing task is being requested
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
                    st.session_state["text_out"] = f"❌ Critical Pipeline Disconnection Error: {str(e)}"
            
            st.rerun()

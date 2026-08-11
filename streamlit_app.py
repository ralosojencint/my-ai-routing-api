import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱", layout="centered")

# Initialize global state tracking variables
if "anonymous_clicks" not in st.session_state:
    st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False

FREE_DAILY_LIMIT = 3

# SIDEBAR MONETIZATION WALL
with st.sidebar:
    st.header("👑 Member Access")
    if not st.session_state["is_premium"]:
        st.write("Status: `FREE TIER`")
        pass_input = st.text_input("Unlock Premium Key Pass", type="password")
        if pass_input == "premium123":
            st.session_state["is_premium"] = True
            st.success("Premium Unlocked! Enjoy infinite queries.")
            st.rerun()
    else:
        st.write("Status: `👑 PREMIUM ACTIVE`")
        if st.button("Log Out of Premium"):
            st.session_state["is_premium"] = False
            st.session_state["anonymous_clicks"] = 0
            st.rerun()

st.title("📱 Mobile AI Multitask Agent")
st.write("Process text instructions, live web scrapers, image reading, and AI art generation directly from one single workspace layout.")

# CHECK FREEMIUM LIMITS
if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 You have reached your Free Tier limit of {FREE_DAILY_LIMIT} requests for today!")
    st.info("💡 Remove limitations instantly! Upgrade to Premium for unlimited text processing, scraping, vision models, and image artwork generation.")
    st.markdown("[👉 Click Here to Unlock Premium Membership ($9.99/month)](https://lemonsqueezy.com)")
else:
    if not st.session_state["is_premium"]:
        st.caption(f"📊 Free Meter: Used {st.session_state['anonymous_clicks']} of your {FREE_DAILY_LIMIT} open daily actions.")

    # ==========================================
    # 🎛️ THE ONE SINGLE WORKSPACE CONTAINER HOOD
    # ==========================================
    st.markdown("### 🛠️ Input Control Center")
    
    # 1. Core Text Field (Handles Questions, Scrapers, Math, and Vision Queries)
    user_input = st.text_input("Your Text Request / Prompt", placeholder="e.g., Who is Elon Musk?, read https://example.com, or ask about your uploaded photo")
    
    # 2. Image Reader Input (Drop a photo here to inject vision processing)
    uploaded_image = st.file_uploader("📸 Image Reader (Optional: Drop a photo to analyze or read text inside it)", type=["png", "jpg", "jpeg"])
    
    # 3. Image Generator Toggle (Check this box if you want to turn your text prompt into AI Art)
    generate_art_mode = st.checkbox("🎨 Image Generator Mode (Check this box to turn your prompt text into AI Artwork!)")
    
    # THE ONE SINGLE ACTION BUTTON FOR ALL ENGINES
    execute_btn = st.button("🚀 Execute Multitask Pipeline", type="primary")

    # ==========================================
    # 🧠 UNIFIED BACKEND PROCESSING SYSTEM
    # ==========================================
    def unified_engine(text_input, img_file, art_mode_active):
        text_lower = text_input.lower().strip()
        api_key_str = st.secrets["GEMINI_KEY"]
        client = genai.Client(api_key=api_key_str)
        
        # ACTIVE FLAGGED PRODUCTION MODEL TARGETS
        TEXT_MODEL = 'gemini-3.5-flash'
        ART_MODEL = 'imagen-3.0-generate-002'

        # ENGINE ROUTE A: AI IMAGE GENERATOR WORKFLOW
        if art_mode_active:
            if not text_input:
                return "⚠️ Input Required:\nPlease describe the artwork image you want to create inside the Text Request box first."
            try:
                result = client.models.generate_images(
                    model=ART_MODEL,
                    prompt=text_input,
                    config=dict(number_of_images=1, output_mime_type="image/jpeg")
                )
                # Store the image bytes directly into a special container variable to show the user
                st.session_state["last_artwork_generated"] = result.generated_images[0].image.image_bytes
                return "🎨 AI Image Generation Complete! Look below the box to view your artwork."
            except Exception as e:
                return f"🎨 Art Generation Error: {str(e)}"

        # ENGINE ROUTE B: MATH COMPUTER LOGIC
        elif "calculate" in text_lower or "math" in text_lower:
            numbers = [int(s) for s in text_lower.split() if s.isdigit()]
            if len(numbers) >= 2: 
                return f"💡 AI Math Result:\n{numbers} + {numbers} = {numbers + numbers}"
            return "💡 AI Math Error:\nPlease provide two numbers inside your prompt text."
            
        # ENGINE ROUTE C: LIVE WEB SCRAPER SCANNER
        elif "read" in text_lower or "http" in text_lower:
            words = text_lower.split()
            url = next((w for w in words if w.startswith("http")), None)
            if not url: return "💡 AI Web Error:\nPlease provide a full link starting with http."
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                html = urllib.request.urlopen(req).read()
                page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
                return f"💡 AI Web Scraper Result:\n\n\"{page_text[:400]}...\""
            except Exception as e: return f"💡 AI Web Error:\nCould not read link: {str(e)}"
            
        # ENGINE ROUTE D: IMAGE READER (VISION / OCR TEXT EXTRACTION)
        elif img_file is not None:
            try:
                image_bytes = img_file.read()
                prompt_to_use = text_input if text_input else "Describe what you see or read any visible text within this image file in complete detail."
                
                response = client.models.generate_content(
                    model=TEXT_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type=img_file.type),
                        prompt_to_use
                    ]
                )
                return f"👁️ Image Analysis Output:\n\n{response.text}"
            except Exception as e:
                return f"👁️ Vision Model Processing Error: {str(e)}"

        # ENGINE ROUTE E: STANDARD INTELLIGENT AI ASSISTANT ANSWER
        else:
            if not text_input:
                return "⚠️ System Waiting:\nPlease type an instruction or upload an item to begin processing data pipeline loops."
            try:
                response = client.models.generate_content(
                    model=TEXT_MODEL,
                    contents=text_input,
                )
                return f"🧠 Intelligent AI Analysis:\n\n{response.text}"
            except Exception as e:
                return f"💡 System Connection Warning:\nRe-establishing background token routing. Details: {str(e)}"

    # TRICK SYSTEM PIPELINE ON BUTTON CLICK ACTIONS
    if execute_btn:
        if not st.session_state["is_premium"]:
            st.session_state["anonymous_clicks"] += 1
            
        # Clear out previous art memories before running a fresh calculation loop
        if "last_artwork_generated" in st.session_state:
            del st.session_state["last_artwork_generated"]
            
        with st.spinner("Processing Application Data Pipeline..."):
            pipeline_output = unified_engine(user_input, uploaded_image, generate_art_mode)
            st.markdown("### 📊 AI System Output Container")
            st.text_area("System Response Window", value=pipeline_output, height=300)
            
            # If an artwork string triggered successfully, display the layout canvas blocks right below the text window
            if "last_artwork_generated" in st.session_state:
                st.image(st.session_state["last_artwork_generated"], caption=f"Generated Prompt: {user_input}", use_container_width=True)
                
            # st.rerun()


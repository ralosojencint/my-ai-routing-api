import streamlit as st
import urllib.request
import json
import base64
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱", layout="centered")

# Initialize state trackers for usage tracking and custom tiers
if "anonymous_clicks" not in st.session_state:
    st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False

FREE_DAILY_LIMIT = 3

# SIDEBAR MONETIZATION CONTROL PANEL
with st.sidebar:
    st.header("👑 Member Access")
    if not st.session_state["is_premium"]:
        st.write("Status: `FREE TIER`")
        # Enter your secret master pass key or connect a Stripe/Lemon Squeezy callback here
        pass_input = st.text_input("Unlock Premium Key Pass", type="password")
        if pass_input == "premium123":  # Give this pass word to paying customers
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
st.write("Process texts, scrapers, math, custom images, and AI artwork instantly!")

# CHECK IF ANONYMOUS VISITOR CONSUMED LIMITS
if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 You have reached your Free Tier limit of {FREE_DAILY_LIMIT} requests for today!")
    st.info("💡 Remove limitations instantly! Upgrade to Premium for unlimited text processing, scraping, vision models, and image artwork generation.")
    st.markdown("[👉 Click Here to Unlock Premium Membership ($9.99/month)](https://lemonsqueezy.com)")
else:
    if not st.session_state["is_premium"]:
        st.caption(f"📊 Free Meter: Used {st.session_state['anonymous_clicks']} of your {FREE_DAILY_LIMIT} open daily actions.")

    # TABS FOR CLEAN ENGINE NAVIGATION
    tab1, tab2, tab3 = st.tabs(["💬 Text & Scraper Router", "👁️ Image Reader (Vision)", "🎨 Image Generator"])

    # --- TAB 1: TEXT/MATH/SCRAPER AUTOMATION ENGINE ---
    with tab1:
        user_input = st.text_input("Your Command/Prompt", placeholder="e.g., read https://example.com or ask a question")
        execute_btn = st.button("Run Action Pipeline", type="primary")

        def core_engine(text_input):
            text_lower = text_input.lower().strip()
            
            if "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2: return f"💡 AI Math Result:\n{numbers} + {numbers} = {numbers + numbers}"
                return "💡 AI Math Error:\nPlease provide two numbers."
                
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
                
            else:
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=text_input,
                    )
                    return f"🧠 Gemini AI Brain Response:\n\n{response.text}"
                except Exception as e:
                    return f"💡 Core Error Details: {str(e)}"

        if execute_btn and user_input:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
            with st.spinner("AI Processing..."):
                result = core_engine(user_input)
                st.text_area("System Output", value=result, height=250)
                st.rerun()

    # --- TAB 2: IMAGE READER VISION ENGINE ---
    with tab2:
        uploaded_image = st.file_uploader("Upload an Image to Analyze", type=["png", "jpg", "jpeg"])
        vision_prompt = st.text_input("What do you want to ask about this image?", value="Describe what you see in this image in detail.")
        run_vision = st.button("Analyze Uploaded Image", type="primary")

        if run_vision and uploaded_image:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
            with st.spinner("Reading Image Data..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                    image_bytes = uploaded_image.read()
                    
                    response = client.models.generate_content(
                        model='gemini-2.0-flash',
                        contents=[
                            types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type),
                            vision_prompt
                        ]
                    )
                    st.success("🤖 Analysis Complete:")
                    st.write(response.text)
                except Exception as e:
                    st.error(f"Vision Processing Error: {str(e)}")
                st.rerun()

    # --- TAB 3: IMAGE GENERATOR ART ENGINE ---
    with tab3:
        art_prompt = st.text_input("Describe the image you want to create", placeholder="e.g., A cinematic shot of a neon cyber city at night")
        generate_art = st.button("Generate AI Artwork", type="primary")

        if generate_art and art_prompt:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
            with st.spinner("Generating Art via Imagen 3 Engine..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
                    result = client.models.generate_images(
                        model='imagen-3.0-generate-002',
                        prompt=art_prompt,
                        config=dict(number_of_images=1, output_mime_type="image/jpeg")
                    )
                    for generated_image in result.generated_images:
                        image = types.Image.from_bytes(generated_image.image.image_bytes)
                        st.image(generated_image.image.image_bytes, caption=f"Prompt: {art_prompt}", use_container_width=True)
                except Exception as e:
                    st.error(f"Image Generation Error: {str(e)}")
                st.rerun()

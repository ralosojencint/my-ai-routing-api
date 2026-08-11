import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

st.set_page_config(page_title="Mobile AI Multitask Agent", page_icon="📱", layout="centered")

if "anonymous_clicks" not in st.session_state:
    st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False

FREE_DAILY_LIMIT = 3

with st.sidebar:
    st.header("👑 Member Access")
    if not st.session_state["is_premium"]:
        st.write("Status: `FREE TIER`")
        pass_input = st.text_input("Unlock Premium Key Pass", type="password")
        if pass_input == "premium123":
            st.session_state["is_premium"] = True
            st.success("Premium Unlocked!")
            st.rerun()
    else:
        st.write("Status: `👑 PREMIUM ACTIVE`")
        if st.button("Log Out of Premium"):
            st.session_state["is_premium"] = False
            st.session_state["anonymous_clicks"] = 0
            st.rerun()

st.title("📱 Mobile AI Multitask Agent")
st.write("Process texts, scrapers, math, custom images, and AI artwork instantly!")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 You have reached your Free Tier limit of {FREE_DAILY_LIMIT} requests for today!")
    st.info("💡 Upgrade to Premium for unlimited processing blocks.")
    st.markdown("[👉 Click Here to Unlock Premium Membership ($9.99/month)](https://lemonsqueezy.com)")
else:
    if not st.session_state["is_premium"]:
        st.caption(f"📊 Free Meter: Used {st.session_state['anonymous_clicks']} of your {FREE_DAILY_LIMIT} open daily actions.")

    st.markdown("### 🛠️ Input Control Center")
    
    # CHANGED SEARCH TITLE TEXT LINK RIGHT HERE:
    user_input = st.text_input("🔍 Type Your Core AI Command / Prompt Box", placeholder="e.g., A cute cat, Who is Elon Musk?, or read https://example.com")
    uploaded_image = st.file_uploader("📸 Drop a Photo to Analyze (Optional)", type=["png", "jpg", "jpeg"])
    
    execute_btn = st.button("🚀 Execute Simultaneous Multitask Suite", type="primary")

    if execute_btn:
        if not text_input and not uploaded_image:
            st.warning("⚠️ Please provide a prompt or upload a photo to begin.")
        else:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
                
            api_key_str = st.secrets["GEMINI_KEY"]
            client = genai.Client(api_key=api_key_str)
            text_lower = user_input.lower().strip()

            st.markdown("### 📊 AI Multitask System Outputs")
            
            # --- OUTPUT 1: CORE TEXT LOGIC ROUTER ---
            if "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2: 
                    st.info(f"💡 AI Math Result:\n{numbers} + {numbers} = {numbers + numbers}")
            elif "read" in text_lower or "http" in text_lower:
                words = text_lower.split()
                url = next((w for w in words if w.startswith("http")), None)
                if url:
                    try:
                        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                        html = urllib.request.urlopen(req).read()
                        page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
                        st.text_area("🌐 Scraper Extraction Window", value=f"💡 Result:\n\"{page_text[:400]}...\"", height=150)
                    except Exception as e: st.error(f"Scraper Error: {str(e)}")
            elif user_input:
                with st.spinner("Generating Intelligence Text Analysis..."):
                    try:
                        response = client.models.generate_content(model='gemini-3.5-flash', contents=user_input)
                        st.text_area("🧠 Intelligent Text Response", value=response.text, height=250)
                    except Exception as e: st.error(f"Text Error: {str(e)}")

            # --- OUTPUT 2: IMAGE ANALYSIS MODEL ROUTER ---
            if uploaded_image:
                with st.spinner("Processing Image Analytics..."):
                    try:
                        image_bytes = uploaded_image.read()
                        prompt_to_use = user_input if user_input else "Describe this image in deep detail."
                        response = client.models.generate_content(
                            model='gemini-3.5-flash',
                            contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use]
                        )
                        st.text_area("👁️ Image Reader Response", value=response.text, height=200)
                    except Exception as e: st.error(f"Vision Error: {str(e)}")

            # --- OUTPUT 3: AI IMAGEN GENERATOR ART ENGINE ---
            if user_input and not "read" in text_lower and not "http" in text_lower:
                with st.spinner("Generating AI Core Artwork..."):
                    try:
                        result = client.models.generate_images(
                            model='imagen-3.0-generate-002',
                            prompt=user_input,
                            config=dict(number_of_images=1, output_mime_type="image/jpeg")
                        )
                        for generated_image in result.generated_images:
                            st.image(generated_image.image.image_bytes, caption=f"🎨 Generated AI Art for: '{user_input}'", use_container_width=True)
                    except Exception as e: st.error(f"Art Engine Notification: {str(e)}")

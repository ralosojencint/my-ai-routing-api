import streamlit as st
import urllib.request
import json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Initialize modern full-width clean canvas layout
st.set_page_config(page_title="NexusAI Premium Suite", page_icon="✨", layout="centered")

# Visual CSS styling to upgrade the interface UI to a luxury dark theme profile
st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; }
    h1 { color: #f3f4f6 !important; font-weight: 800 !important; font-family: 'Inter', sans-serif; }
    .stButton>button { background-color: #6366f1 !important; color: white !important; border-radius: 8px !important; width: 100% !important; font-weight: bold !important; height: 50px; border: none !important; }
    .stButton>button:hover { background-color: #4f46e5 !important; }
    </style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state:
    st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state:
    st.session_state["is_premium"] = False

FREE_DAILY_LIMIT = 3

with st.sidebar:
    st.markdown("### 👑 Premium Membership")
    if not st.session_state["is_premium"]:
        st.write("Status: `FREE TIER`")
        pass_input = st.text_input("Unlock Executive Pass", type="password")
        if pass_input == "premium123":
            st.session_state["is_premium"] = True
            st.success("Executive Access Granted!")
            st.rerun()
    else:
        st.write("Status: `👑 EXECUTIVE ACCESS ACTIVE`")
        if st.button("Secure Logout"):
            st.session_state["is_premium"] = False
            st.session_state["anonymous_clicks"] = 0
            st.rerun()

# BRAND UPGRADE NAME CHANGE
st.title("✨ NexusAI Premium Suite")
st.caption("The complete all-in-one pipeline: Advanced text intelligence, automated web scraping, multimodal image processing, and high-fidelity AI art generation.")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= FREE_DAILY_LIMIT:
    st.error(f"🛑 Free Tier Limit Reached ({FREE_DAILY_LIMIT}/{FREE_DAILY_LIMIT} requests used for today)")
    st.info("💡 Unlock infinite processing pipelines instantly. Upgrade to Premium for unrestricted computing throughput across all models.")
    st.markdown("[👉 Click Here to Unlock Unlimited Access ($9.99/month)](https://lemonsqueezy.com)")
else:
    if not st.session_state["is_premium"]:
        st.caption(f"📊 Usage Remaining: {FREE_DAILY_LIMIT - st.session_state['anonymous_clicks']} free requests left today.")

    st.markdown("---")
    
    # COMBINED VISUAL INPUT HUB WITH UPDATED HEADERS AND PLACEHOLDERS
    user_input = st.text_input(
        "💬 Enter Your Vision or AI Artwork Instruction Prompt", 
        placeholder="e.g., A majestic white tiger, Who is Elon Musk?, or explain this photo"
    )
    uploaded_image = st.file_uploader("📸 Drop a Photo to Analyze / Extract Text (Optional)", type=["png", "jpg", "jpeg"])
    
    st.markdown("<br>", unsafe_allow_html=True)
    execute_btn = st.button("🚀 Run Simultaneous Multitask Pipeline Suite", type="primary")

    if execute_btn:
        # THE FIX: Correctly maps variables to prevent the NameError bug
        if not user_input and not uploaded_image:
            st.warning("⚠️ Please input text instructions or upload a file template to engage the core engine.")
        else:
            if not st.session_state["is_premium"]:
                st.session_state["anonymous_clicks"] += 1
                
            api_key_str = st.secrets["GEMINI_KEY"]
            client = genai.Client(api_key=api_key_str)
            text_lower = user_input.lower().strip()

            st.markdown("---")
            st.markdown("### 📊 Live System Engine Outputs")
            
            # --- OUT 1: TEXT/SCRAPER ENGINE ---
            if "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2: 
                    st.info(f"💡 Local Compute Result: {numbers} + {numbers} = {numbers + numbers}")
            elif "read" in text_lower or "http" in text_lower:
                words = text_lower.split()
                url = next((w for w in words if w.startswith("http")), None)
                if url:
                    with st.spinner("Extracting web domain elements..."):
                        try:
                            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                            html = urllib.request.urlopen(req).read()
                            page_text = ' '.join(BeautifulSoup(html, 'html.parser').get_text().split())
                            st.text_area("🌐 Automated Scraper Output Container", value=f"💡 Data Scrape Result:\n\n\"{page_text[:500]}...\"", height=180)
                        except Exception as e: st.error(f"Web Scraper Connection Fault: {str(e)}")
            elif user_input:
                with st.spinner("Processing deep text reasoning..."):
                    try:
                        response = client.models.generate_content(model='gemini-3.5-flash', contents=user_input)
                        st.text_area("🧠 Deep Text Reasoner Output", value=response.text, height=250)
                    except Exception as e: st.error(f"Reasoning Core Error: {str(e)}")

            # --- OUT 2: MULTIMODAL IMAGE READER ---
            if uploaded_image:
                with st.spinner("Analyzing image array parameters..."):
                    try:
                        image_bytes = uploaded_image.read()
                        prompt_to_use = user_input if user_input else "Describe what you see or read any text inside this photo in complete detail."
                        response = client.models.generate_content(
                            model='gemini-3.5-flash',
                            contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use]
                        )
                        st.text_area("👁️ Multimodal Image Analysis Response", value=response.text, height=200)
                    except Exception as e: st.error(f"Multimodal Vision Pipeline Error: {str(e)}")

            # --- OUT 3: AI IMAGEN GENERATOR ---
            if user_input and not "read" in text_lower and not "http" in text_lower:
                with st.spinner("Engaging neural image generators..."):
                    try:
                        result = client.models.generate_images(
                            model='imagen-3.0-generate-002',
                            prompt=user_input,
                            config=dict(number_of_images=1, output_mime_type="image/jpeg")
                        )
                        for generated_image in result.generated_images:
                            st.image(generated_image.image.image_bytes, caption=f"🎨 High-Fidelity Creative Render: '{user_input}'", use_container_width=True)
                    except Exception as e: st.error(f"Creative Art Engine Notice: {str(e)}")

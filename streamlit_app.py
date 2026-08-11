import streamlit as st, urllib.request, json
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# Configure luxury full-width layout canvas
st.set_page_config(page_title="Nexus", page_icon="✨", layout="centered")

# Visual CSS styling to upgrade the interface UI and inject ALL icons inside the search bar track
st.markdown("""
<style>
.stApp { background-color: #0d0e12; }
h1 { color: #f3f4f6 !important; font-family: 'Inter', sans-serif; text-align: center; font-weight: 700; margin-top: 50px !important; margin-bottom: 25px !important;}

/* HARD-FORCING EVERY CONTROL ONTO 1 SINGLE HORIZONTAL CHAT PILL LINE CONTAINER */
form[data-testid="stForm"] {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    background-color: #1e202a !important;
    border-radius: 35px !important;
    border: 1px solid #2e3244 !important;
    padding: 4px 10px !important;
    gap: 10px !important;
    width: 100% !important;
    position: fixed !important;
    bottom: 20px !important; /* Pins capsule to the absolute bottom row */
    left: 50% !important;
    transform: translateX(-50%) !important;
    max-width: 90% !important;
    z-index: 99999 !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}

/* Forcing all internal element column segments to align on 1 flat row inside the capsule bar */
form[data-testid="stForm"] > div { width: auto !important; padding: 0 !important; margin: 0 !important; display: flex !important; align-items: center !important; }
form[data-testid="stForm"] > div:nth-child(2) { flex-grow: 2 !important; width: 100% !important; }

/* Merging text inputs cleanly inside the search bar container */
div.stTextInput { width: 100% !important; padding: 0 !important; margin: 0 !important; }
div.stTextInput > div > div > input {
    background-color: transparent !important;
    color: white !important;
    border: none !important;
    padding-left: 5px !important;
    height: 44px !important;
    font-size: 15px !important;
    outline: none !important;
}
div.stTextInput > div > div { border: none !important; background-color: transparent !important; box-shadow: none !important; }

/* 1. Turning the upload box into a clean grey circular '+' inside the left side of the search bar */
div[data-testid="stFileUploader"] { max-width: 38px !important; margin: 0 !important; padding: 0 !important; }
div[data-testid="stFileUploaderDropzone"] { padding: 0 !important; background-color: transparent !important; border: none !important; }
div[data-testid="stFileUploaderDropzone"] button {
    background-color: #2e3244 !important;
    color: #9ca3af !important;
    border-radius: 50% !important;
    height: 36px !important;
    width: 36px !important;
    min-width: 36px !important;
    font-size: 20px !important;
    font-weight: bold !important;
    padding: 0 !important;
    padding-bottom: 2px !important;
    border: none !important;
}
div[data-testid="stFileUploaderDropzone"] span, div[data-testid="stFileUploaderDropzone"] div { display: none !important; }

/* 2. Your custom orange circular up arrow send button inside the far right track of the bar */
form[data-testid="stForm"] button[type="submit"] {
    background-color: #d0755d !important;
    color: white !important;
    border-radius: 50% !important;
    height: 36px !important;
    width: 36px !important;
    min-width: 36px !important;
    border: none !important;
    font-size: 16px !important;
    font-weight: bold !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 0 !important;
}
form[data-testid="stForm"] button[type="submit"]:hover { background-color: #be654e !important; }
</style>
""", unsafe_allow_html=True)

if "anonymous_clicks" not in st.session_state: st.session_state["anonymous_clicks"] = 0
if "is_premium" not in st.session_state: st.session_state["is_premium"] = False
if "text_out" not in st.session_state: st.session_state["text_out"] = None

with st.sidebar:
    st.markdown("### 👑 Member Directory")
    if not st.session_state["is_premium"]:
        pass_input = st.text_input("Enter Passcode Key", type="password")
        if pass_input == "premium123": st.session_state["is_premium"] = True; st.rerun()
    else: st.success("👑 Premium Active")

st.title("✨ Nexus")

if not st.session_state["is_premium"] and st.session_state["anonymous_clicks"] >= 3:
    st.error("🛑 Limit Reached. Upgrade to Premium for unlimited access.")
else:
    # DESIGN WORKSPACE MIDDLE OUTPUT VIEW CONTAINERS (Outputs freeze safely above inputs)
    out_holder = st.empty()
    if st.session_state["text_out"]:
        out_holder.markdown(f"### 📊 Outputs\n{st.session_state['text_out']}")

    st.markdown("<br><br>", unsafe_allow_html=True)

    # =========================================================================================
    # 📱 THE COMPACT HORIZONTAL PILL BAR DOCK (Plus, Text Bar, Orange Button ALL COMPRESSED INLINE)
    # ========================================================================================
    with st.form(key="nexus_unbreakable_capsule_bar", clear_on_submit=False):
        # Circular grey '+' button nested natively into the inside left track of the search bar container
        uploaded_image = st.file_uploader("+", type=["png", "jpg", "jpeg"], label_visibility="collapsed")
        
        # Core continuous unbordered text prompt entry field
        user_input = st.text_input("", placeholder="Nexus AI", label_visibility="collapsed")
        
        # Circular orange submit arrow button nested natively into the far right track of the search bar container
        execute_btn = st.form_submit_button(label="↑")

    generate_art_mode = st.checkbox("🎨 Paint AI Art Mode")

    # ==========================================
    # 🧠 BACKEND MULTITASKING ROUTER LOOPS
    # ==========================================
    if execute_btn:
        u_valid = 'uploaded_image' in locals() and uploaded_image is not None
        art_valid = 'generate_art_mode' in locals() and generate_art_mode
        
        if not user_input and not u_valid:
            st.warning("⚠️ Please provide an instruction text string or upload a photo asset.")
        else:
            if not st.session_state["is_premium"]: st.session_state["anonymous_clicks"] += 1
            api_key_str = st.secrets["GEMINI_KEY"]
            client = genai.Client(api_key=api_key_str)
            text_lower = user_input.lower().strip() if user_input else ""
            
            # CORE MODEL LAYER LOCKED TO YOUR PRECISE DIRECTION
            TEXT_MODEL = 'gemini-1.5-flash'
            ART_MODEL = 'imagen-3.0-generate-002'

            if art_valid and user_input:
                try:
                    result = client.models.generate_images(model=ART_MODEL, prompt=user_input, config=dict(number_of_images=1, output_mime_type="image/jpeg"))
                    st.image(result.generated_images.image.image_bytes, use_container_width=True)
                    st.session_state["text_out"] = "✨ Deep creative render pipeline successful!"
                except Exception as e: st.session_state["text_out"] = f"❌ Creative Art Engine Fault: {str(e)}"
            elif "calculate" in text_lower or "math" in text_lower:
                numbers = [int(s) for s in text_lower.split() if s.isdigit()]
                if len(numbers) >= 2: st.session_state["text_out"] = f"💡 Programmatic Compute:\n{numbers} + {numbers} = {numbers + numbers}"
            else:
                try:
                    # NATIVE MULTIMODAL EXTRACTION: Links text prompts and raw image data files cleanly with no network faults
                    if u_valid:
                        image_bytes = uploaded_image.read()
                        prompt_to_use = user_input if user_input else "Describe this image asset in deep detail."
                        response = client.models.generate_content(model=TEXT_MODEL, contents=[types.Part.from_bytes(data=image_bytes, mime_type=uploaded_image.type), prompt_to_use])
                    else:
                        response = client.models.generate_content(model=TEXT_MODEL, contents=user_input)
                    # Saving answer data directly inside global cache states to secure data freezing parameters
                    st.session_state["text_out"] = response.text
                except Exception as e: st.session_state["text_out"] = f"❌ Critical Pipeline Error: {str(e)}"
        st.rerun()

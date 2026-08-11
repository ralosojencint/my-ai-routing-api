import streamlit as st
import requests

# -----------------------------
# NEXUS — AI Assistant
# -----------------------------

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="centered"
)

# -----------------------------
# STYLE
# -----------------------------

st.markdown("""
<style>

.stApp {
    background: #0b0d10;
    color: #f5f5f5;
}

header {
    visibility: hidden;
}

.block-container {
    max-width: 800px;
    padding-top: 40px;
    padding-bottom: 100px;
}

.nexus-title {
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    letter-spacing: -2px;
    margin-bottom: 5px;
}

.nexus-subtitle {
    text-align: center;
    color: #888;
    font-size: 14px;
    margin-bottom: 35px;
}

[data-testid="stChatMessage"] {
    background: transparent;
}

[data-testid="stChatInput"] {
    background: #15181e;
}

button {
    border-radius: 12px !important;
}

</style>
""", unsafe_allow_html=True)

# -----------------------------
# HEADER
# -----------------------------

st.markdown(
    '<div class="nexus-title">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-subtitle">Your intelligent AI assistant</div>',
    unsafe_allow_html=True
)

# -----------------------------
# API KEY
# -----------------------------

try:
    API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    API_KEY = ""

if not API_KEY:
    st.error(
        "NEXUS needs a Groq API key. Add GROQ_API_KEY to Streamlit Secrets."
    )
    st.stop()

# -----------------------------
# MEMORY
# -----------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

# -----------------------------
# DISPLAY CHAT
# -----------------------------

for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# -----------------------------
# AI FUNCTION
# -----------------------------

def ask_nexus(messages):

    url = "https://api.groq.com/openai/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": """
You are NEXUS, a highly capable AI assistant.

Your personality:
- Intelligent
- Clear
- Helpful
- Direct
- Professional
- Friendly

Give useful answers instead of unnecessary filler.

When explaining something:
1. Understand the user's goal.
2. Give the answer clearly.
3. Use steps when helpful.
4. Ask a question only when necessary.

You can help with:
- Programming
- Business
- Writing
- Research
- Ideas
- Learning
- Problem solving
- General questions

Never claim you performed an action that you did not actually perform.
"""
            }
        ] + messages,
        "temperature": 0.7,
        "max_tokens": 2000
    }

    response = requests.post(
        url,
        headers=headers,
        json=data,
        timeout=60
    )

    if response.status_code != 200:
        return f"API error: {response.status_code}\n\n{response.text}"

    result = response.json()

    return result["choices"][0]["message"]["content"]

# -----------------------------
# CHAT INPUT
# -----------------------------

prompt = st.chat_input("Message NEXUS...")

if prompt:

    # Add user message
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate response
    with st.chat_message("assistant"):

        with st.spinner("NEXUS is thinking..."):

            answer = ask_nexus(
                st.session_state.messages
            )

        st.markdown(answer)

    # Save AI response
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

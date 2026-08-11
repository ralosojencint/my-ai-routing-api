import os
import requests
import streamlit as st

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="centered"
)

# -----------------------------
# NEXUS STYLE
# -----------------------------

st.markdown("""
<style>
.stApp {
    background: #090b10;
}

.block-container {
    max-width: 850px;
    padding-top: 35px;
    padding-bottom: 100px;
}

.nexus-title {
    text-align: center;
    font-size: 42px;
    font-weight: 800;
    letter-spacing: 5px;
}

.nexus-subtitle {
    text-align: center;
    color: #777;
    margin-bottom: 35px;
}

[data-testid="stChatInput"] {
    position: fixed;
    bottom: 20px;
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
    '<div class="nexus-subtitle">Simple intelligence. Powerful results.</div>',
    unsafe_allow_html=True
)


# -----------------------------
# API KEY
# -----------------------------

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# -----------------------------
# CHAT MEMORY
# -----------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# -----------------------------
# SIDEBAR
# -----------------------------

with st.sidebar:

    st.title("NEXUS")

    mode = st.selectbox(
        "Mode",
        [
            "General",
            "Coding",
            "Business",
            "Research",
            "Writing"
        ]
    )

    st.divider()

    if st.button(
        "🗑️ New conversation",
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()


# -----------------------------
# AI FUNCTION
# -----------------------------

def ask_nexus(messages):

    if not GROQ_API_KEY:
        return (
            "GROQ_API_KEY is missing.\n\n"
            "Open Streamlit → Manage app → Settings → Secrets "
            "and add your new Groq API key."
        )

    system = {
        "role": "system",
        "content": f"""
You are NEXUS, a powerful AI assistant.

Current mode: {mode}

Be:
- Helpful
- Direct
- Intelligent
- Clear
- Professional

Help with:
- Coding
- AI
- Business
- Research
- Writing
- Learning
- Problem solving

When giving code, give complete usable code
and explain where it should be placed.

Never reveal API keys or secrets.
"""
    }

    chat_messages = [system] + messages[-12:]

    try:

        response = requests.post(

            "https://api.groq.com/openai/v1/chat/completions",

            headers={
                "Authorization":
                    "Bearer " + GROQ_API_KEY,

                "Content-Type":
                    "application/json"
            },

            json={
                "model":
                    "llama-3.3-70b-versatile",

                "messages":
                    chat_messages,

                "temperature":
                    0.6,

                "max_tokens":
                    2500
            },

            timeout=90
        )

        if response.status_code != 200:
            return (
                "NEXUS API error:\n\n"
                + response.text
            )

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as error:

        return (
            "NEXUS connection error:\n\n"
            + str(error)
        )


# -----------------------------
# DISPLAY CHAT
# -----------------------------

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


# -----------------------------
# BOTTOM CHAT INPUT
# -----------------------------

prompt = st.chat_input(
    "Message NEXUS..."
)


if prompt:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):

        with st.spinner(
            "NEXUS is thinking..."
        ):

            answer = ask_nexus(
                st.session_state.messages
            )

        st.markdown(answer)

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

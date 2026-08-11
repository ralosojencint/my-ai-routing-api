import streamlit as st
import requests
import io
from datetime import datetime

# PDF support
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# NEXUS
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="centered"
)


# ============================================================
# SETTINGS
# ============================================================

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"


# ============================================================
# API KEYS
# ============================================================

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except Exception:
    GROQ_API_KEY = ""

try:
    TAVILY_API_KEY = st.secrets["TAVILY_API_KEY"]
except Exception:
    TAVILY_API_KEY = ""


# ============================================================
# STYLE
# ============================================================

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
    max-width: 850px;
    padding-top: 35px;
    padding-bottom: 120px;
}

.nexus-logo {
    text-align: center;
    font-size: 38px;
    font-weight: 800;
    letter-spacing: -1px;
    margin-bottom: 3px;
}

.nexus-subtitle {
    text-align: center;
    color: #777;
    font-size: 13px;
    margin-bottom: 25px;
}

[data-testid="stChatMessage"] {
    background: transparent;
}

[data-testid="stChatInput"] {
    background: #15181e;
}

.stButton button {
    border-radius: 10px;
}

section[data-testid="stSidebar"] {
    background: #101216;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="nexus-logo">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-subtitle">Simple intelligence. Powerful results.</div>',
    unsafe_allow_html=True
)


# ============================================================
# SESSION MEMORY
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "uploaded_context" not in st.session_state:
    st.session_state.uploaded_context = ""

if "web_context" not in st.session_state:
    st.session_state.web_context = ""


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## NEXUS")

    st.caption("AI assistant")

    st.divider()

    if st.button("🗑️ New conversation", use_container_width=True):

        st.session_state.messages = []
        st.session_state.uploaded_context = ""
        st.session_state.web_context = ""

        st.rerun()

    st.divider()

    st.markdown("### Tools")

    web_enabled = st.toggle(
        "🌐 Web search",
        value=False
    )

    st.divider()

    st.markdown("### Files")

    uploaded_file = st.file_uploader(
        "Upload a file",
        type=["txt", "pdf"],
        help="Upload a TXT or PDF and ask NEXUS about it."
    )

    if uploaded_file:

        try:

            if uploaded_file.type == "text/plain":

                text = uploaded_file.read().decode(
                    "utf-8",
                    errors="ignore"
                )

            elif uploaded_file.type == "application/pdf":

                if PdfReader is None:

                    st.error(
                        "PDF support is not installed yet."
                    )

                    text = ""

                else:

                    pdf_bytes = uploaded_file.read()

                    reader = PdfReader(
                        io.BytesIO(pdf_bytes)
                    )

                    pages = []

                    for page in reader.pages:

                        page_text = page.extract_text()

                        if page_text:
                            pages.append(page_text)

                    text = "\n\n".join(pages)

            else:

                text = ""

            # Prevent gigantic prompts
            st.session_state.uploaded_context = text[:50000]

            st.success(
                f"Loaded: {uploaded_file.name}"
            )

        except Exception as e:

            st.error(
                f"Could not read file: {e}"
            )

    if st.session_state.uploaded_context:

        st.caption(
            f"{len(st.session_state.uploaded_context):,} characters loaded"
        )

    st.divider()

    st.markdown("### Export")

    if st.session_state.messages:

        conversation_text = ""

        for message in st.session_state.messages:

            role = message["role"].upper()

            conversation_text += (
                f"{role}:\n"
                f"{message['content']}\n\n"
            )

        st.download_button(
            "📥 Download chat",
            conversation_text,
            file_name="nexus_conversation.txt",
            mime="text/plain",
            use_container_width=True
        )


# ============================================================
# API CHECK
# ============================================================

if not GROQ_API_KEY:

    st.warning(
        "NEXUS needs a GROQ_API_KEY. "
        "Add it under Streamlit Secrets."
    )

    st.stop()


# ============================================================
# WEB SEARCH
# ============================================================

def web_search(query):

    if not TAVILY_API_KEY:

        return (
            "Web search is enabled but no "
            "TAVILY_API_KEY is configured."
        )

    try:

        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 5
            },
            timeout=30
        )

        if response.status_code != 200:

            return "Web search failed."

        data = response.json()

        results = []

        for result in data.get("results", []):

            title = result.get("title", "")
            content = result.get("content", "")
            url = result.get("url", "")

            results.append(
                f"TITLE: {title}\n"
                f"URL: {url}\n"
                f"CONTENT: {content}"
            )

        return "\n\n".join(results)

    except Exception as e:

        return f"Web search error: {e}"


# ============================================================
# AI
# ============================================================

def ask_nexus(messages, file_context="", web_context=""):

    system_prompt = """
You are NEXUS, a powerful general-purpose AI assistant.

Your personality:
- Intelligent
- Clear
- Direct
- Helpful
- Calm
- Professional

Your priorities:
1. Give accurate and useful answers.
2. Understand the user's actual goal.
3. Avoid unnecessary filler.
4. Explain complicated things simply.
5. Use step-by-step instructions when appropriate.
6. When writing code, provide complete usable code.
7. Never pretend you performed an action that you did not perform.

You can help with:
- Programming
- Software development
- AI
- Business
- Entrepreneurship
- Writing
- Research
- Learning
- Mathematics
- Planning
- Problem solving
- Creative ideas

If the user asks for code:
- Give working code.
- Explain where it goes.
- Mention dependencies when necessary.

If web research is provided:
- Use the provided information.
- Do not invent sources.
"""

    if file_context:

        system_prompt += """

The user uploaded a document.

Use the document below as context when answering questions about it.

DOCUMENT:
""" + file_context

    if web_context:

        system_prompt += """

WEB SEARCH RESULTS:

""" + web_context

    payload = {

        "model": MODEL,

        "messages": [
            {
                "role": "system",
                "content": system_prompt
            }
        ] + messages,

        "temperature": 0.6,

        "max_tokens": 4000
    }

    headers = {

        "Authorization":
            f"Bearer {GROQ_API_KEY}",

        "Content-Type":
            "application/json"
    }

    try:

        response = requests.post(
            GROQ_URL,
            headers=headers,
            json=payload,
            timeout=90
        )

        if response.status_code != 200:

            return (
                "NEXUS API error:\n\n"
                f"{response.status_code}\n\n"
                f"{response.text}"
            )

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except requests.exceptions.Timeout:

        return (
            "NEXUS took too long to respond. "
            "Please try again."
        )

    except Exception as e:

        return f"NEXUS error: {e}"


# ============================================================
# DISPLAY CHAT
# ============================================================

for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(
            message["content"]
        )


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Message NEXUS..."
)


if prompt:

    # Add user message

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt
        }
    )

    with st.chat_message("user"):

        st.markdown(prompt)


    # Web search

    web_context = ""

    if web_enabled:

        with st.spinner("Searching the web..."):

            web_context = web_search(prompt)

        st.session_state.web_context = web_context


    # AI response

    with st.chat_message("assistant"):

        with st.spinner("NEXUS is thinking..."):

            answer = ask_nexus(
                st.session_state.messages,
                st.session_state.uploaded_context,
                web_context
            )

        st.markdown(answer)


    # Save response

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

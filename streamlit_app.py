import asyncio
import json
import os
import re
import time
from pathlib import Path

import streamlit as st
from google import genai

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None


# ============================================================
# NEXUS
# ============================================================

APP_NAME = "NEXUS"
APP_VERSION = "7.0"

MAX_HISTORY = 12
MAX_FILE_MB = 25


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "messages": [],
    "request_count": 0,
    "selected_model": None,
    "uploaded_files": [],
    "memory": "",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SECRETS
# ============================================================

def get_secret(name):
    value = os.getenv(name, "").strip()

    if value:
        return value

    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")


# ============================================================
# GEMINI
# ============================================================

@st.cache_resource(show_spinner=False)
def get_client():
    if not GEMINI_API_KEY:
        return None

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def find_model():
    if st.session_state.selected_model:
        return st.session_state.selected_model

    client = get_client()

    if client is None:
        return None

    preferred = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.6-flash",
    ]

    try:
        models = list(client.models.list())

        available = []

        for model in models:
            name = getattr(model, "name", "")

            if name:
                name = name.replace(
                    "models/",
                    ""
                )

                available.append(name)

        # Preferred models first
        for candidate in preferred:
            if candidate in available:
                st.session_state.selected_model = candidate
                return candidate

        # Generic Gemini fallback
        for name in available:
            lower = name.lower()

            if (
                "gemini" in lower
                and "embedding" not in lower
                and "image" not in lower
                and "tts" not in lower
                and "live" not in lower
            ):
                st.session_state.selected_model = name
                return name

    except Exception:
        pass

    return None


# ============================================================
# FILE EXTRACTION
# ============================================================

def read_pdf(uploaded_file):
    if PdfReader is None:
        return "PDF support requires pypdf."

    reader = PdfReader(uploaded_file)

    pages = []

    for page in reader.pages:
        try:
            pages.append(
                page.extract_text() or ""
            )
        except Exception:
            pass

    return "\n\n".join(pages)


def read_text(uploaded_file):
    raw = uploaded_file.getvalue()

    try:
        return raw.decode("utf-8")
    except Exception:
        return raw.decode(
            "latin-1",
            errors="replace"
        )


def file_to_text(uploaded_file):
    extension = Path(
        uploaded_file.name
    ).suffix.lower()

    if extension == ".pdf":
        return read_pdf(uploaded_file)

    if extension in [".txt", ".md"]:
        return read_text(uploaded_file)

    if extension == ".csv":
        return read_text(uploaded_file)

    return ""


# ============================================================
# TAVILY
# ============================================================

@st.cache_resource(show_spinner=False)
def get_tavily():
    if not TAVILY_API_KEY:
        return None

    if TavilyClient is None:
        return None

    return TavilyClient(
        api_key=TAVILY_API_KEY
    )


async def web_search(query):

    client = get_tavily()

    if client is None:
        return []

    try:
        result = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="basic",
            max_results=5,
            include_answer=True
        )

        return result.get(
            "results",
            []
        )

    except Exception:
        return []


# ============================================================
# SIMPLE ROUTING
# ============================================================

def needs_web(query):

    keywords = [
        "current",
        "today",
        "latest",
        "recent",
        "news",
        "price",
        "bitcoin",
        "stock",
        "weather",
        "live",
        "2026",
    ]

    text = query.lower()

    return any(
        word in text
        for word in keywords
    )


# ============================================================
# GEMINI RESPONSE
# ============================================================

async def ask_nexus(query):

    client = get_client()

    if client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    model = find_model()

    if not model:
        raise RuntimeError(
            "No compatible Gemini model was found."
        )

    # --------------------------------------------------------
    # Conversation
    # --------------------------------------------------------

    history = []

    for message in st.session_state.messages[
        -MAX_HISTORY:
    ]:

        history.append(
            f"{message['role'].upper()}: "
            f"{message['content']}"
        )

    conversation = "\n".join(history)

    # --------------------------------------------------------
    # Uploaded files
    # --------------------------------------------------------

    file_context = []

    image_parts = []

    for uploaded in st.session_state.uploaded_files:

        extension = Path(
            uploaded.name
        ).suffix.lower()

        if extension in [
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        ]:

            image_parts.append(
                uploaded
            )

        else:

            text = file_to_text(
                uploaded
            )

            if text:

                file_context.append(
                    f"""
FILE: {uploaded.name}

{text[:20000]}
"""
                )

    # --------------------------------------------------------
    # Web
    # --------------------------------------------------------

    research_context = ""

    if needs_web(query):

        results = await web_search(
            query
        )

        if results:

            research_context = "\n\n".join(
                f"""
SOURCE: {item.get('title', '')}
URL: {item.get('url', '')}

{item.get('content', '')}
"""
                for item in results
            )

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are NEXUS, an AI assistant for research,
analysis, reasoning, documents, and images.

Answer the user's request directly.

USER:
{query}

PREVIOUS CONVERSATION:
{conversation}

UPLOADED FILES:
{"".join(file_context)}

WEB RESEARCH:
{research_context}

Rules:

- Be accurate.
- Do not invent information.
- If the user uploads an image, analyze it.
- If the user uploads a PDF or text document, use it.
- If web research is supplied, use it when relevant.
- Keep answers clear and useful.
"""

    contents = [prompt]

    # Add images directly to Gemini
    for image in image_parts:
        try:
            contents.append(
                genai.types.Part.from_bytes(
                    data=image.getvalue(),
                    mime_type=image.type
                )
            )
        except Exception:
            pass

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=contents
    )

    return response.text or "I couldn't generate a response."


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

/* DO NOT HIDE STREAMLIT HEADER */

#MainMenu {
    visibility: hidden;
}

/* MAIN */

.block-container {
    max-width: 1050px;
    padding-top: 2rem;
    padding-bottom: 7rem;
}

/* NEXUS BRAND */

.nexus-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 28px;
}

.nexus-logo {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
}

.nexus-sub {
    color: #888;
    font-size: 13px;
    margin-top: 3px;
}

/* MODEL */

.model-pill {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 999px;
    padding: 7px 12px;
    font-size: 12px;
    color: #888;
}

/* CHAT */

[data-testid="stChatMessage"] {
    padding-top: 1rem;
    padding-bottom: 1rem;
}

[data-testid="stChatMessageContent"] {
    font-size: 15px;
    line-height: 1.7;
}

/* CHAT INPUT */

[data-testid="stChatInput"] {
    border-radius: 18px;
}

/* FILE UPLOADER */

[data-testid="stFileUploader"] {
    border: 1px solid rgba(128,128,128,.2);
    border-radius: 14px;
    padding: 8px;
}

/* STATUS */

.status-card {
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 14px;
    padding: 14px;
}

.status-label {
    font-size: 10px;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.status-value {
    font-size: 14px;
    font-weight: 600;
    margin-top: 5px;
}

/* MOBILE */

@media (max-width: 700px) {

    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1rem;
    }

    .nexus-logo {
        font-size: 26px;
    }

}

</style>
""",
    unsafe_allow_html=True
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### ✦ NEXUS"
    )

    st.caption(
        "Agentic workspace"
    )

    st.divider()

    if st.button(
        "＋ New conversation",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.session_state.request_count = 0
        st.rerun()

    st.divider()

    st.markdown("### System")

    model = find_model()

    if model:

        st.success(
            f"Gemini connected\n\n`{model}`"
        )

    else:

        st.error(
            "Gemini not connected"
        )

    if TAVILY_API_KEY:

        st.success(
            "Web research available"
        )

    else:

        st.info(
            "Web research unavailable"
        )

    st.divider()

    # --------------------------------------------------------
    # ATTACHMENTS
    # --------------------------------------------------------

    st.markdown("### 📎 Attach files")

    uploaded_files = st.file_uploader(
        "Upload images, PDFs, TXT or CSV files",
        type=[
            "png",
            "jpg",
            "jpeg",
            "webp",
            "pdf",
            "txt",
            "md",
            "csv"
        ],
        accept_multiple_files=True
    )

    if uploaded_files:

        valid_files = []

        for file in uploaded_files:

            size_mb = (
                file.size
                / 1024
                / 1024
            )

            if size_mb <= MAX_FILE_MB:

                valid_files.append(file)

            else:

                st.warning(
                    f"{file.name} is over "
                    f"{MAX_FILE_MB} MB."
                )

        st.session_state.uploaded_files = (
            valid_files
        )

    if st.session_state.uploaded_files:

        st.caption(
            f"{len(st.session_state.uploaded_files)} "
            "file(s) attached"
        )

        for file in st.session_state.uploaded_files:

            st.write(
                f"📄 {file.name}"
            )

        if st.button(
            "Clear attachments",
            use_container_width=True
        ):

            st.session_state.uploaded_files = []

            st.rerun()

    st.divider()

    st.markdown("### Statistics")

    st.metric(
        "Requests",
        st.session_state.request_count
    )

    st.metric(
        "Attachments",
        len(
            st.session_state.uploaded_files
        )
    )


# ============================================================
# MAIN HEADER
# ============================================================

model_name = (
    st.session_state.selected_model
    or "Auto"
)

st.markdown(
    f"""
<div class="nexus-header">

    <div>
        <div class="nexus-logo">
            ✦ NEXUS
        </div>

        <div class="nexus-sub">
            Agentic workspace
        </div>
    </div>

    <div class="model-pill">
        {model_name}
    </div>

</div>
""",
    unsafe_allow_html=True
)


# ============================================================
# STATUS ROW
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:

    st.markdown(
        f"""
<div class="status-card">
    <div class="status-label">
        Model
    </div>

    <div class="status-value">
        {model_name}
    </div>
</div>
""",
        unsafe_allow_html=True
    )

with col2:

    st.markdown(
        f"""
<div class="status-card">
    <div class="status-label">
        Attachments
    </div>

    <div class="status-value">
        {len(st.session_state.uploaded_files)} files
    </div>
</div>
""",
        unsafe_allow_html=True
    )

with col3:

    st.markdown(
        f"""
<div class="status-card">
    <div class="status-label">
        Requests
    </div>

    <div class="status-value">
        {st.session_state.request_count}
    </div>
</div>
""",
        unsafe_allow_html=True
    )


st.write("")


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


# ============================================================
# ATTACHED FILE PREVIEW
# ============================================================

if st.session_state.uploaded_files:

    with st.expander(
        "📎 Attached files",
        expanded=False
    ):

        for file in st.session_state.uploaded_files:

            extension = Path(
                file.name
            ).suffix.lower()

            if extension in [
                ".png",
                ".jpg",
                ".jpeg",
                ".webp"
            ]:

                st.image(
                    file,
                    caption=file.name,
                    use_container_width=True
                )

            else:

                st.write(
                    f"📄 {file.name}"
                )


# ============================================================
# CHAT INPUT
# ============================================================

query = st.chat_input(
    "Message NEXUS..."
)


# ============================================================
# SEND
# ============================================================

if query:

    if not GEMINI_API_KEY:

        st.error(
            "GEMINI_API_KEY is missing. "
            "Add it to Streamlit Secrets."
        )

        st.stop()

    # User message
    st.session_state.messages.append(
        {
            "role": "user",
            "content": query
        }
    )

    with st.chat_message("user"):

        st.markdown(query)

        if st.session_state.uploaded_files:

            st.caption(
                "📎 "
                + ", ".join(
                    file.name
                    for file
                    in st.session_state.uploaded_files
                )
            )

    # Assistant
    with st.chat_message("assistant"):

        with st.spinner(
            "NEXUS is thinking..."
        ):

            try:

                answer = asyncio.run(
                    ask_nexus(query)
                )

                st.markdown(
                    answer
                )

            except Exception as exc:

                answer = (
                    f"Request failed\n\n"
                    f"`{type(exc).__name__}: "
                    f"{exc}`"
                )

                st.error(
                    answer
                )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    st.session_state.request_count += 1

    st.rerun()

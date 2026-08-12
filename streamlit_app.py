import asyncio
import os
from pathlib import Path

import streamlit as st
from google import genai

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
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "attachments" not in st.session_state:
    st.session_state.attachments = []

if "request_count" not in st.session_state:
    st.session_state.request_count = 0

if "selected_model" not in st.session_state:
    st.session_state.selected_model = None


# ============================================================
# SECRETS
# ============================================================

def get_secret(name):

    value = os.getenv(name, "").strip()

    if value:
        return value

    try:
        return str(
            st.secrets.get(name, "")
        ).strip()
    except Exception:
        return ""


GEMINI_API_KEY = get_secret(
    "GEMINI_API_KEY"
)


# ============================================================
# GEMINI
# ============================================================

@st.cache_resource
def get_client():

    if not GEMINI_API_KEY:
        return None

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def get_model():

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

        models = list(
            client.models.list()
        )

        available = []

        for model in models:

            name = getattr(
                model,
                "name",
                ""
            )

            if name:

                name = name.replace(
                    "models/",
                    ""
                )

                available.append(name)

        for candidate in preferred:

            if candidate in available:

                st.session_state.selected_model = candidate

                return candidate

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
# FILE READING
# ============================================================

def read_pdf(file):

    if PdfReader is None:
        return "PDF reader is not installed."

    reader = PdfReader(file)

    pages = []

    for page in reader.pages:

        try:

            pages.append(
                page.extract_text() or ""
            )

        except Exception:
            pass

    return "\n\n".join(pages)


def read_text(file):

    raw = file.getvalue()

    try:
        return raw.decode("utf-8")

    except Exception:

        return raw.decode(
            "latin-1",
            errors="replace"
        )


def get_file_text(file):

    extension = Path(
        file.name
    ).suffix.lower()

    if extension == ".pdf":

        return read_pdf(file)

    if extension in [
        ".txt",
        ".md",
        ".csv"
    ]:

        return read_text(file)

    return ""


# ============================================================
# GEMINI
# ============================================================

async def ask_nexus(
    query,
    files
):

    client = get_client()

    if client is None:

        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    model = get_model()

    if not model:

        raise RuntimeError(
            "No Gemini model is available."
        )

    previous = []

    for message in st.session_state.messages[-10:]:

        previous.append(
            f"{message['role']}: "
            f"{message['content']}"
        )

    history = "\n".join(previous)

    text_files = []
    image_files = []

    for file in files:

        extension = Path(
            file.name
        ).suffix.lower()

        if extension in [
            ".png",
            ".jpg",
            ".jpeg",
            ".webp"
        ]:

            image_files.append(file)

        else:

            text = get_file_text(file)

            if text:

                text_files.append(
                    f"""
FILE: {file.name}

{text[:20000]}
"""
                )

    prompt = f"""
You are NEXUS, an AI assistant.

Answer the user's request clearly and directly.

USER:
{query}

CONVERSATION:
{history}

UPLOADED DOCUMENTS:
{"".join(text_files)}

If an image is attached, analyze the image
and answer questions about it.

Do not invent information.
"""

    contents = [prompt]

    for image in image_files:

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

    return (
        response.text
        or "No response was generated."
    )


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
<style>

/* ----------------------------------------------------------
   GENERAL
---------------------------------------------------------- */

#MainMenu {
    visibility: hidden;
}

.block-container {
    max-width: 1050px;
    padding-top: 2rem;
    padding-bottom: 8rem;
}

/* ----------------------------------------------------------
   HEADER
---------------------------------------------------------- */

.nexus-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 35px;
}

.nexus-logo {
    font-size: 31px;
    font-weight: 800;
    letter-spacing: -1px;
}

.nexus-sub {
    color: #888;
    font-size: 13px;
    margin-top: 3px;
}

.model-pill {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 999px;
    padding: 7px 13px;
    font-size: 12px;
    color: #888;
}

/* ----------------------------------------------------------
   HERO
---------------------------------------------------------- */

.hero {
    text-align: center;
    margin-top: 100px;
    margin-bottom: 35px;
}

.hero-icon {
    font-size: 42px;
    margin-bottom: 15px;
}

.hero-title {
    font-size: 34px;
    font-weight: 750;
    letter-spacing: -1px;
}

.hero-text {
    color: #888;
    font-size: 15px;
    margin-top: 10px;
}

/* ----------------------------------------------------------
   CHAT
---------------------------------------------------------- */

[data-testid="stChatMessage"] {
    padding-top: 12px;
    padding-bottom: 12px;
}

[data-testid="stChatMessageContent"] {
    font-size: 15px;
    line-height: 1.7;
}

/* ----------------------------------------------------------
   CUSTOM COMPOSER
---------------------------------------------------------- */

.nexus-composer {
    position: fixed;
    bottom: 18px;
    left: 50%;
    transform: translateX(-50%);
    width: min(900px, calc(100% - 30px));

    background: rgba(20,20,20,.96);

    border: 1px solid rgba(255,255,255,.13);

    border-radius: 20px;

    padding: 8px;

    box-shadow:
        0 10px 40px rgba(0,0,0,.35);

    z-index: 999;
}

/* File button */

.nexus-attach {
    display: inline-flex;
    align-items: center;
    justify-content: center;

    width: 42px;
    height: 42px;

    border-radius: 13px;

    background: rgba(255,255,255,.07);

    font-size: 20px;
}

/* Hide default uploader label */

.nexus-upload-label {
    font-size: 11px;
    color: #777;
    margin-top: 3px;
}

/* Mobile */

@media (max-width: 700px) {

    .block-container {
        padding-left: 12px;
        padding-right: 12px;
    }

    .nexus-header {
        margin-bottom: 20px;
    }

    .nexus-logo {
        font-size: 27px;
    }

    .hero {
        margin-top: 60px;
    }

    .hero-title {
        font-size: 28px;
    }

    .nexus-composer {
        width: calc(100% - 16px);
        bottom: 8px;
    }

}

</style>
""",
    unsafe_allow_html=True
)


# ============================================================
# HEADER
# ============================================================

model_name = (
    st.session_state.selected_model
    or get_model()
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
# HERO
# ============================================================

if not st.session_state.messages:

    st.markdown(
        """
<div class="hero">

    <div class="hero-icon">
        ✦
    </div>

    <div class="hero-title">
        How can I help?
    </div>

    <div class="hero-text">
        Research, analyze, reason, and work
        with your knowledge using NEXUS.
    </div>

</div>
""",
        unsafe_allow_html=True
    )


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
# CUSTOM COMPOSER
# ============================================================

st.markdown(
    '<div class="nexus-composer">',
    unsafe_allow_html=True
)

# ------------------------------------------------------------
# ATTACHMENT
# ------------------------------------------------------------

upload_col, input_col, send_col = st.columns(
    [0.8, 7, 1.2],
    vertical_alignment="bottom"
)

with upload_col:

    uploaded = st.file_uploader(
        "📎",
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
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="nexus_file_upload"
    )

with input_col:

    query = st.text_input(
        "Message NEXUS...",
        label_visibility="collapsed",
        key="nexus_message"
    )

with send_col:

    send = st.button(
        "➤",
        use_container_width=True,
        key="nexus_send"
    )

st.markdown(
    "</div>",
    unsafe_allow_html=True
)


# ============================================================
# PROCESS ATTACHMENTS
# ============================================================

if uploaded:

    st.session_state.attachments = uploaded


# ============================================================
# SHOW ATTACHED FILES
# ============================================================

if st.session_state.attachments:

    with st.expander(
        "📎 Attached files",
        expanded=False
    ):

        for file in st.session_state.attachments:

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

        if st.button(
            "Clear attachments"
        ):

            st.session_state.attachments = []

            st.rerun()


# ============================================================
# SEND MESSAGE
# ============================================================

if send and query.strip():

    if not GEMINI_API_KEY:

        st.error(
            "GEMINI_API_KEY is missing."
        )

        st.stop()

    clean_query = query.strip()

    files = list(
        st.session_state.attachments
    )

    # --------------------------------------------------------
    # USER MESSAGE
    # --------------------------------------------------------

    st.session_state.messages.append(
        {
            "role": "user",
            "content": clean_query
        }
    )

    with st.chat_message("user"):

        st.markdown(
            clean_query
        )

        if files:

            st.caption(
                "📎 "
                + ", ".join(
                    file.name
                    for file in files
                )
            )

    # --------------------------------------------------------
    # ASSISTANT
    # --------------------------------------------------------

    with st.chat_message("assistant"):

        with st.spinner(
            "NEXUS is thinking..."
        ):

            try:

                answer = asyncio.run(
                    ask_nexus(
                        clean_query,
                        files
                    )
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

    # Clear input attachments after send
    st.session_state.attachments = []

    st.rerun()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## ✦ NEXUS"
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

        st.session_state.attachments = []

        st.rerun()

    st.divider()

    st.markdown(
        "### System"
    )

    if GEMINI_API_KEY:

        st.success(
            "Gemini connected"
        )

        st.caption(
            model_name
        )

    else:

        st.error(
            "Gemini API key missing"
        )

    st.divider()

    st.markdown(
        "### Requests"
    )

    st.metric(
        "Total",
        st.session_state.request_count
    )

    st.divider()

    st.caption(
        f"NEXUS v7.0"
    )

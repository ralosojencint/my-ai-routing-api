import asyncio
import json
import os
import re
import time
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# NEXUS
# ============================================================

APP_NAME = "NEXUS"
APP_VERSION = "7.0"

MAX_FILE_MB = 25
MAX_HISTORY = 12
MAX_CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
MAX_WEB_RESULTS = 5


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "messages": [],
    "documents": [],
    "csv_datasets": [],
    "sources": [],
    "agent_log": [],
    "request_count": 0,
    "selected_model": None,
    "memory_summary": "",
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
# CLIENTS
# ============================================================

@st.cache_resource(show_spinner=False)
def get_gemini_client():

    if not GEMINI_API_KEY:
        return None

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


@st.cache_resource(show_spinner=False)
def get_tavily_client():

    if not TAVILY_API_KEY:
        return None

    if TavilyClient is None:
        return None

    return TavilyClient(
        api_key=TAVILY_API_KEY
    )


# ============================================================
# MODEL
# ============================================================

def discover_model():

    if st.session_state.selected_model:
        return st.session_state.selected_model

    client = get_gemini_client()

    if client is None:
        return None

    preferred = [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
    ]

    try:

        models = client.models.list()

        available = []

        for model in models:

            name = getattr(
                model,
                "name",
                ""
            )

            if not name:
                continue

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

            low = name.lower()

            if (
                "gemini" in low
                and "embedding" not in low
                and "image" not in low
                and "tts" not in low
                and "live" not in low
            ):

                st.session_state.selected_model = name

                return name

    except Exception:
        pass

    return None


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize(text):

    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def truncate(text, limit):

    if not text:
        return ""

    if len(text) <= limit:
        return text

    return (
        text[:limit]
        + "\n...[truncated]"
    )


# ============================================================
# DOCUMENTS
# ============================================================

def extract_txt(file):

    raw = file.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(
            "latin-1",
            errors="replace"
        )


def extract_pdf(file):

    if PdfReader is None:
        raise RuntimeError(
            "pypdf is not installed."
        )

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


def extract_csv(file):

    df = pd.read_csv(file)

    preview = df.head(50).to_csv(
        index=False
    )

    text = f"""
CSV FILE: {file.name}

ROWS: {len(df)}

COLUMNS:
{", ".join(map(str, df.columns))}

PREVIEW:
{preview}
"""

    return text, df


def chunk_text(text):

    text = normalize(text)

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + MAX_CHUNK_SIZE,
            len(text)
        )

        chunk = text[start:end]

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(
            0,
            end - CHUNK_OVERLAP
        )

    return chunks


def index_document(
    filename,
    file_type,
    text
):

    for index, chunk in enumerate(
        chunk_text(text)
    ):

        st.session_state.documents.append(
            {
                "filename": filename,
                "type": file_type,
                "chunk": index,
                "text": chunk,
            }
        )


def search_documents(query):

    if not st.session_state.documents:
        return ""

    query_words = set(
        re.findall(
            r"[a-zA-Z0-9]+",
            query.lower()
        )
    )

    scored = []

    for doc in st.session_state.documents:

        text_words = re.findall(
            r"[a-zA-Z0-9]+",
            doc["text"].lower()
        )

        score = sum(
            text_words.count(word)
            for word in query_words
        )

        if score > 0:

            scored.append(
                (
                    score,
                    doc
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    selected = [
        item[1]
        for item in scored[:5]
    ]

    if not selected:
        return ""

    result = []

    for doc in selected:

        result.append(
            f"""
SOURCE FILE: {doc["filename"]}
CHUNK: {doc["chunk"]}

{doc["text"]}
"""
        )

    return truncate(
        "\n".join(result),
        18000
    )


# ============================================================
# WEB RESEARCH
# ============================================================

async def web_search(query):

    client = get_tavily_client()

    if client is None:
        return []

    try:

        result = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="basic",
            max_results=MAX_WEB_RESULTS,
            include_answer=True,
        )

        return result.get(
            "results",
            []
        )

    except Exception:
        return []


def should_search_web(query):

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
        "this week",
    ]

    query = query.lower()

    return any(
        word in query
        for word in keywords
    )


# ============================================================
# SAFETY
# ============================================================

def safety_check(query):

    blocked = [
        "make a bomb",
        "build a bomb",
        "steal password",
        "credential theft",
        "ransomware",
        "keylogger",
    ]

    query = query.lower()

    for item in blocked:

        if item in query:

            return False

    return True


# ============================================================
# AI
# ============================================================

async def ask_nexus(
    query,
    local_context="",
    web_results=None
):

    client = get_gemini_client()

    if client is None:

        raise RuntimeError(
            "GEMINI_API_KEY is missing."
        )

    model = discover_model()

    if not model:

        raise RuntimeError(
            "No Gemini model is available."
        )

    web_context = ""

    if web_results:

        parts = []

        for source in web_results:

            parts.append(
                f"""
TITLE:
{source.get("title", "")}

URL:
{source.get("url", "")}

CONTENT:
{source.get("content", "")}
"""
            )

        web_context = truncate(
            "\n".join(parts),
            18000
        )

    history = ""

    for message in st.session_state.messages[-MAX_HISTORY:]:

        history += (
            f'{message["role"].upper()}: '
            f'{message["content"]}\n'
        )

    prompt = f"""
You are NEXUS, a modern AI assistant for research,
analysis, reasoning, and productivity.

Answer the user's question clearly and naturally.

USER:
{query}

LOCAL KNOWLEDGE:
{local_context}

WEB RESEARCH:
{web_context}

RECENT CONVERSATION:
{history}

Rules:

- Answer directly.
- Be accurate.
- Do not invent facts.
- If web information is provided, use it when relevant.
- If information is uncertain, say so.
- For calculations, show the calculation clearly.
- Do not mention internal routing or implementation details.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt
    )

    return response.text or ""


# ============================================================
# MAIN NEXUS RUNNER
# ============================================================

async def run_nexus(query):

    start = time.perf_counter()

    st.session_state.agent_log = []

    if not safety_check(query):

        return {
            "answer":
                "I can't help with instructions "
                "that facilitate harmful activity.",
            "sources": [],
            "latency":
                time.perf_counter() - start,
        }

    st.session_state.agent_log.append(
        "Safety check"
    )

    local_context = search_documents(
        query
    )

    if local_context:

        st.session_state.agent_log.append(
            "Knowledge search"
        )

    web_results = []

    if (
        TAVILY_API_KEY
        and should_search_web(query)
    ):

        web_results = await web_search(
            query
        )

        if web_results:

            st.session_state.agent_log.append(
                "Web research"
            )

    answer = await ask_nexus(
        query,
        local_context,
        web_results
    )

    st.session_state.agent_log.append(
        "Reasoning complete"
    )

    return {
        "answer": answer,
        "sources": web_results,
        "latency":
            time.perf_counter() - start,
    }


# ============================================================
# CSS — NEW UI
# ============================================================

st.markdown(
    """
<style>

html, body, [class*="css"] {
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

/* REMOVE STREAMLIT CHROME */

#MainMenu {
    visibility: hidden;
}

header {
    visibility: hidden;
}

footer {
    visibility: hidden;
}


/* PAGE */

.block-container {

    max-width: 1050px;

    padding-top: 1.5rem;
    padding-bottom: 8rem;
}


/* SIDEBAR */

section[data-testid="stSidebar"] {

    background: rgba(15,15,18,.96);

    border-right:
        1px solid rgba(255,255,255,.07);
}


/* TOP BAR */

.nexus-top {

    display: flex;

    align-items: center;

    justify-content: space-between;

    margin-bottom: 20px;
}


.nexus-logo {

    font-size: 20px;

    font-weight: 800;

    letter-spacing: -0.8px;
}


.nexus-sub {

    color: #777;

    font-size: 12px;

    margin-top: 2px;
}


.model-pill {

    border:
        1px solid rgba(255,255,255,.10);

    background:
        rgba(255,255,255,.035);

    border-radius: 999px;

    padding:
        7px 12px;

    font-size: 11px;

    color: #aaa;
}


/* HERO */

.hero {

    text-align: center;

    padding:
        15vh 10px 8vh;
}


.hero-icon {

    width: 58px;

    height: 58px;

    border-radius: 18px;

    display: inline-flex;

    align-items: center;

    justify-content: center;

    font-size: 26px;

    background:
        linear-gradient(
            135deg,
            #202027,
            #111116
        );

    border:
        1px solid rgba(255,255,255,.10);

    box-shadow:
        0 15px 50px
        rgba(0,0,0,.25);

    margin-bottom: 22px;
}


.hero-title {

    font-size: 42px;

    font-weight: 750;

    letter-spacing: -2px;

    margin-bottom: 8px;
}


.hero-text {

    color: #777;

    font-size: 15px;

    max-width: 520px;

    margin:
        0 auto;
}


/* SUGGESTIONS */

.suggestion {

    border:
        1px solid rgba(255,255,255,.08);

    background:
        rgba(255,255,255,.025);

    border-radius: 15px;

    padding: 14px;

    color: #aaa;

    font-size: 13px;

    transition: .2s;
}


.suggestion:hover {

    background:
        rgba(255,255,255,.05);

    border-color:
        rgba(255,255,255,.15);
}


/* CHAT */

[data-testid="stChatMessage"] {

    padding-top: 1.1rem;

    padding-bottom: 1.1rem;

}


[data-testid="stChatMessageContent"] {

    font-size: 15px;

    line-height: 1.7;

}


/* HIDE AVATARS */

[data-testid="stChatMessageAvatar"] {

    display: none;
}


/* INPUT */

[data-testid="stChatInput"] {

    border-radius: 20px !important;

}


[data-testid="stChatInput"] textarea {

    font-size: 15px !important;
}


/* ACTIVITY */

.activity-box {

    border:
        1px solid rgba(255,255,255,.07);

    border-radius: 14px;

    padding: 12px 15px;

    background:
        rgba(255,255,255,.025);

    color: #999;

    font-size: 12px;

}


/* SOURCE */

.source-card {

    padding: 12px 14px;

    margin:
        7px 0;

    border-radius: 12px;

    background:
        rgba(255,255,255,.025);

    border:
        1px solid rgba(255,255,255,.07);
}


.source-title {

    font-size: 13px;

    font-weight: 600;
}


.source-url {

    font-size: 10px;

    color: #666;

    overflow-wrap: anywhere;

    margin-top: 3px;
}


/* SIDEBAR BUTTONS */

.stButton > button {

    border-radius: 12px;

    min-height: 40px;
}


/* MOBILE */

@media(max-width:700px) {

    .hero {

        padding:
            10vh 10px 5vh;
    }

    .hero-title {

        font-size: 32px;
    }

    .block-container {

        padding-left: 14px;

        padding-right: 14px;
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
        "AI workspace"
    )

    st.divider()

    if st.button(
        "＋ New conversation",
        use_container_width=True
    ):

        st.session_state.messages = []

        st.session_state.agent_log = []

        st.session_state.sources = []

        st.rerun()

    st.divider()

    st.markdown(
        "**System**"
    )

    model = discover_model()

    if model:

        st.success(
            f"Gemini · {model}"
        )

    else:

        st.error(
            "Gemini not connected"
        )

    if TAVILY_API_KEY:

        st.success(
            "Web research · Available"
        )

    else:

        st.warning(
            "Web research · Unavailable"
        )

    st.divider()

    st.markdown(
        "**Knowledge**"
    )

    uploads = st.file_uploader(
        "Upload files",
        type=[
            "pdf",
            "txt",
            "csv"
        ],
        accept_multiple_files=True
    )

    if uploads:

        existing = {
            doc["filename"]
            for doc
            in st.session_state.documents
        }

        for uploaded in uploads:

            if uploaded.name in existing:
                continue

            if (
                uploaded.size
                > MAX_FILE_MB * 1024 * 1024
            ):

                st.warning(
                    f"{uploaded.name} is too large."
                )

                continue

            try:

                extension = (
                    Path(
                        uploaded.name
                    ).suffix.lower()
                )

                if extension == ".pdf":

                    text = extract_pdf(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "PDF",
                        text
                    )

                elif extension == ".txt":

                    text = extract_txt(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "TXT",
                        text
                    )

                elif extension == ".csv":

                    text, df = extract_csv(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "CSV",
                        text
                    )

                    st.session_state.csv_datasets.append(
                        {
                            "name":
                                uploaded.name,
                            "data":
                                df
                        }
                    )

                st.success(
                    f"Added {uploaded.name}"
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

    st.caption(
        f"{len(st.session_state.documents)} "
        "knowledge chunks"
    )

    if st.button(
        "Clear knowledge",
        use_container_width=True
    ):

        st.session_state.documents = []

        st.session_state.csv_datasets = []

        st.rerun()

    st.divider()

    st.caption(
        f"NEXUS v{APP_VERSION}"
    )


# ============================================================
# TOP BAR
# ============================================================

model_display = (
    st.session_state.selected_model
    or "Auto"
)

st.markdown(
    f"""
<div class="nexus-top">

    <div>
        <div class="nexus-logo">
            ✦ NEXUS
        </div>

        <div class="nexus-sub">
            Agentic workspace
        </div>
    </div>

    <div class="model-pill">
        {model_display}
    </div>

</div>
""",
    unsafe_allow_html=True
)


# ============================================================
# WELCOME SCREEN
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

    c1, c2, c3 = st.columns(3)

    with c1:

        st.markdown(
            """
<div class="suggestion">
<b>Research</b><br>
Find current information and sources.
</div>
""",
            unsafe_allow_html=True
        )

    with c2:

        st.markdown(
            """
<div class="suggestion">
<b>Analyze</b><br>
Work with documents and data.
</div>
""",
            unsafe_allow_html=True
        )

    with c3:

        st.markdown(
            """
<div class="suggestion">
<b>Reason</b><br>
Solve problems and explain ideas.
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
# ACTIVITY
# ============================================================

if st.session_state.agent_log:

    with st.expander(
        "Activity"
    ):

        for item in st.session_state.agent_log:

            st.markdown(
                f"""
<div class="activity-box">
    ✓ {item}
</div>
""",
                unsafe_allow_html=True
            )


# ============================================================
# INPUT
# ============================================================

query = st.chat_input(
    "Message NEXUS..."
)


# ============================================================
# PROCESS
# ============================================================

if query:

    if not GEMINI_API_KEY:

        st.error(
            "GEMINI_API_KEY is missing. "
            "Add it to Streamlit Secrets."
        )

        st.stop()

    st.session_state.messages.append(
        {
            "role": "user",
            "content": query
        }
    )

    with st.chat_message("user"):

        st.markdown(query)

    with st.chat_message("assistant"):

        try:

            with st.spinner(
                "NEXUS is thinking..."
            ):

                result = asyncio.run(
                    run_nexus(query)
                )

            answer = result["answer"]

            st.markdown(
                answer
            )

            if result["sources"]:

                with st.expander(
                    "Sources"
                ):

                    for source in result["sources"]:

                        title = source.get(
                            "title",
                            "Source"
                        )

                        url = source.get(
                            "url",
                            ""
                        )

                        st.markdown(
                            f"""
<div class="source-card">

    <div class="source-title">
        {title}
    </div>

    <div class="source-url">
        {url}
    </div>

</div>
""",
                            unsafe_allow_html=True
                        )

        except Exception as exc:

            st.error(
                f"{type(exc).__name__}: {exc}"
            )

            st.stop()

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": answer
        }
    )

    st.session_state.request_count += 1

    st.rerun()

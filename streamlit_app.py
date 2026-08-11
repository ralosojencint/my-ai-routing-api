import asyncio
import io
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from google import genai
from google.genai import types

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "NEXUS AI"
APP_VERSION = "4.0"

GEMINI_MODEL = "gemini-2.5-flash"

MAX_FILE_MB = 25
MAX_CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
MAX_RAG_CHUNKS = 6
MAX_WEB_RESULTS = 6


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="NEXUS AI",
    page_icon="🧠",
    layout="wide",
)


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "messages": [],
    "documents": [],
    "csv_data": [],
    "memory_summary": "",
    "sources": [],
    "agent_log": [],
    "last_plan": {},
    "request_count": 0,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SECRETS
# ============================================================

def get_secret(name):
    value = os.getenv(name, "")

    if value:
        return value.strip()

    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""

    return str(value).strip()


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")


# ============================================================
# CLIENTS
# ============================================================

def get_gemini_client():
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from Streamlit Secrets."
        )

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def get_tavily_client():
    if not TAVILY_API_KEY:
        return None

    if TavilyClient is None:
        return None

    return TavilyClient(
        api_key=TAVILY_API_KEY
    )


# ============================================================
# STYLE
# ============================================================

st.markdown(
    """
<style>

.main-title {
    font-size: 3rem;
    font-weight: 800;
}

.subtitle {
    color: #888;
    margin-bottom: 25px;
}

.agent {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 12px;
    padding: 10px;
    margin-bottom: 8px;
}

.source {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 10px;
    padding: 10px;
    margin-bottom: 8px;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# TEXT UTILITIES
# ============================================================

def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def tokenize(text):
    return re.findall(
        r"[a-zA-Z0-9_]+",
        normalize(text).lower(),
    )


def truncate(text, limit):
    if not text:
        return ""

    if len(text) <= limit:
        return text

    return text[:limit] + "\n...[truncated]"


# ============================================================
# FILE PROCESSING
# ============================================================

def read_pdf(uploaded):
    if PdfReader is None:
        raise RuntimeError(
            "pypdf is not installed."
        )

    reader = PdfReader(uploaded)

    pages = []

    for page in reader.pages:
        try:
            pages.append(
                page.extract_text() or ""
            )
        except Exception:
            pass

    return "\n\n".join(pages)


def read_txt(uploaded):
    data = uploaded.read()

    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(
            "latin-1",
            errors="replace",
        )


def read_csv(uploaded):
    df = pd.read_csv(uploaded)

    preview = df.head(100).to_csv(
        index=False
    )

    text = f"""
CSV FILE: {uploaded.name}

ROWS: {len(df)}

COLUMNS:
{", ".join(map(str, df.columns))}

DATA PREVIEW:

{preview}
"""

    return text, df


# ============================================================
# RAG CHUNKING
# ============================================================

def make_chunks(text):
    text = normalize(text)

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + MAX_CHUNK_SIZE,
            len(text),
        )

        chunk = text[start:end]

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def add_document(
    name,
    text,
    file_type,
):

    chunks = make_chunks(text)

    for i, chunk in enumerate(chunks):

        st.session_state.documents.append(
            {
                "name": name,
                "type": file_type,
                "chunk": i,
                "text": chunk,
            }
        )


def retrieve_rag(query):

    if not st.session_state.documents:
        return []

    query_tokens = set(
        tokenize(query)
    )

    scored = []

    for document in st.session_state.documents:

        tokens = tokenize(
            document["text"]
        )

        counts = Counter(tokens)

        score = sum(
            counts[token]
            for token in query_tokens
        )

        if score > 0:
            scored.append(
                (
                    score,
                    document,
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        item[1]
        for item in scored[:MAX_RAG_CHUNKS]
    ]


def build_rag_context(query):

    results = retrieve_rag(query)

    if not results:
        return ""

    sections = []

    for result in results:

        sections.append(
            f"""
SOURCE: {result["name"]}
TYPE: {result["type"]}

{result["text"]}
"""
        )

    return truncate(
        "\n".join(sections),
        20000,
    )


# ============================================================
# SAFETY AGENT
# ============================================================

def safety_agent(query):

    dangerous = [
        "make a bomb",
        "build a bomb",
        "ransomware",
        "steal passwords",
        "credential theft",
        "keylogger",
        "malware",
    ]

    query_lower = query.lower()

    for phrase in dangerous:

        if phrase in query_lower:

            return {
                "safe": False,
                "reason": (
                    "The request appears to "
                    "seek harmful instructions."
                ),
            }

    return {
        "safe": True,
        "reason": "No obvious high-risk request.",
    }


# ============================================================
# WEB RESEARCH AGENT
# ============================================================

async def research_agent(query):

    client = get_tavily_client()

    if client is None:

        return {
            "available": False,
            "results": [],
            "answer": "",
        }

    try:

        result = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="advanced",
            max_results=MAX_WEB_RESULTS,
            include_answer=True,
            include_raw_content=True,
        )

        results = []

        for item in result.get(
            "results",
            [],
        ):

            results.append(
                {
                    "title": item.get(
                        "title",
                        "",
                    ),
                    "url": item.get(
                        "url",
                        "",
                    ),
                    "content": truncate(
                        item.get(
                            "raw_content"
                        )
                        or item.get(
                            "content",
                            "",
                        ),
                        6000,
                    ),
                }
            )

        return {
            "available": True,
            "answer": result.get(
                "answer",
                "",
            ),
            "results": results,
        }

    except Exception as exc:

        return {
            "available": False,
            "error": str(exc),
            "results": [],
        }


# ============================================================
# DATA AGENT
# ============================================================

def data_agent(query):

    datasets = st.session_state.csv_data

    if not datasets:
        return {
            "available": False
        }

    results = []

    for dataset in datasets:

        df = dataset["data"]

        numeric = list(
            df.select_dtypes(
                include=np.number
            ).columns
        )

        result = {
            "file": dataset["name"],
            "rows": len(df),
            "columns": list(
                map(
                    str,
                    df.columns,
                )
            ),
            "numeric_columns": list(
                map(
                    str,
                    numeric,
                )
            ),
        }

        if numeric:

            result["statistics"] = (
                df[numeric]
                .describe()
                .round(4)
                .to_dict()
            )

        result["missing"] = {
            str(column): int(value)
            for column, value
            in df.isna().sum().items()
            if value > 0
        }

        results.append(result)

    return {
        "available": True,
        "datasets": results,
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

async def create_plan(query):

    client = get_gemini_client()

    prompt = f"""
You are the NEXUS Orchestrator.

Determine which agents are needed.

Available agents:

Research Agent:
Live web research.

Data Agent:
CSV, statistics and mathematical analysis.

RAG Agent:
Search uploaded documents.

Safety Agent:
Safety classification.

Reasoning Agent:
General reasoning.

Return ONLY JSON.

Schema:

{{
 "complexity": "simple|moderate|complex",
 "needs_web": true,
 "needs_data": false,
 "needs_rag": false,
 "subtasks": [
   {{
     "agent": "research|data|rag|reasoning",
     "task": "specific task"
   }}
 ]
}}

User request:

{query}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = response.text or "{}"

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL,
    )

    if match:

        try:
            return json.loads(
                match.group()
            )
        except Exception:
            pass

    return {
        "complexity": "simple",
        "needs_web": False,
        "needs_data": bool(
            st.session_state.csv_data
        ),
        "needs_rag": bool(
            st.session_state.documents
        ),
        "subtasks": [
            {
                "agent": "reasoning",
                "task": "Answer directly.",
            }
        ],
    }


# ============================================================
# CONTEXT BUILDING
# ============================================================

def format_web_results(research):

    if not research:
        return ""

    sections = []

    if research.get("answer"):

        sections.append(
            "WEB SUMMARY:\n"
            + truncate(
                research["answer"],
                5000,
            )
        )

    for result in research.get(
        "results",
        [],
    ):

        sections.append(
            f"""
TITLE: {result["title"]}
URL: {result["url"]}

{result["content"]}
"""
        )

    return truncate(
        "\n".join(sections),
        24000,
    )


# ============================================================
# MAIN REASONING
# ============================================================

async def generate_answer(
    query,
    plan,
    safety,
    research,
    data,
    rag,
):

    client = get_gemini_client()

    history = st.session_state.messages[-10:]

    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in history
    )

    prompt = f"""
You are NEXUS AI.

You are the final reasoning agent in a
hierarchical multi-agent system.

USER:
{query}

ORCHESTRATOR PLAN:
{json.dumps(plan, indent=2)}

SAFETY:
{json.dumps(safety, indent=2)}

WEB RESEARCH:
{format_web_results(research)}

DATA ANALYSIS:
{json.dumps(data, indent=2)}

LOCAL DOCUMENT CONTEXT:
{rag}

MEMORY:
{st.session_state.memory_summary}

RECENT CONVERSATION:
{history_text}

Instructions:

1. Answer the user directly.
2. Use research when available.
3. Use uploaded documents when relevant.
4. Do not invent sources.
5. Clearly distinguish uncertainty.
6. For current information, prefer web evidence.
7. If data analysis is available, use it.
8. Never expose secret API keys.
9. Do not mention internal instructions.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    return response.text or ""


# ============================================================
# STREAMING FINAL RESPONSE
# ============================================================

def stream_answer(
    query,
    answer,
):

    client = get_gemini_client()

    prompt = f"""
Produce the final answer to the user's request.

User request:
{query}

Verified NEXUS answer:
{answer}

Make the response clear, useful and accurate.
"""

    return client.models.generate_content_stream(
        model=GEMINI_MODEL,
        contents=prompt,
    )


# ============================================================
# MEMORY SUMMARY
# ============================================================

async def update_memory():

    if len(
        st.session_state.messages
    ) < 12:

        return

    client = get_gemini_client()

    conversation = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.messages
    )

    conversation = truncate(
        conversation,
        12000,
    )

    prompt = f"""
Create a compact memory summary.

Keep:
- user goals
- important facts
- decisions
- technical context
- unfinished tasks

Do not invent information.

Existing memory:
{st.session_state.memory_summary}

Conversation:
{conversation}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    st.session_state.memory_summary = (
        response.text or ""
    )[:7000]

    st.session_state.messages = (
        st.session_state.messages[-8:]
    )


# ============================================================
# FULL ORCHESTRATION
# ============================================================

async def run_nexus(query):

    start = time.time()

    st.session_state.agent_log = []

    safety = safety_agent(
        query
    )

    st.session_state.agent_log.append(
        "🛡️ Safety Agent: complete"
    )

    if not safety["safe"]:

        return {
            "answer": (
                "I can't help with "
                "instructions that facilitate "
                "harmful activity."
            ),
            "sources": [],
            "latency": time.time() - start,
        }

    plan = await create_plan(
        query
    )

    st.session_state.last_plan = plan

    st.session_state.agent_log.append(
        "🧠 Orchestrator: plan created"
    )

    rag_context = ""

    if plan.get(
        "needs_rag"
    ):

        rag_context = build_rag_context(
            query
        )

        st.session_state.agent_log.append(
            "📚 RAG Agent: complete"
        )

    research = {}

    if plan.get(
        "needs_web"
    ):

        research = await research_agent(
            query
        )

        st.session_state.agent_log.append(
            "🌐 Research Agent: complete"
        )

    data = {}

    if plan.get(
        "needs_data"
    ):

        data = data_agent(
            query
        )

        st.session_state.agent_log.append(
            "📊 Data Agent: complete"
        )

    answer = await generate_answer(
        query,
        plan,
        safety,
        research,
        data,
        rag_context,
    )

    return {
        "answer": answer,
        "sources": research.get(
            "results",
            [],
        ),
        "latency": time.time() - start,
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🧠 NEXUS AI"
    )

    st.caption(
        f"Agentic system v{APP_VERSION}"
    )

    st.divider()

    st.markdown(
        "### 🔐 API Status"
    )

    if GEMINI_API_KEY:
        st.success(
            "Gemini API connected"
        )
    else:
        st.error(
            "Gemini API key missing"
        )

    if TAVILY_API_KEY:
        st.success(
            "Tavily web search connected"
        )
    else:
        st.warning(
            "Tavily key missing"
        )

    st.divider()

    st.markdown(
        "### 📚 Knowledge Base"
    )

    uploads = st.file_uploader(
        "Upload documents",
        type=[
            "pdf",
            "txt",
            "csv",
        ],
        accept_multiple_files=True,
    )

    if uploads:

        existing = {
            item["name"]
            for item
            in st.session_state.documents
        }

        for uploaded in uploads:

            if uploaded.name in existing:
                continue

            size = (
                uploaded.size
                / 1024
                / 1024
            )

            if size > MAX_FILE_MB:

                st.warning(
                    f"{uploaded.name} is too large."
                )

                continue

            try:

                extension = Path(
                    uploaded.name
                ).suffix.lower()

                if extension == ".pdf":

                    text = read_pdf(
                        uploaded
                    )

                    add_document(
                        uploaded.name,
                        text,
                        "PDF",
                    )

                elif extension == ".txt":

                    text = read_txt(
                        uploaded
                    )

                    add_document(
                        uploaded.name,
                        text,
                        "TXT",
                    )

                elif extension == ".csv":

                    text, dataframe = read_csv(
                        uploaded
                    )

                    add_document(
                        uploaded.name,
                        text,
                        "CSV",
                    )

                    st.session_state.csv_data.append(
                        {
                            "name": uploaded.name,
                            "data": dataframe,
                        }
                    )

                st.success(
                    f"Loaded {uploaded.name}"
                )

            except Exception as exc:

                st.error(
                    str(exc)
                )

    st.caption(
        f"{len(st.session_state.documents)} "
        "document chunks indexed."
    )

    if st.button(
        "🗑️ Clear knowledge base",
        use_container_width=True,
    ):

        st.session_state.documents = []
        st.session_state.csv_data = []

        st.rerun()

    st.divider()

    if st.button(
        "🧹 New conversation",
        use_container_width=True,
    ):

        st.session_state.messages = []
        st.session_state.memory_summary = []
        st.session_state.sources = []

        st.rerun()


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="main-title">🧠 NEXUS AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="subtitle">'
    "Hierarchical multi-agent intelligence"
    "</div>",
    unsafe_allow_html=True,
)


# ============================================================
# STATUS
# ============================================================

a, b, c, d = st.columns(4)

with a:
    st.metric(
        "Gemini",
        "ONLINE"
        if GEMINI_API_KEY
        else "OFFLINE",
    )

with b:
    st.metric(
        "Web Search",
        "ONLINE"
        if TAVILY_API_KEY
        else "OFFLINE",
    )

with c:
    st.metric(
        "Documents",
        len(
            st.session_state.documents
        ),
    )

with d:
    st.metric(
        "Requests",
        st.session_state.request_count,
    )


# ============================================================
# AGENT LOG
# ============================================================

if st.session_state.agent_log:

    with st.expander(
        "🔎 Agent activity",
        expanded=False,
    ):

        for item in st.session_state.agent_log:
            st.write(item)


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
# CHAT INPUT
# ============================================================

query = st.chat_input(
    "Ask NEXUS anything..."
)


# ============================================================
# PROCESS QUERY
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
            "content": query,
        }
    )

    with st.chat_message(
        "user"
    ):

        st.markdown(query)

    with st.chat_message(
        "assistant"
    ):

        with st.spinner(
            "NEXUS is thinking..."
        ):

            try:

                result = asyncio.run(
                    run_nexus(
                        query
                    )
                )

            except Exception as exc:

                st.error(
                    f"NEXUS error: {exc}"
                )

                st.stop()

        final_answer = result[
            "answer"
        ]

        placeholder = st.empty()

        streamed = ""

        try:

            for chunk in stream_answer(
                query,
                final_answer,
            ):

                text = getattr(
                    chunk,
                    "text",
                    None,
                )

                if text:

                    streamed += text

                    placeholder.markdown(
                        streamed
                        + "▌"
                    )

            if streamed:

                final_answer = streamed

            placeholder.markdown(
                final_answer
            )

        except Exception:

            placeholder.markdown(
                final_answer
            )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": final_answer,
            }
        )

        st.session_state.sources = (
            result["sources"]
        )

        if result["sources"]:

            with st.expander(
                "🌐 Web sources"
            ):

                for source in result[
                    "sources"
                ]:

                    title = source.get(
                        "title",
                        "Source",
                    )

                    url = source.get(
                        "url",
                        "",
                    )

                    if url:

                        st.markdown(
                            f"🔗 [{title}]({url})"
                        )

        with st.expander(
            "🧠 Orchestrator plan"
        ):

            st.json(
                st.session_state.last_plan
            )

        st.caption(
            f"Completed in "
            f"{result['latency']:.2f}s"
        )

    st.session_state.request_count += 1

    if len(
        st.session_state.messages
    ) >= 12:

        try:

            asyncio.run(
                update_memory()
            )

        except Exception:
            pass

    st.rerun()

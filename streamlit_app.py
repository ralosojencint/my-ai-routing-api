import asyncio
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import numpy as np
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
# NEXUS AI
# ============================================================

APP_NAME = "NEXUS"
APP_VERSION = "6.0"

MAX_FILE_MB = 25
MAX_CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
MAX_RAG_RESULTS = 6
MAX_WEB_RESULTS = 6
MAX_HISTORY = 10


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULTS = {
    "messages": [],
    "memory_summary": "",
    "documents": [],
    "csv_datasets": [],
    "agent_log": [],
    "sources": [],
    "last_plan": {},
    "last_execution": [],
    "request_count": 0,
    "total_latency": 0.0,
    "selected_model": None,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# SECRETS
# ============================================================

def secret(name):
    value = os.getenv(name, "").strip()

    if value:
        return value

    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


GEMINI_API_KEY = secret("GEMINI_API_KEY")
TAVILY_API_KEY = secret("TAVILY_API_KEY")


# ============================================================
# GEMINI
# ============================================================

@st.cache_resource(show_spinner=False)
def get_gemini_client():

    if not GEMINI_API_KEY:
        return None

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def discover_gemini_model():

    if st.session_state.selected_model:
        return st.session_state.selected_model

    client = get_gemini_client()

    if client is None:
        return None

    preferred = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3-flash-preview",
        "gemini-flash-latest",
    ]

    available = {}

    try:
        models = client.models.list()

        for model in models:

            name = getattr(
                model,
                "name",
                ""
            )

            if not name:
                continue

            clean = name.replace(
                "models/",
                ""
            )

            available[clean] = model

    except Exception:
        available = {}

    # Prefer known production-capable models
    for candidate in preferred:

        if candidate in available:

            st.session_state.selected_model = candidate

            return candidate

    # Fallback to any Gemini generation model
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

    return None


def require_model():

    model = discover_gemini_model()

    if not model:

        raise RuntimeError(
            "No compatible Gemini generation model "
            "is available to this API key."
        )

    return model


# ============================================================
# TAVILY
# ============================================================

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
# CLEAN UI
# ============================================================

st.markdown(
    """
<style>

/* ---------- GLOBAL ---------- */

#MainMenu {
    visibility: hidden;
}

footer {
    visibility: hidden;
}

header {
    visibility: visible;
}

.block-container {
    max-width: 1180px;
    padding-top: 2rem;
    padding-bottom: 7rem;
}

/* ---------- TYPOGRAPHY ---------- */

html, body, [class*="css"] {
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
}

.nexus-brand {
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.8px;
    margin-bottom: 2px;
}

.nexus-description {
    font-size: 13px;
    color: #777;
    margin-bottom: 28px;
}

/* ---------- SIDEBAR ---------- */

section[data-testid="stSidebar"] {
    border-right: 1px solid rgba(128,128,128,.16);
}

section[data-testid="stSidebar"] > div {
    padding-top: 2rem;
}

.sidebar-brand {
    font-size: 21px;
    font-weight: 700;
    letter-spacing: -0.5px;
    margin-bottom: 4px;
}

.sidebar-muted {
    color: #858585;
    font-size: 12px;
}

/* ---------- CHAT ---------- */

[data-testid="stChatMessage"] {
    padding: 1rem 0;
}

[data-testid="stChatMessageContent"] {
    line-height: 1.65;
}

[data-testid="stChatMessageAvatar"] {
    display: none;
}

/* ---------- INPUT ---------- */

[data-testid="stChatInput"] {
    border-radius: 16px;
}

[data-testid="stChatInput"] textarea {
    font-size: 15px;
}

/* ---------- CARDS ---------- */

.status-card {
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 12px;
    padding: 14px 16px;
    background: rgba(128,128,128,.025);
}

.status-label {
    font-size: 11px;
    color: #858585;
    text-transform: uppercase;
    letter-spacing: .7px;
}

.status-value {
    font-size: 15px;
    font-weight: 600;
    margin-top: 4px;
}

.dot {
    display: inline-block;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    margin-right: 7px;
    background: #35a66f;
}

.dot-off {
    background: #b54a4a;
}

/* ---------- SOURCES ---------- */

.source {
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 10px;
    padding: 11px 13px;
    margin: 7px 0;
}

.source-title {
    font-size: 14px;
    font-weight: 600;
}

.source-url {
    font-size: 11px;
    color: #858585;
    overflow-wrap: anywhere;
}

/* ---------- AGENTS ---------- */

.agent-row {
    padding: 7px 0;
    font-size: 13px;
    border-bottom: 1px solid rgba(128,128,128,.10);
}

.agent-row:last-child {
    border-bottom: none;
}

/* ---------- MOBILE ---------- */

@media (max-width: 700px) {

    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1rem;
    }

    .nexus-brand {
        font-size: 24px;
    }

}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# HELPERS
# ============================================================

def normalize(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def tokens(text):
    return re.findall(
        r"[a-zA-Z0-9_]+",
        normalize(text).lower(),
    )


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


def extract_txt(file):

    raw = file.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(
            "latin-1",
            errors="replace"
        )


def extract_csv(file):

    df = pd.read_csv(file)

    preview = df.head(100).to_csv(
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


# ============================================================
# RAG
# ============================================================

def chunk_text(text):

    text = normalize(text)

    chunks = []

    start = 0

    while start < len(text):

        end = min(
            start + MAX_CHUNK_SIZE,
            len(text)
        )

        piece = text[start:end]

        if piece:
            chunks.append(piece)

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

    for number, piece in enumerate(
        chunk_text(text)
    ):

        st.session_state.documents.append(
            {
                "filename": filename,
                "type": file_type,
                "chunk": number,
                "text": piece,
            }
        )


def retrieve_documents(
    query,
    limit=MAX_RAG_RESULTS
):

    if not st.session_state.documents:
        return []

    query_terms = set(
        tokens(query)
    )

    scored = []

    for document in st.session_state.documents:

        counts = Counter(
            tokens(
                document["text"]
            )
        )

        score = sum(
            counts[token]
            for token in query_terms
        )

        if score > 0:
            scored.append(
                (
                    score,
                    document
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return [
        item[1]
        for item in scored[:limit]
    ]


def rag_context(query):

    results = retrieve_documents(
        query
    )

    if not results:
        return ""

    sections = []

    for item in results:

        sections.append(
            f"""
FILE: {item["filename"]}
TYPE: {item["type"]}
CHUNK: {item["chunk"]}

{item["text"]}
"""
        )

    return truncate(
        "\n".join(sections),
        24000
    )


# ============================================================
# SAFETY
# ============================================================

def safety_agent(query):

    patterns = [
        r"\bmake\s+(a\s+)?bomb\b",
        r"\bbuild\s+(a\s+)?bomb\b",
        r"\bransomware\b",
        r"\bsteal\s+password",
        r"\bcredential\s+theft\b",
        r"\bkeylogger\b",
        r"\bmalware\b",
    ]

    for pattern in patterns:

        if re.search(
            pattern,
            query.lower()
        ):

            return {
                "safe": False,
                "reason":
                    "Potentially harmful request."
            }

    return {
        "safe": True,
        "reason":
            "No obvious high-risk request detected."
    }


# ============================================================
# RESEARCH
# ============================================================

async def research_agent(query):

    client = get_tavily_client()

    if client is None:

        return {
            "available": False,
            "results": [],
            "answer": ""
        }

    try:

        result = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="advanced",
            max_results=MAX_WEB_RESULTS,
            include_answer=True,
            include_raw_content=True
        )

        sources = []

        for item in result.get(
            "results",
            []
        ):

            sources.append(
                {
                    "title": item.get(
                        "title",
                        "Source"
                    ),
                    "url": item.get(
                        "url",
                        ""
                    ),
                    "content": truncate(
                        item.get(
                            "raw_content"
                        )
                        or item.get(
                            "content",
                            ""
                        ),
                        7000
                    )
                }
            )

        return {
            "available": True,
            "answer": result.get(
                "answer",
                ""
            ),
            "results": sources
        }

    except Exception as exc:

        return {
            "available": False,
            "results": [],
            "error": str(exc)
        }


# ============================================================
# DATA AGENT
# ============================================================

def data_agent():

    datasets = (
        st.session_state.csv_datasets
    )

    if not datasets:

        return {
            "available": False,
            "datasets": []
        }

    output = []

    for dataset in datasets:

        df = dataset["data"]

        numeric = list(
            df.select_dtypes(
                include=np.number
            ).columns
        )

        item = {
            "file": dataset["name"],
            "rows": len(df),
            "columns": list(
                map(
                    str,
                    df.columns
                )
            ),
            "numeric_columns": list(
                map(
                    str,
                    numeric
                )
            )
        }

        if numeric:

            item["statistics"] = (
                df[numeric]
                .describe()
                .round(4)
                .to_dict()
            )

        item["missing_values"] = {
            str(column): int(value)
            for column, value
            in df.isna().sum().items()
            if int(value) > 0
        }

        output.append(item)

    return {
        "available": True,
        "datasets": output
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

async def create_plan(query):

    client = get_gemini_client()
    model = require_model()

    prompt = f"""
You are the NEXUS task orchestrator.

Determine which agents are needed.

Available agents:

research:
Live web research through Tavily.

data:
Analyze uploaded CSV files.

rag:
Retrieve relevant uploaded document context.

reasoning:
General reasoning and synthesis.

Return ONLY JSON.

Schema:

{{
  "complexity": "simple|moderate|complex",
  "needs_web": true,
  "needs_data": false,
  "needs_rag": false,
  "needs_verification": false,
  "subtasks": [
    {{
      "agent": "research|data|rag|reasoning",
      "task": "specific task"
    }}
  ]
}}

User:
{query}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt
    )

    text = response.text or ""

    match = re.search(
        r"\{.*\}",
        text,
        re.DOTALL
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
            st.session_state.csv_datasets
        ),
        "needs_rag": bool(
            st.session_state.documents
        ),
        "needs_verification": False,
        "subtasks": [
            {
                "agent": "reasoning",
                "task": "Answer directly."
            }
        ]
    }


# ============================================================
# RESEARCH FORMAT
# ============================================================

def format_research(research):

    if not research:
        return ""

    parts = []

    if research.get("answer"):

        parts.append(
            "WEB SUMMARY:\n"
            + truncate(
                research["answer"],
                6000
            )
        )

    for source in research.get(
        "results",
        []
    ):

        parts.append(
            f"""
TITLE:
{source["title"]}

URL:
{source["url"]}

CONTENT:
{source["content"]}
"""
        )

    return truncate(
        "\n".join(parts),
        26000
    )


# ============================================================
# REASONING
# ============================================================

async def reasoning_agent(
    query,
    plan,
    safety,
    research,
    data,
    local_context
):

    client = get_gemini_client()
    model = require_model()

    recent = (
        st.session_state.messages[
            -MAX_HISTORY:
        ]
    )

    conversation = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in recent
    )

    prompt = f"""
You are NEXUS, a professional AI assistant.

Answer the user's request completely and directly.

USER:
{query}

ORCHESTRATOR:
{json.dumps(plan, indent=2)}

SAFETY:
{json.dumps(safety, indent=2)}

WEB RESEARCH:
{format_research(research)}

DATA:
{json.dumps(data, indent=2)}

LOCAL DOCUMENTS:
{local_context}

MEMORY:
{st.session_state.memory_summary}

RECENT CHAT:
{conversation}

Rules:

- Give a complete answer.
- Do not intentionally truncate the response.
- Do not mention internal agents unless useful.
- Do not invent sources.
- Use supplied sources when relevant.
- Clearly distinguish facts from uncertainty.
- If calculations need checking, create a small Python
  calculation block.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt
    )

    return response.text or ""


# ============================================================
# CODE VERIFICATION
# ============================================================

class CodeSafetyError(Exception):
    pass


class Validator(ast.NodeVisitor):

    forbidden_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.ClassDef,
        ast.AsyncFunctionDef,
        ast.Global,
        ast.Nonlocal,
    )

    forbidden_names = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "requests",
        "urllib",
        "pathlib",
        "pickle",
        "importlib",
        "__import__",
    }

    forbidden_functions = {
        "eval",
        "exec",
        "compile",
        "open",
        "input",
    }

    def visit(self, node):

        if isinstance(
            node,
            self.forbidden_nodes
        ):

            raise CodeSafetyError(
                f"Forbidden syntax: "
                f"{type(node).__name__}"
            )

        super().visit(node)

    def visit_Name(self, node):

        if node.id in self.forbidden_names:

            raise CodeSafetyError(
                f"Forbidden name: {node.id}"
            )

        self.generic_visit(node)

    def visit_Call(self, node):

        if (
            isinstance(
                node.func,
                ast.Name
            )
            and node.func.id
            in self.forbidden_functions
        ):

            raise CodeSafetyError(
                f"Forbidden function: "
                f"{node.func.id}"
            )

        self.generic_visit(node)

    def visit_Attribute(self, node):

        if node.attr.startswith("__"):

            raise CodeSafetyError(
                "Dunder access is forbidden."
            )

        self.generic_visit(node)


def verify_code(code):

    try:

        if len(code) > 10000:
            raise CodeSafetyError(
                "Code block is too large."
            )

        tree = ast.parse(
            code,
            mode="exec"
        )

        Validator().visit(tree)

    except Exception as exc:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc)
        }

    runner = f"""
import math
import statistics
import json

SAFE_BUILTINS = {{
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip
}}

environment = {{
    "__builtins__": SAFE_BUILTINS,
    "math": math,
    "statistics": statistics,
    "json": json
}}

exec(
    compile(
        {code!r},
        "<nexus>",
        "exec"
    ),
    environment,
    environment
)
"""

    try:

        process = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                runner
            ],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=tempfile.gettempdir()
        )

        return {
            "success":
                process.returncode == 0,
            "stdout":
                truncate(
                    process.stdout,
                    8000
                ),
            "stderr":
                truncate(
                    process.stderr,
                    8000
                )
        }

    except subprocess.TimeoutExpired:

        return {
            "success": False,
            "stdout": "",
            "stderr":
                "Verification timed out."
        }

    except Exception as exc:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc)
        }


def extract_python(text):

    return re.findall(
        r"```python\s*(.*?)```",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )


# ============================================================
# SELF CORRECTION
# ============================================================

async def self_correct(
    query,
    draft,
    verification
):

    if not verification:
        return draft

    client = get_gemini_client()
    model = require_model()

    feedback = []

    for item in verification:

        feedback.append(
            f"""
CODE:
{item["code"]}

SUCCESS:
{item["result"]["success"]}

OUTPUT:
{item["result"]["stdout"]}

ERROR:
{item["result"]["stderr"]}
"""
        )

    prompt = f"""
Correct the answer below.

Original request:
{query}

Draft:
{draft}

Verification:
{chr(10).join(feedback)}

Return a complete corrected answer.
Do not hide errors.
Do not invent information.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt
    )

    return response.text or draft


# ============================================================
# MASTER ORCHESTRATOR
# ============================================================

async def run_nexus(query):

    start = time.perf_counter()

    st.session_state.agent_log = []

    # Safety check
    safety = safety_agent(query)

    st.session_state.agent_log.append(
        "Safety check complete"
    )

    if not safety["safe"]:
        return {
            "answer":
                "I can't help with instructions "
                "that facilitate harmful activity.",
            "sources": [],
            "execution": [],
            "latency":
                time.perf_counter() - start
        }

    # --------------------------------------------------------
    # Lightweight routing — no Gemini call needed
    # --------------------------------------------------------

    lower_query = query.lower()

    web_keywords = [
        "current",
        "today",
        "latest",
        "recent",
        "news",
        "price",
        "stock",
        "bitcoin",
        "weather",
        "live",
        "2026"
    ]

    needs_web = (
        TAVILY_API_KEY
        and any(
            word in lower_query
            for word in web_keywords
        )
    )

    needs_rag = bool(
        st.session_state.documents
    )

    needs_data = bool(
        st.session_state.csv_datasets
    )

    plan = {
        "complexity": "simple",
        "needs_web": bool(needs_web),
        "needs_data": needs_data,
        "needs_rag": needs_rag,
        "needs_verification": False,
        "subtasks": []
    }

    st.session_state.last_plan = plan

    st.session_state.agent_log.append(
        "Lightweight routing complete"
    )

    # --------------------------------------------------------
    # Document retrieval
    # --------------------------------------------------------

    local_context = ""

    if needs_rag:

        local_context = rag_context(query)

        st.session_state.agent_log.append(
            "Document retrieval complete"
        )

    # --------------------------------------------------------
    # Web research
    # --------------------------------------------------------

    research = {}

    if needs_web:

        research = await research_agent(query)

        st.session_state.agent_log.append(
            "Web research complete"
        )

    # --------------------------------------------------------
    # Data analysis
    # --------------------------------------------------------

    data = {}

    if needs_data:

        data = data_agent()

    start = time.perf_counter()

    st.session_state.agent_log = []

    safety = safety_agent(query)

    st.session_state.agent_log.append(
        "Safety check complete"
    )

    if not safety["safe"]:
        return {
            "answer": "I can't help with instructions that facilitate harmful activity.",
            "sources": [],
            "execution": [],
            "latency": time.perf_counter() - start
        }

    plan = await create_plan(query)
    st.session_state.last_plan = plan

    st.session_state.agent_log.append(
        "Orchestrator plan created"
    )

    local_context = ""

    if plan.get("needs_rag"):
        local_context = rag_context(query)
        st.session_state.agent_log.append(
            "Document retrieval complete"
        )

    research = {}

    if plan.get("needs_web"):
        research = await research_agent(query)
        st.session_state.agent_log.append(
            "Web research complete"
        )

    data = {}

    if plan.get("needs_data"):
        data = data_agent()
        st.session_state.agent_log.append(
            "Data analysis complete"
        )

    draft = await reasoning_agent(
        query,
        plan,
        safety,
        research,
        data,
        local_context
    )

    execution = []

    code_blocks = extract_python(draft)

    if plan.get("needs_verification") or code_blocks:
        for code in code_blocks[:3]:
            result = await asyncio.to_thread(
                verify_code,
                code
            )

            execution.append({
                "code": code,
                "result": result
            })

        if execution:
            draft = await self_correct(
                query,
                draft,
                execution
            )

            st.session_state.agent_log.append(
                "Verification complete"
            )

    return {
        "answer": draft,
        "sources": research.get("results", []),
        "execution": execution,
        "latency": time.perf_counter() - start
    }


# ============================================================
# MEMORY
# ============================================================

async def compress_memory():

    if len(
        st.session_state.messages
    ) < 12:
        return

    client = get_gemini_client()
    model = require_model()

    old = (
        st.session_state.messages[:-8]
    )

    transcript = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in old
    )

    prompt = f"""
Create compact memory for this conversation.

Preserve:
- goals
- decisions
- important facts
- technical context
- unfinished work

Existing memory:
{st.session_state.memory_summary}

Conversation:
{truncate(transcript, 14000)}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=prompt
    )

    st.session_state.memory_summary = (
        response.text or ""
    )[:7000]

    st.session_state.messages = (
        st.session_state.messages[-8:]
    )


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        '<div class="sidebar-brand">NEXUS</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="sidebar-muted">'
        "AI workspace"
        "</div>",
        unsafe_allow_html=True
    )

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.session_state.memory_summary = ""
        st.session_state.agent_log = []
        st.session_state.last_plan = {}

        st.rerun()

    st.divider()

    st.markdown(
        "**System**"
    )

    model = None

    if GEMINI_API_KEY:

        try:
            model = discover_gemini_model()
        except Exception:
            model = None

    if model:

        st.markdown(
            f"""
            <div class="status-card">
                <div class="status-label">Gemini</div>
                <div class="status-value">
                    <span class="dot"></span>
                    Connected
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.caption(
            model
        )

    else:

        st.markdown(
            """
            <div class="status-card">
                <div class="status-label">Gemini</div>
                <div class="status-value">
                    <span class="dot dot-off"></span>
                    Not connected
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.write("")

    if TAVILY_API_KEY:

        st.markdown(
            """
            <div class="status-card">
                <div class="status-label">Web research</div>
                <div class="status-value">
                    <span class="dot"></span>
                    Available
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    else:

        st.markdown(
            """
            <div class="status-card">
                <div class="status-label">Web research</div>
                <div class="status-value">
                    <span class="dot dot-off"></span>
                    Unavailable
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.divider()

    st.markdown(
        "**Knowledge**"
    )

    uploads = st.file_uploader(
        "Upload documents",
        type=[
            "pdf",
            "txt",
            "csv"
        ],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploads:

        loaded = {
            item["filename"]
            for item
            in st.session_state.documents
        }

        for uploaded in uploads:

            if uploaded.name in loaded:
                continue

            size_mb = (
                uploaded.size
                / 1024
                / 1024
            )

            if size_mb > MAX_FILE_MB:

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

            except Exception as exc:

                st.error(
                    str(exc)
                )

    st.caption(
        f"{len(st.session_state.documents)} "
        "document chunks"
    )

    if st.button(
        "Clear knowledge",
        use_container_width=True
    ):

        st.session_state.documents = []
        st.session_state.csv_datasets = []

        st.rerun()

    st.divider()

    st.markdown(
        "**Memory**"
    )

    if st.session_state.memory_summary:

        with st.expander(
            "View memory"
        ):

            st.write(
                st.session_state.memory_summary
            )

    else:

        st.caption(
            "Memory will appear here as the "
            "conversation grows."
        )


# ============================================================
# MAIN HEADER
# ============================================================

st.markdown(
    '<div class="nexus-brand">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-description">'
    "A clean agentic workspace for research, "
    "analysis, and reasoning."
    "</div>",
    unsafe_allow_html=True
)


# ============================================================
# STATUS
# ============================================================

col1, col2, col3 = st.columns(3)

with col1:

    st.markdown(
        f"""
        <div class="status-card">
            <div class="status-label">Model</div>
            <div class="status-value">
                {st.session_state.selected_model
                 or "Auto"}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col2:

    st.markdown(
        f"""
        <div class="status-card">
            <div class="status-label">Knowledge</div>
            <div class="status-value">
                {len(st.session_state.documents)}
                chunks indexed
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

with col3:

    st.markdown(
        f"""
        <div class="status-card">
            <div class="status-label">Requests</div>
            <div class="status-value">
                {st.session_state.request_count}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


st.write("")


# ============================================================
# CHAT
# ============================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )


# ============================================================
# AGENT ACTIVITY
# ============================================================

if st.session_state.agent_log:

    with st.expander(
        "Activity"
    ):

        for item in st.session_state.agent_log:

            st.markdown(
                f"""
                <div class="agent-row">
                    {item}
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
# EXECUTION
# ============================================================

if query:

    if not GEMINI_API_KEY:

        st.error(
            "Add GEMINI_API_KEY to Streamlit Secrets."
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

        with st.status(
            "Working...",
            expanded=False
        ) as status:

            try:

                result = asyncio.run(
                    run_nexus(query)
                )

                status.update(
                    label="Complete",
                    state="complete"
                )

            except Exception as exc:

                status.update(
                    label="Request failed",
                    state="error"
                )

                st.error(
                    f"{type(exc).__name__}: {exc}"
                )

                st.stop()

        # ----------------------------------------------------
        # FINAL ANSWER
        # ----------------------------------------------------

        final_answer = result["answer"]

        st.markdown(
            final_answer
        )

        # ----------------------------------------------------
        # SOURCES
        # ----------------------------------------------------

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

                    if url:

                        st.markdown(
                            f"""
                            <div class="source">
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

        # ----------------------------------------------------
        # DETAILS
        # ----------------------------------------------------

        with st.expander(
            "Details"
        ):

            st.write(
                f"Response time: "
                f"{result['latency']:.2f}s"
            )

            if st.session_state.last_plan:

                st.json(
                    st.session_state.last_plan
                )

        # ----------------------------------------------------
        # VERIFICATION
        # ----------------------------------------------------

        if result["execution"]:

            with st.expander(
                "Verification"
            ):

                for item in result["execution"]:

                    st.code(
                        item["code"],
                        language="python"
                    )

                    verification = item[
                        "result"
                    ]

                    if verification["success"]:

                        st.success(
                            "Verification passed."
                        )

                    else:

                        st.warning(
                            verification["stderr"]
                        )

                    if verification["stdout"]:

                        st.code(
                            verification["stdout"]
                        )

    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": final_answer
        }
    )

    st.session_state.request_count += 1

    st.session_state.total_latency += (
        result["latency"]
    )

    if len(
        st.session_state.messages
    ) >= 12:

        try:

            asyncio.run(
                compress_memory()
            )

        except Exception:
            pass

    st.rerun()

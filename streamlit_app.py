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
# NEXUS AI — GEMINI EDITION
# ============================================================

APP_NAME = "NEXUS AI"
APP_VERSION = "5.0"
GEMINI_MODEL = "gemini-3.5-flash-lite"

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
    page_title=APP_NAME,
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

STATE_DEFAULTS = {
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
}

for key, value in STATE_DEFAULTS.items():
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
        return str(
            st.secrets.get(name, "")
        ).strip()
    except Exception:
        return ""


GEMINI_API_KEY = secret("GEMINI_API_KEY")
TAVILY_API_KEY = secret("TAVILY_API_KEY")


# ============================================================
# CLIENTS
# ============================================================

def gemini_client():
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from Streamlit Secrets."
        )

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def tavily_client():
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

.block-container {
    max-width: 1400px;
    padding-top: 1.5rem;
}

.nexus-title {
    font-size: 3rem;
    font-weight: 800;
}

.nexus-subtitle {
    color: #888;
    margin-bottom: 1.5rem;
}

.agent-card {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 12px;
    padding: 10px;
    margin: 7px 0;
}

.source-card {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 10px;
    padding: 10px;
    margin: 7px 0;
}

</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# TEXT HELPERS
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

    return text[:limit] + "\n...[truncated]"


# ============================================================
# DOCUMENT PROCESSING
# ============================================================

def extract_pdf(uploaded_file):

    if PdfReader is None:
        raise RuntimeError(
            "pypdf is not installed."
        )

    reader = PdfReader(
        uploaded_file
    )

    pages = []

    for page in reader.pages:

        try:
            pages.append(
                page.extract_text() or ""
            )
        except Exception:
            pass

    return "\n\n".join(pages)


def extract_txt(uploaded_file):

    raw = uploaded_file.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(
            "latin-1",
            errors="replace",
        )


def extract_csv(uploaded_file):

    df = pd.read_csv(
        uploaded_file
    )

    preview = df.head(
        100
    ).to_csv(
        index=False
    )

    text = f"""
CSV FILE: {uploaded_file.name}

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
            len(text),
        )

        piece = text[start:end]

        if piece:
            chunks.append(piece)

        if end >= len(text):
            break

        start = max(
            0,
            end - CHUNK_OVERLAP,
        )

    return chunks


def index_document(
    filename,
    file_type,
    text,
):

    pieces = chunk_text(
        text
    )

    for number, piece in enumerate(
        pieces
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
    limit=MAX_RAG_RESULTS,
):

    if not st.session_state.documents:
        return []

    query_terms = set(
        tokens(query)
    )

    scored = []

    for document in st.session_state.documents:

        document_terms = Counter(
            tokens(
                document["text"]
            )
        )

        score = sum(
            document_terms[token]
            for token in query_terms
        )

        if score > 0:
            scored.append(
                (
                    score,
                    document,
                )
            )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        document
        for _, document
        in scored[:limit]
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
        24000,
    )


# ============================================================
# SAFETY AGENT
# ============================================================

def safety_agent(query):

    dangerous_patterns = [
        r"\bmake\s+(a\s+)?bomb\b",
        r"\bbuild\s+(a\s+)?bomb\b",
        r"\bransomware\b",
        r"\bsteal\s+password",
        r"\bcredential\s+theft\b",
        r"\bkeylogger\b",
        r"\bmalware\b",
    ]

    for pattern in dangerous_patterns:

        if re.search(
            pattern,
            query.lower(),
        ):

            return {
                "safe": False,
                "reason": (
                    "The request appears to "
                    "seek harmful instructions."
                ),
            }

    return {
        "safe": True,
        "reason": "No obvious high-risk request detected.",
    }


# ============================================================
# RESEARCH AGENT
# ============================================================

async def research_agent(query):

    client = tavily_client()

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

        sources = []

        for item in result.get(
            "results",
            [],
        ):

            sources.append(
                {
                    "title": item.get(
                        "title",
                        "Untitled",
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
                        7000,
                    ),
                }
            )

        return {
            "available": True,
            "answer": result.get(
                "answer",
                "",
            ),
            "results": sources,
        }

    except Exception as exc:

        return {
            "available": False,
            "results": [],
            "error": str(exc),
        }


# ============================================================
# DATA AGENT
# ============================================================

def data_agent():

    datasets = st.session_state.csv_datasets

    if not datasets:

        return {
            "available": False,
            "datasets": [],
        }

    output = []

    for dataset in datasets:

        df = dataset["data"]

        numeric_columns = list(
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
                    df.columns,
                )
            ),
            "numeric_columns": list(
                map(
                    str,
                    numeric_columns,
                )
            ),
        }

        if numeric_columns:

            item["statistics"] = (
                df[
                    numeric_columns
                ]
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
        "datasets": output,
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

async def create_plan(query):

    client = gemini_client()

    prompt = f"""
You are the NEXUS hierarchical orchestrator.

Analyze the user's request.

Available agents:

research:
Live web research using Tavily.

data:
CSV analysis and mathematical/statistical reasoning.

rag:
Search uploaded PDF, TXT and CSV context.

safety:
Safety classification.

reasoning:
General reasoning.

Return ONLY valid JSON.

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

User request:

{query}
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    text = response.text or ""

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
            st.session_state.csv_datasets
        ),
        "needs_rag": bool(
            st.session_state.documents
        ),
        "needs_verification": False,
        "subtasks": [
            {
                "agent": "reasoning",
                "task": "Answer directly.",
            }
        ],
    }


# ============================================================
# WEB CONTEXT
# ============================================================

def format_research(research):

    if not research:
        return ""

    sections = []

    if research.get("answer"):

        sections.append(
            "WEB SEARCH SUMMARY:\n"
            + truncate(
                research["answer"],
                6000,
            )
        )

    for source in research.get(
        "results",
        [],
    ):

        sections.append(
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
        "\n".join(sections),
        26000,
    )


# ============================================================
# REASONING AGENT
# ============================================================

async def reasoning_agent(
    query,
    plan,
    safety,
    research,
    data,
    local_context,
):

    client = gemini_client()

    recent = st.session_state.messages[
        -MAX_HISTORY:
    ]

    conversation = "\n".join(
        f"{item['role']}: {item['content']}"
        for item in recent
    )

    prompt = f"""
You are the primary reasoning agent for NEXUS AI.

USER REQUEST:
{query}

ORCHESTRATOR PLAN:
{json.dumps(plan, indent=2)}

SAFETY RESULT:
{json.dumps(safety, indent=2)}

WEB RESEARCH:
{format_research(research)}

DATA AGENT:
{json.dumps(data, indent=2)}

LOCAL RAG:
{local_context}

ROLLING MEMORY:
{st.session_state.memory_summary}

RECENT CONVERSATION:
{conversation}

Rules:

- Answer the user directly.
- Use provided web sources when available.
- Use local documents when relevant.
- Use numerical analysis when available.
- Do not invent sources or facts.
- Clearly state uncertainty.
- Do not reveal API keys or internal secrets.
- If a calculation requires verification, create a small
  Python code block containing only the calculation.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    return response.text or ""


# ============================================================
# CODE EXTRACTION
# ============================================================

def extract_python(code):

    return re.findall(
        r"```python\s*(.*?)```",
        code,
        flags=re.DOTALL | re.IGNORECASE,
    )


# ============================================================
# RESTRICTED CODE VALIDATION
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
            self.forbidden_nodes,
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
                ast.Name,
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


def validate_code(code):

    if len(code) > 10000:

        raise CodeSafetyError(
            "Code block is too large."
        )

    tree = ast.parse(
        code,
        mode="exec",
    )

    Validator().visit(tree)


# ============================================================
# CODE VERIFICATION
# ============================================================

def verify_code(code):

    try:

        validate_code(
            code
        )

    except Exception as exc:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
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
    "zip": zip,
}}

environment = {{
    "__builtins__": SAFE_BUILTINS,
    "math": math,
    "statistics": statistics,
    "json": json,
}}

exec(
    compile(
        {code!r},
        "<nexus-verification>",
        "exec"
    ),
    environment,
    environment,
)
"""

    try:

        process = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                runner,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=tempfile.gettempdir(),
        )

        return {
            "success": (
                process.returncode == 0
            ),
            "stdout": truncate(
                process.stdout,
                8000,
            ),
            "stderr": truncate(
                process.stderr,
                8000,
            ),
        }

    except subprocess.TimeoutExpired:

        return {
            "success": False,
            "stdout": "",
            "stderr": "Verification timed out.",
        }

    except Exception as exc:

        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
        }


# ============================================================
# SELF CORRECTION
# ============================================================

async def self_correct(
    query,
    draft,
    verification,
):

    if not verification:
        return draft

    client = gemini_client()

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
You are the NEXUS verification agent.

Original request:
{query}

Draft:
{draft}

Verification results:
{chr(10).join(feedback)}

Produce a corrected final answer.

Fix numerical mistakes.
Do not hide verification errors.
Do not invent information.
Answer the original request directly.
"""

    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=prompt,
    )

    return response.text or draft


# ============================================================
# MEMORY
# ============================================================

async def compress_memory():

    if len(
        st.session_state.messages
    ) < 12:

        return

    client = gemini_client()

    old_messages = (
        st.session_state.messages[:-8]
    )

    transcript = "\n".join(
        f"{item['role']}: {item['content']}"
        for item in old_messages
    )

    transcript = truncate(
        transcript,
        14000,
    )

    prompt = f"""
Create a compact rolling memory for NEXUS.

Preserve:
- goals
- decisions
- important facts
- technical context
- unfinished work

Do not invent information.

Existing memory:
{st.session_state.memory_summary}

Conversation:
{transcript}
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
# STREAMING
# ============================================================

def stream_final(
    query,
    verified_answer,
):

    client = gemini_client()

    prompt = f"""
Return the final answer to this user request.

REQUEST:
{query}

VERIFIED ANSWER:
{verified_answer}

Be clear and useful.
Do not mention internal agent instructions.
"""

    return client.models.generate_content_stream(
        model=GEMINI_MODEL,
        contents=prompt,
    )


# ============================================================
# MASTER ORCHESTRATOR
# ============================================================

async def run_nexus(query):

    start = time.perf_counter()

    st.session_state.agent_log = []

    safety = safety_agent(
        query
    )

    st.session_state.agent_log.append(
        "🛡️ Safety Agent — complete"
    )

    if not safety["safe"]:

        return {
            "answer": (
                "I can't help with "
                "instructions that facilitate "
                "harmful activity."
            ),
            "sources": [],
            "execution": [],
            "latency": (
                time.perf_counter()
                - start
            ),
        }

    plan = await create_plan(
        query
    )

    st.session_state.last_plan = plan

    st.session_state.agent_log.append(
        "🧠 Orchestrator — plan created"
    )

    local_context = ""

    if plan.get(
        "needs_rag"
    ):

        local_context = rag_context(
            query
        )

        st.session_state.agent_log.append(
            "📚 RAG Agent — complete"
        )

    research = {}

    if plan.get(
        "needs_web"
    ):

        research = await research_agent(
            query
        )

        st.session_state.agent_log.append(
            "🌐 Research Agent — complete"
        )

    data = {}

    if plan.get(
        "needs_data"
    ):

        data = data_agent()

        st.session_state.agent_log.append(
            "📊 Data Agent — complete"
        )

    draft = await reasoning_agent(
        query,
        plan,
        safety,
        research,
        data,
        local_context,
    )

    # --------------------------------------------------------
    # OPTIONAL CODE VERIFICATION
    # --------------------------------------------------------

    execution = []

    code_blocks = extract_python(
        draft
    )

    if (
        plan.get(
            "needs_verification"
        )
        or code_blocks
    ):

        for code in code_blocks[:3]:

            result = await asyncio.to_thread(
                verify_code,
                code,
            )

            execution.append(
                {
                    "code": code,
                    "result": result,
                }
            )

        if execution:

            draft = await self_correct(
                query,
                draft,
                execution,
            )

            st.session_state.agent_log.append(
                "🧪 Verification Agent — complete"
            )

    latency = (
        time.perf_counter()
        - start
    )

    return {
        "answer": draft,
        "sources": research.get(
            "results",
            [],
        ),
        "execution": execution,
        "latency": latency,
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "## 🧠 NEXUS AI"
    )

    st.caption(
        f"Gemini Agentic System v{APP_VERSION}"
    )

    st.divider()

    st.markdown(
        "### 🔐 API STATUS"
    )

    if GEMINI_API_KEY:

        st.success(
            "Gemini connected"
        )

    else:

        st.error(
            "Gemini key missing"
        )

    if TAVILY_API_KEY:

        st.success(
            "Tavily connected"
        )

    else:

        st.warning(
            "Tavily unavailable"
        )

    st.divider()

    st.markdown(
        "### 📚 LOCAL KNOWLEDGE"
    )

    uploads = st.file_uploader(
        "PDF / TXT / CSV",
        type=[
            "pdf",
            "txt",
            "csv",
        ],
        accept_multiple_files=True,
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
                    f"{uploaded.name} "
                    "is too large."
                )

                continue

            try:

                extension = Path(
                    uploaded.name
                ).suffix.lower()

                if extension == ".pdf":

                    text = extract_pdf(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "PDF",
                        text,
                    )

                elif extension == ".txt":

                    text = extract_txt(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "TXT",
                        text,
                    )

                elif extension == ".csv":

                    text, df = extract_csv(
                        uploaded
                    )

                    index_document(
                        uploaded.name,
                        "CSV",
                        text,
                    )

                    st.session_state.csv_datasets.append(
                        {
                            "name": uploaded.name,
                            "data": df,
                        }
                    )

                st.success(
                    f"Loaded {uploaded.name}"
                )

            except Exception as exc:

                st.error(
                    f"Could not load "
                    f"{uploaded.name}: {exc}"
                )

    st.caption(
        f"{len(st.session_state.documents)} "
        "document chunks indexed"
    )

    if st.button(
        "🗑️ Clear knowledge",
        use_container_width=True,
    ):

        st.session_state.documents = []
        st.session_state.csv_datasets = []

        st.rerun()

    st.divider()

    st.markdown(
        "### 🧠 MEMORY"
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
            "No compressed memory yet."
        )

    if st.button(
        "🧹 New conversation",
        use_container_width=True,
    ):

        st.session_state.messages = []
        st.session_state.memory_summary = ""
        st.session_state.sources = []
        st.session_state.agent_log = []

        st.rerun()


# ============================================================
# MAIN UI
# ============================================================

st.markdown(
    '<div class="nexus-title">🧠 NEXUS AI</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="nexus-subtitle">'
    "Hierarchical multi-agent intelligence system"
    "</div>",
    unsafe_allow_html=True,
)

st.divider()


# ============================================================
# STATUS DASHBOARD
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
        "Knowledge",
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
# INPUT
# ============================================================

query = st.chat_input(
    "Ask NEXUS anything..."
)


# ============================================================
# EXECUTION
# ============================================================

if query:

    if not GEMINI_API_KEY:

        st.error(
            "GEMINI_API_KEY is missing "
            "from Streamlit Secrets."
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

        st.markdown(
            query
        )

    with st.chat_message(
        "assistant"
    ):

        with st.status(
            "NEXUS is orchestrating agents...",
            expanded=True,
        ) as status:

            try:

                result = asyncio.run(
                    run_nexus(
                        query
                    )
                )

                status.update(
                    label=(
                        "Orchestration complete"
                    ),
                    state="complete",
                    expanded=False,
                )

            except Exception as exc:

                status.update(
                    label="NEXUS error",
                    state="error",
                )

                st.error(
                    f"{type(exc).__name__}: {exc}"
                )

                st.stop()

        # ----------------------------------------------------
        # STREAM
        # ----------------------------------------------------

        placeholder = st.empty()

        streamed = ""

        try:

            for chunk in stream_final(
                query,
                result["answer"],
            ):

                text = getattr(
                    chunk,
                    "text",
                    None,
                )

                if text:

                    streamed += text

                    placeholder.markdown(
                        streamed + "▌"
                    )

            if streamed:

                final_answer = streamed

            else:

                final_answer = result[
                    "answer"
                ]

            placeholder.markdown(
                final_answer
            )

        except Exception:

            final_answer = result[
                "answer"
            ]

            placeholder.markdown(
                final_answer
            )

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": final_answer,
            }
        )

        # ----------------------------------------------------
        # SOURCES
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # PLAN
        # ----------------------------------------------------

        with st.expander(
            "🧠 Orchestrator plan"
        ):

            st.json(
                st.session_state.last_plan
            )

        # ----------------------------------------------------
        # VERIFICATION
        # ----------------------------------------------------

        if result["execution"]:

            with st.expander(
                "🧪 Verification"
            ):

                for item in result[
                    "execution"
                ]:

                    st.code(
                        item["code"],
                        language="python",
                    )

                    verification = item[
                        "result"
                    ]

                    if verification[
                        "success"
                    ]:

                        st.success(
                            "Verification succeeded."
                        )

                    else:

                        st.warning(
                            verification[
                                "stderr"
                            ]
                        )

                    if verification[
                        "stdout"
                    ]:

                        st.code(
                            verification[
                                "stdout"
                            ]
                        )

        st.caption(
            f"Completed in "
            f"{result['latency']:.2f}s"
        )

    st.session_state.request_count += 1

    st.session_state.total_latency += (
        result["latency"]
    )

    # --------------------------------------------------------
    # MEMORY
    # --------------------------------------------------------

    if len(
        st.session_state.messages
    ) >= 12:

        try:

            asyncio.run(
                compress_memory()
            )

        except Exception as exc:

            st.warning(
                "Memory compression failed: "
                + str(exc)
            )

    st.rerun()

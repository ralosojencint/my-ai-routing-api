import asyncio
import ast
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# NEXUS CONFIGURATION
# ============================================================

APP_NAME = "NEXUS AI"
APP_VERSION = "3.0"

DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_MAX_HISTORY = 12
DEFAULT_TOP_K = 6
DEFAULT_SEARCH_DEPTH = "advanced"

MAX_FILE_SIZE_MB = 25
MAX_CHUNKS_PER_FILE = 300
MAX_CONTEXT_CHARS = 24000
MAX_WEB_CONTEXT_CHARS = 30000
MAX_MEMORY_SUMMARY_CHARS = 8000

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "then", "than",
    "is", "are", "was", "were", "be", "been", "being",
    "to", "of", "in", "on", "for", "with", "from", "by",
    "this", "that", "these", "those", "it", "its",
    "as", "at", "into", "about", "can", "could", "would",
    "should", "will", "what", "when", "where", "who", "why",
    "how", "which", "do", "does", "did", "not", "no",
    "you", "your", "we", "our", "they", "their"
}


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="NEXUS AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSS
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
    margin-bottom: 0;
}

.nexus-subtitle {
    color: #888;
    margin-top: -8px;
}

.agent-card {
    border: 1px solid rgba(128,128,128,.25);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 10px;
}

.status-good {
    padding: 8px 12px;
    border-radius: 10px;
    background: rgba(0,180,100,.12);
}

.status-warn {
    padding: 8px 12px;
    border-radius: 10px;
    background: rgba(255,180,0,.12);
}

.source-card {
    border: 1px solid rgba(128,128,128,.2);
    border-radius: 10px;
    padding: 10px;
    margin: 8px 0;
}

.small-muted {
    color: #888;
    font-size: .85rem;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

def initialize_state():
    defaults = {
        "messages": [],
        "memory_summary": "",
        "documents": [],
        "chunks": [],
        "vectors": None,
        "vocabulary": {},
        "agent_log": [],
        "last_sources": [],
        "last_plan": {},
        "last_execution": None,
        "request_count": 0,
        "total_latency": 0.0,
        "new_chat_counter": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ============================================================
# API CONFIGURATION
# ============================================================

def get_secret(name: str) -> str:
    value = os.getenv(name, "").strip()

    if value:
        return value

    try:
        value = str(st.secrets.get(name, "")).strip()
    except Exception:
        value = ""

    return value


def get_openai_key() -> str:
    return st.session_state.get("openai_key") or get_secret("OPENAI_API_KEY")


def get_tavily_key() -> str:
    return st.session_state.get("tavily_key") or get_secret("TAVILY_API_KEY")


def get_model() -> str:
    return st.session_state.get("model", DEFAULT_MODEL)


# ============================================================
# TEXT UTILITIES
# ============================================================

def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", normalize_text(text))

    return [
        token
        for token in tokens
        if token not in STOP_WORDS and len(token) > 1
    ]


def truncate(text: str, max_chars: int) -> str:
    if not text:
        return ""

    if len(text) <= max_chars:
        return text

    return text[:max_chars] + "\n...[truncated]"


# ============================================================
# FILE PROCESSING
# ============================================================

def extract_pdf(file) -> str:
    if PdfReader is None:
        raise RuntimeError(
            "PDF support requires the pypdf package."
        )

    reader = PdfReader(file)
    pages = []

    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")

    return "\n\n".join(pages)


def extract_text_file(file) -> str:
    raw = file.read()

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")


def extract_csv(file) -> Tuple[str, pd.DataFrame]:
    df = pd.read_csv(file)

    preview = df.head(100).to_csv(index=False)

    description = (
        f"CSV file: {file.name}\n"
        f"Rows: {len(df)}\n"
        f"Columns: {len(df.columns)}\n"
        f"Columns: {', '.join(map(str, df.columns))}\n\n"
        f"Preview:\n{preview}"
    )

    return description, df


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 150,
) -> List[str]:

    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(0, end - overlap)

    return chunks[:MAX_CHUNKS_PER_FILE]


# ============================================================
# SIMPLE IN-MEMORY RAG
# ============================================================

def build_vocabulary(chunks: List[str]) -> Dict[str, int]:
    vocabulary = {}

    for chunk in chunks:
        for token in set(tokenize(chunk)):
            if token not in vocabulary:
                vocabulary[token] = len(vocabulary)

    return vocabulary


def vectorize(text: str, vocabulary: Dict[str, int]) -> np.ndarray:
    vector = np.zeros(len(vocabulary), dtype=np.float32)

    counts = Counter(tokenize(text))

    for token, count in counts.items():
        index = vocabulary.get(token)

        if index is not None:
            vector[index] = float(count)

    norm = np.linalg.norm(vector)

    if norm > 0:
        vector /= norm

    return vector


def rebuild_rag_index():
    chunks = st.session_state.documents

    if not chunks:
        st.session_state.chunks = []
        st.session_state.vocabulary = {}
        st.session_state.vectors = None
        return

    vocabulary = build_vocabulary(chunks)

    vectors = np.vstack([
        vectorize(chunk["text"], vocabulary)
        for chunk in chunks
    ])

    st.session_state.chunks = chunks
    st.session_state.vocabulary = vocabulary
    st.session_state.vectors = vectors


def add_document(
    name: str,
    text: str,
    source_type: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    pieces = chunk_text(text)

    for index, piece in enumerate(pieces):
        st.session_state.documents.append(
            {
                "id": f"{name}-{index}-{time.time_ns()}",
                "name": name,
                "type": source_type,
                "text": piece,
                "metadata": metadata or {},
            }
        )

    rebuild_rag_index()


def retrieve_context(
    query: str,
    top_k: int = DEFAULT_TOP_K,
) -> List[Dict[str, Any]]:

    chunks = st.session_state.documents
    vectors = st.session_state.vectors
    vocabulary = st.session_state.vocabulary

    if not chunks or vectors is None or not vocabulary:
        return []

    query_vector = vectorize(query, vocabulary)

    scores = vectors @ query_vector

    indices = np.argsort(scores)[::-1]

    results = []

    for index in indices[:top_k]:
        score = float(scores[index])

        if score <= 0:
            continue

        item = dict(chunks[index])
        item["score"] = score

        results.append(item)

    return results


# ============================================================
# DATA AGENT
# ============================================================

def detect_numeric_columns(df: pd.DataFrame) -> List[str]:
    return list(df.select_dtypes(include=np.number).columns)


def run_data_agent(
    query: str,
    csv_data: List[Dict[str, Any]],
) -> Dict[str, Any]:

    if not csv_data:
        return {
            "available": False,
            "analysis": "No CSV datasets are loaded.",
        }

    outputs = []

    for dataset in csv_data:
        df = dataset["data"]

        numeric = detect_numeric_columns(df)

        result = {
            "file": dataset["name"],
            "rows": len(df),
            "columns": list(map(str, df.columns)),
            "numeric_columns": list(map(str, numeric)),
        }

        if numeric:
            stats = df[numeric].describe().round(4).to_dict()
            result["statistics"] = stats

        missing = df.isna().sum()
        result["missing_values"] = {
            str(k): int(v)
            for k, v in missing.items()
            if int(v) > 0
        }

        outputs.append(result)

    return {
        "available": True,
        "query": query,
        "datasets": outputs,
    }


# ============================================================
# SAFETY AGENT
# ============================================================

DANGEROUS_PATTERNS = [
    r"\bmake\s+(?:a\s+)?bomb\b",
    r"\bbuild\s+(?:a\s+)?bomb\b",
    r"\bexplosive\s+device\b",
    r"\bmalware\b",
    r"\bransomware\b",
    r"\bsteal\s+password",
    r"\bcredential\s+steal",
    r"\bkeylogger\b",
    r"\bphishing\s+kit\b",
]


def safety_agent(query: str) -> Dict[str, Any]:
    lowered = normalize_text(query)

    matched = []

    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, lowered):
            matched.append(pattern)

    if matched:
        return {
            "safe": False,
            "reason": "The request appears to seek harmful or dangerous instructions.",
            "matched": matched,
        }

    return {
        "safe": True,
        "reason": "No obvious high-risk request detected.",
        "matched": [],
    }


# ============================================================
# WEB RESEARCH AGENT
# ============================================================

def tavily_search_sync(
    query: str,
    api_key: str,
    max_results: int = 6,
    search_depth: str = DEFAULT_SEARCH_DEPTH,
) -> Dict[str, Any]:

    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY is not configured."
        )

    if TavilyClient is None:
        raise RuntimeError(
            "Tavily support requires the tavily-python package."
        )

    client = TavilyClient(api_key=api_key)

    return client.search(
        query=query,
        search_depth=search_depth,
        max_results=max_results,
        include_answer=True,
        include_raw_content=True,
    )


async def run_research_agent(
    query: str,
    api_key: str,
    max_results: int = 6,
) -> Dict[str, Any]:

    result = await asyncio.to_thread(
        tavily_search_sync,
        query,
        api_key,
        max_results,
        DEFAULT_SEARCH_DEPTH,
    )

    formatted = []

    for item in result.get("results", []):
        formatted.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": truncate(
                    item.get("raw_content")
                    or item.get("content")
                    or "",
                    7000,
                ),
                "score": item.get("score"),
            }
        )

    return {
        "query": query,
        "answer": result.get("answer", ""),
        "results": formatted,
    }


# ============================================================
# OPENAI CLIENT
# ============================================================

def get_client() -> AsyncOpenAI:
    if AsyncOpenAI is None:
        raise RuntimeError(
            "The openai package is not installed."
        )

    key = get_openai_key()

    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured."
        )

    return AsyncOpenAI(api_key=key)


# ============================================================
# MEMORY
# ============================================================

def compact_messages() -> List[Dict[str, str]]:
    messages = st.session_state.messages

    max_history = st.session_state.get(
        "max_history",
        DEFAULT_MAX_HISTORY,
    )

    if len(messages) <= max_history:
        return messages

    old_messages = messages[:-max_history]
    recent_messages = messages[-max_history:]

    old_text = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in old_messages
    )

    old_text = truncate(
        old_text,
        12000,
    )

    return [
        {
            "role": "system",
            "content": (
                "Previous conversation summary:\n"
                + st.session_state.memory_summary
            ),
        }
    ] + recent_messages


async def update_memory_summary():
    messages = st.session_state.messages

    if len(messages) <= DEFAULT_MAX_HISTORY:
        return

    client = get_client()

    old_messages = messages[:-DEFAULT_MAX_HISTORY]

    transcript = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in old_messages
    )

    transcript = truncate(transcript, 16000)

    prompt = f"""
Create a compact rolling memory summary of this conversation.

Preserve:
- user goals
- important facts
- decisions
- preferences expressed in the conversation
- unfinished tasks
- technical context
- important constraints

Do not invent information.

Previous summary:
{st.session_state.memory_summary}

Conversation:
{transcript}
"""

    response = await client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": "You are a precise conversation-memory compressor.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
    )

    summary = response.choices[0].message.content or ""

    st.session_state.memory_summary = truncate(
        summary,
        MAX_MEMORY_SUMMARY_CHARS,
    )


# ============================================================
# ORCHESTRATOR PLANNER
# ============================================================

async def create_plan(query: str) -> Dict[str, Any]:
    client = get_client()

    prompt = f"""
You are the NEXUS Orchestrator.

Analyze the user's request and create a hierarchical execution plan.

Available agents:
1. Research Agent
   - web research
   - current information
   - source collection
2. Data Agent
   - CSV analysis
   - mathematics
   - statistics
   - tabular reasoning
3. Refusal/Safety Agent
   - safety assessment
4. Local RAG
   - uploaded PDFs/TXT/CSV context
5. Code Execution
   - only when useful for calculations or verification

Return ONLY valid JSON.

Schema:
{{
  "complexity": "simple|moderate|complex",
  "needs_web": true,
  "needs_data": false,
  "needs_code": false,
  "subtasks": [
    {{
      "agent": "research|data|rag|safety|reasoning",
      "task": "specific task"
    }}
  ],
  "reason": "short explanation"
}}

User request:
{query}
"""

    response = await client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": "You are a deterministic orchestration planner.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )

    content = response.choices[0].message.content or "{}"

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {
            "complexity": "moderate",
            "needs_web": False,
            "needs_data": bool(st.session_state.documents),
            "needs_code": False,
            "subtasks": [
                {
                    "agent": "reasoning",
                    "task": "Answer the user's request directly.",
                }
            ],
            "reason": "Planner returned invalid JSON; fallback plan used.",
        }


# ============================================================
# CODE EXTRACTION
# ============================================================

def extract_python_blocks(text: str) -> List[str]:
    pattern = r"```python\s*(.*?)```"
    return re.findall(
        pattern,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )


# ============================================================
# RESTRICTED PYTHON EXECUTOR
# ============================================================

class UnsafeCodeError(Exception):
    pass


class SafetyValidator(ast.NodeVisitor):

    FORBIDDEN_NODES = (
        ast.Import,
        ast.ImportFrom,
        ast.Global,
        ast.Nonlocal,
        ast.ClassDef,
        ast.AsyncFunctionDef,
    )

    FORBIDDEN_CALLS = {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "input",
        "breakpoint",
    }

    FORBIDDEN_NAMES = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
        "pathlib",
        "requests",
        "urllib",
        "httpx",
        "pickle",
        "builtins",
        "importlib",
    }

    def visit(self, node):
        if isinstance(node, self.FORBIDDEN_NODES):
            raise UnsafeCodeError(
                f"Forbidden syntax: {type(node).__name__}"
            )

        super().visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id in self.FORBIDDEN_CALLS:
                raise UnsafeCodeError(
                    f"Forbidden function: {node.func.id}"
                )

        self.generic_visit(node)

    def visit_Name(self, node):
        if node.id in self.FORBIDDEN_NAMES:
            raise UnsafeCodeError(
                f"Forbidden name: {node.id}"
            )

        self.generic_visit(node)

    def visit_Attribute(self, node):
        if node.attr.startswith("__"):
            raise UnsafeCodeError(
                "Dunder attribute access is forbidden."
            )

        self.generic_visit(node)


def validate_python(code: str):
    if len(code) > 12000:
        raise UnsafeCodeError(
            "Code block is too large."
        )

    tree = ast.parse(code, mode="exec")

    SafetyValidator().visit(tree)


def execute_python_sandbox(
    code: str,
    timeout_seconds: int = 5,
) -> Dict[str, Any]:

    try:
        validate_python(code)
    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
        }

    runner = textwrap.dedent(
        """
        import math
        import statistics
        import json

        SAFE_BUILTINS = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "filter": filter,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "map": map,
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
        }

        safe_globals = {
            "__builtins__": SAFE_BUILTINS,
            "math": math,
            "statistics": statistics,
            "json": json,
        }

        code = {code!r}

        exec(
            compile(code, "<nexus-sandbox>", "exec"),
            safe_globals,
            safe_globals,
        )
        """
    )

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                runner,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=tempfile.gettempdir(),
        )

        return {
            "success": completed.returncode == 0,
            "stdout": truncate(
                completed.stdout,
                10000,
            ),
            "stderr": truncate(
                completed.stderr,
                10000,
            ),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Execution timed out.",
        }

    except Exception as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
        }


# ============================================================
# DATA CONTEXT
# ============================================================

def get_loaded_csv_data() -> List[Dict[str, Any]]:
    result = []

    for item in st.session_state.get(
        "csv_datasets",
        [],
    ):
        result.append(item)

    return result


def build_rag_context(query: str) -> str:
    matches = retrieve_context(
        query,
        top_k=st.session_state.get(
            "rag_top_k",
            DEFAULT_TOP_K,
        ),
    )

    if not matches:
        return ""

    sections = []

    for item in matches:
        sections.append(
            f"""
SOURCE: {item['name']}
RELEVANCE: {item['score']:.3f}

{item['text']}
"""
        )

    return truncate(
        "\n".join(sections),
        MAX_CONTEXT_CHARS,
    )


# ============================================================
# FINAL SYNTHESIS
# ============================================================

def format_web_context(
    research: Dict[str, Any],
) -> str:

    if not research:
        return ""

    sections = []

    answer = research.get("answer", "")

    if answer:
        sections.append(
            "SEARCH ENGINE SUMMARY:\n"
            + truncate(answer, 6000)
        )

    for result in research.get("results", []):
        sections.append(
            f"""
TITLE: {result.get('title')}
URL: {result.get('url')}

CONTENT:
{truncate(result.get('content', ''), 6000)}
"""
        )

    return truncate(
        "\n".join(sections),
        MAX_WEB_CONTEXT_CHARS,
    )


async def generate_draft(
    query: str,
    plan: Dict[str, Any],
    research: Dict[str, Any],
    data_result: Dict[str, Any],
    rag_context: str,
    safety: Dict[str, Any],
) -> str:

    client = get_client()

    history = compact_messages()

    system_prompt = """
You are NEXUS, an advanced AI orchestrator.

You must:
- reason carefully
- distinguish facts from assumptions
- use supplied sources when available
- never invent citations
- use uploaded documents when relevant
- use data-agent results for numerical claims
- follow safety requirements
- answer directly and clearly

If Python verification is useful, you may produce a Python
code block. Keep code focused on calculations only.
"""

    context = f"""
ORCHESTRATOR PLAN:
{json.dumps(plan, indent=2)}

SAFETY:
{json.dumps(safety, indent=2)}

LOCAL RAG:
{rag_context or "No relevant uploaded document context."}

WEB RESEARCH:
{format_web_context(research) or "No web research performed."}

DATA AGENT:
{json.dumps(data_result, indent=2)}

USER REQUEST:
{query}
"""

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    if st.session_state.memory_summary:
        messages.append(
            {
                "role": "system",
                "content": (
                    "ROLLING MEMORY:\n"
                    + st.session_state.memory_summary
                ),
            }
        )

    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": context,
        }
    )

    response = await client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=0.2,
    )

    return response.choices[0].message.content or ""


# ============================================================
# SELF-CORRECTION
# ============================================================

async def self_correct(
    query: str,
    draft: str,
    execution_results: List[Dict[str, Any]],
) -> str:

    if not execution_results:
        return draft

    client = get_client()

    feedback = []

    for item in execution_results:
        feedback.append(
            f"""
CODE:
{item['code']}

SUCCESS:
{item['result']['success']}

STDOUT:
{item['result']['stdout']}

STDERR:
{item['result']['stderr']}
"""
        )

    prompt = f"""
You are the NEXUS verification agent.

Original request:
{query}

Draft answer:
{draft}

Python verification results:
{chr(10).join(feedback)}

Rewrite the answer so that:
1. verified calculations are corrected if necessary
2. errors are not hidden
3. unsupported claims are removed
4. the answer directly addresses the user
5. do not include Python code unless genuinely useful
"""

    response = await client.chat.completions.create(
        model=get_model(),
        messages=[
            {
                "role": "system",
                "content": "You are a meticulous answer verifier.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.1,
    )

    return response.choices[0].message.content or draft


# ============================================================
# STREAM FINAL RESPONSE
# ============================================================

async def stream_final_answer(
    query: str,
    answer: str,
):

    client = get_client()

    history = compact_messages()

    messages = [
        {
            "role": "system",
            "content": """
You are NEXUS AI.

Return the verified final answer.
Be concise when the question is simple.
Be detailed when the question requires it.
Do not mention internal agent architecture unless asked.
Do not claim you performed actions that you did not perform.
""",
        }
    ]

    if st.session_state.memory_summary:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Conversation memory:\n"
                    + st.session_state.memory_summary
                ),
            }
        )

    messages.extend(history)

    messages.append(
        {
            "role": "user",
            "content": (
                f"Original request:\n{query}\n\n"
                f"Verified draft:\n{answer}"
            ),
        }
    )

    stream = await client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=0.2,
        stream=True,
    )

    async for chunk in stream:
        try:
            delta = chunk.choices[0].delta.content

            if delta:
                yield delta

        except Exception:
            continue


# ============================================================
# ORCHESTRATOR
# ============================================================

async def orchestrate(query: str) -> Dict[str, Any]:

    start = time.perf_counter()

    st.session_state.agent_log = []

    # Safety always runs.
    safety = safety_agent(query)

    st.session_state.agent_log.append(
        {
            "agent": "Safety Agent",
            "status": "completed",
        }
    )

    if not safety["safe"]:
        return {
            "answer": (
                "I can't help with instructions that facilitate "
                "harmful or dangerous activity."
            ),
            "plan": {
                "complexity": "blocked",
                "reason": safety["reason"],
            },
            "research": {},
            "data": {},
            "rag": "",
            "execution": [],
            "sources": [],
            "latency": time.perf_counter() - start,
        }

    plan = await create_plan(query)

    st.session_state.last_plan = plan

    st.session_state.agent_log.append(
        {
            "agent": "Orchestrator",
            "status": "planned",
        }
    )

    rag_context = build_rag_context(query)

    if rag_context:
        st.session_state.agent_log.append(
            {
                "agent": "RAG Agent",
                "status": "completed",
            }
        )

    research = {}
    data_result = {}

    tasks = []

    if plan.get("needs_web"):
        tavily_key = get_tavily_key()

        if tavily_key:
            tasks.append(
                run_research_agent(
                    query,
                    tavily_key,
                    st.session_state.get(
                        "max_search_results",
                        6,
                    ),
                )
            )
        else:
            st.session_state.agent_log.append(
                {
                    "agent": "Research Agent",
                    "status": "skipped: no Tavily key",
                }
            )

    csv_data = get_loaded_csv_data()

    if plan.get("needs_data") or csv_data:
        data_result = run_data_agent(
            query,
            csv_data,
        )

        st.session_state.agent_log.append(
            {
                "agent": "Data Agent",
                "status": "completed",
            }
        )

    if tasks:
        results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                st.session_state.agent_log.append(
                    {
                        "agent": "Research Agent",
                        "status": f"error: {result}",
                    }
                )
            else:
                research = result
                st.session_state.agent_log.append(
                    {
                        "agent": "Research Agent",
                        "status": "completed",
                    }
                )

    draft = await generate_draft(
        query=query,
        plan=plan,
        research=research,
        data_result=data_result,
        rag_context=rag_context,
        safety=safety,
    )

    # ========================================================
    # CODE VERIFICATION LOOP
    # ========================================================

    execution_results = []

    if plan.get("needs_code") or extract_python_blocks(draft):

        blocks = extract_python_blocks(draft)

        for code in blocks[:3]:
            result = execute_python_sandbox(code)

            execution_results.append(
                {
                    "code": code,
                    "result": result,
                }
            )

        if execution_results:
            st.session_state.last_execution = execution_results

            draft = await self_correct(
                query,
                draft,
                execution_results,
            )

            st.session_state.agent_log.append(
                {
                    "agent": "Code Verification Agent",
                    "status": "completed",
                }
            )

    latency = time.perf_counter() - start

    sources = research.get("results", [])

    st.session_state.last_sources = sources

    return {
        "answer": draft,
        "plan": plan,
        "research": research,
        "data": data_result,
        "rag": rag_context,
        "execution": execution_results,
        "sources": sources,
        "latency": latency,
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## 🧠 NEXUS AI")

    st.caption(
        f"Agentic Intelligence • v{APP_VERSION}"
    )

    st.divider()

    st.markdown("### 🔑 API Configuration")

    openai_input = st.text_input(
        "OpenAI API Key",
        value=st.session_state.get("openai_key", ""),
        type="password",
        help="Used for the NEXUS reasoning and streaming engine.",
    )

    st.session_state.openai_key = openai_input.strip()

    tavily_input = st.text_input(
        "Tavily API Key",
        value=st.session_state.get("tavily_key", ""),
        type="password",
        help="Used by the Research Agent for live web search.",
    )

    st.session_state.tavily_key = tavily_input.strip()

    st.divider()

    st.markdown("### ⚙️ Model")

    st.session_state.model = st.selectbox(
        "Reasoning model",
        [
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-4o-mini",
            "gpt-4o",
        ],
        index=0,
    )

    st.session_state.max_search_results = st.slider(
        "Web results",
        min_value=3,
        max_value=10,
        value=6,
    )

    st.session_state.rag_top_k = st.slider(
        "RAG context chunks",
        min_value=2,
        max_value=12,
        value=6,
    )

    st.session_state.max_history = st.slider(
        "Recent memory turns",
        min_value=4,
        max_value=20,
        value=12,
    )

    st.divider()

    st.markdown("### 📚 Local Knowledge")

    uploaded_files = st.file_uploader(
        "Upload PDF, TXT, or CSV",
        type=["pdf", "txt", "csv"],
        accept_multiple_files=True,
    )

    if uploaded_files:

        existing_names = {
            d["name"]
            for d in st.session_state.documents
        }

        for uploaded in uploaded_files:

            if uploaded.name in existing_names:
                continue

            size_mb = uploaded.size / (1024 * 1024)

            if size_mb > MAX_FILE_SIZE_MB:
                st.warning(
                    f"{uploaded.name} exceeds the "
                    f"{MAX_FILE_SIZE_MB} MB limit."
                )
                continue

            try:

                extension = Path(
                    uploaded.name
                ).suffix.lower()

                if extension == ".pdf":

                    text = extract_pdf(uploaded)

                    add_document(
                        uploaded.name,
                        text,
                        "PDF",
                    )

                elif extension == ".txt":

                    text = extract_text_file(uploaded)

                    add_document(
                        uploaded.name,
                        text,
                        "TXT",
                    )

                elif extension == ".csv":

                    description, df = extract_csv(
                        uploaded
                    )

                    add_document(
                        uploaded.name,
                        description,
                        "CSV",
                    )

                    if "csv_datasets" not in st.session_state:
                        st.session_state.csv_datasets = []

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
                    f"Could not process "
                    f"{uploaded.name}: {exc}"
                )

    if st.session_state.documents:
        st.info(
            f"{len(st.session_state.documents)} "
            f"RAG chunks indexed."
        )

    if st.button(
        "🗑️ Clear Knowledge Base",
        use_container_width=True,
    ):
        st.session_state.documents = []
        st.session_state.chunks = []
        st.session_state.vectors = None
        st.session_state.vocabulary = {}
        st.session_state.csv_datasets = []
        st.rerun()

    st.divider()

    st.markdown("### 🧠 Memory")

    if st.session_state.memory_summary:
        with st.expander("View rolling memory"):
            st.write(
                st.session_state.memory_summary
            )
    else:
        st.caption(
            "No compressed memory yet."
        )

    if st.button(
        "🧹 New Chat",
        use_container_width=True,
    ):
        st.session_state.messages = []
        st.session_state.memory_summary = ""
        st.session_state.agent_log = []
        st.session_state.last_sources = []
        st.session_state.last_plan = {}
        st.session_state.last_execution = None
        st.rerun()

    st.divider()

    st.markdown("### 📊 Runtime")

    st.metric(
        "Requests",
        st.session_state.request_count,
    )

    if st.session_state.request_count:
        average = (
            st.session_state.total_latency
            / st.session_state.request_count
        )

        st.metric(
            "Avg latency",
            f"{average:.2f}s",
        )

    st.caption(
        "NEXUS uses an orchestrator + specialist agents."
    )


# ============================================================
# MAIN HEADER
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
# DASHBOARD
# ============================================================

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "RAG",
        "ONLINE" if st.session_state.documents else "EMPTY",
    )

with col2:
    st.metric(
        "Web Research",
        "ONLINE" if get_tavily_key() else "OFFLINE",
    )

with col3:
    st.metric(
        "AI Engine",
        "ONLINE" if get_openai_key() else "OFFLINE",
    )

with col4:
    st.metric(
        "Agents",
        "5",
    )


# ============================================================
# AGENT STATUS
# ============================================================

if st.session_state.agent_log:

    with st.expander(
        "🔎 Current Orchestration",
        expanded=False,
    ):

        for item in st.session_state.agent_log:

            status = item["status"]

            icon = (
                "✅"
                if status == "completed"
                or status == "planned"
                else "⚠️"
            )

            st.write(
                f"{icon} **{item['agent']}** — {status}"
            )


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    role = message["role"]

    if role not in {"user", "assistant"}:
        continue

    with st.chat_message(
        role,
        avatar="🧑" if role == "user" else "🧠",
    ):
        st.markdown(
            message["content"]
        )


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask NEXUS anything..."
)


# ============================================================
# REQUEST PROCESSING
# ============================================================

if prompt:

    if not get_openai_key():

        st.error(
            "OpenAI API key is required. "
            "Add it in the sidebar."
        )

        st.stop()

    st.session_state.messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    with st.chat_message(
        "user",
        avatar="🧑",
    ):
        st.markdown(prompt)

    with st.chat_message(
        "assistant",
        avatar="🧠",
    ):

        status_box = st.status(
            "NEXUS is orchestrating agents...",
            expanded=True,
        )

        try:

            result = asyncio.run(
                orchestrate(prompt)
            )

            status_box.update(
                label=(
                    "Agent orchestration complete"
                ),
                state="complete",
                expanded=False,
            )

        except Exception as exc:

            status_box.update(
                label="NEXUS encountered an error",
                state="error",
                expanded=True,
            )

            st.error(
                f"{type(exc).__name__}: {exc}"
            )

            st.stop()

        # ----------------------------------------------------
        # Safety blocked response
        # ----------------------------------------------------

        if result["plan"].get(
            "complexity"
        ) == "blocked":

            final_answer = result["answer"]

            st.markdown(final_answer)

        else:

            # ------------------------------------------------
            # Streaming final response
            # ------------------------------------------------

            placeholder = st.empty()

            collected = ""

            async def collect_stream():

                nonlocal_holder = []

                async for token in stream_final_answer(
                    prompt,
                    result["answer"],
                ):
                    nonlocal_holder.append(token)

                    placeholder.markdown(
                        "".join(nonlocal_holder)
                        + "▌"
                    )

                return "".join(
                    nonlocal_holder
                )

            final_answer = asyncio.run(
                collect_stream()
            )

            placeholder.markdown(
                final_answer
            )

        # ----------------------------------------------------
        # Store assistant message
        # ----------------------------------------------------

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": final_answer,
            }
        )

        # ----------------------------------------------------
        # Metrics
        # ----------------------------------------------------

        latency = result["latency"]

        st.session_state.request_count += 1

        st.session_state.total_latency += latency

        # ----------------------------------------------------
        # Sources
        # ----------------------------------------------------

        sources = result.get(
            "sources",
            [],
        )

        if sources:

            with st.expander(
                f"🌐 Sources ({len(sources)})",
                expanded=False,
            ):

                for source in sources:

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
                            f"**[{title}]({url})**"
                        )

                    else:
                        st.markdown(
                            f"**{title}**"
                        )

                    score = source.get(
                        "score"
                    )

                    if score is not None:
                        st.caption(
                            f"Relevance: {score:.3f}"
                        )

        # ----------------------------------------------------
        # RAG evidence
        # ----------------------------------------------------

        if result.get("rag"):

            with st.expander(
                "📚 Local RAG context used",
                expanded=False,
            ):
                st.code(
                    result["rag"],
                    language="text",
                )

        # ----------------------------------------------------
        # Execution
        # ----------------------------------------------------

        if result.get(
            "execution"
        ):

            with st.expander(
                "🧪 Code verification",
                expanded=False,
            ):

                for item in result["execution"]:

                    st.code(
                        item["code"],
                        language="python",
                    )

                    execution = item[
                        "result"
                    ]

                    if execution[
                        "success"
                    ]:

                        st.success(
                            "Execution successful"
                        )

                    else:

                        st.warning(
                            "Execution failed"
                        )

                    if execution[
                        "stdout"
                    ]:

                        st.code(
                            execution[
                                "stdout"
                            ],
                            language="text",
                        )

                    if execution[
                        "stderr"
                    ]:

                        st.code(
                            execution[
                                "stderr"
                            ],
                            language="text",
                        )

        # ----------------------------------------------------
        # Plan
        # ----------------------------------------------------

        with st.expander(
            "🧠 Orchestrator plan",
            expanded=False,
        ):

            st.json(
                result["plan"]
            )

    # --------------------------------------------------------
    # MEMORY COMPRESSION
    # --------------------------------------------------------

    try:

        if len(
            st.session_state.messages
        ) > DEFAULT_MAX_HISTORY:

            asyncio.run(
                update_memory_summary()
            )

    except Exception as exc:

        st.warning(
            "Memory compression failed: "
            + str(exc)
        )

    st.rerun()

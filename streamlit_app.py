import os
import re
import json
import sqlite3
import asyncio
import time
import io
import base64
from pathlib import Path
from collections import Counter

import streamlit as st
import pandas as pd

try:
    from google import genai
except Exception:
    genai = None

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from PIL import Image
except Exception:
    Image = None


# ============================================================
# NEXUS AI — STABLE SINGLE FILE
# Chat + attachments + datasets + documents + memory
# Gemini -> Groq fallback + Tavily research
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="wide",
)

APP_NAME = "NEXUS AI"
MODEL = "gemini-3.5-flash"
DB_PATH = Path("nexus_memory.db")


# -------------------- Secrets --------------------

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
GROQ_API_KEY = get_secret("GROQ_API_KEY")


# -------------------- Persistent memory --------------------

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL
        )
        """
    )
    con.commit()
    return con


def save_memory(user_text, assistant_text):
    try:
        con = db()
        con.execute(
            "INSERT INTO memories(created_at,user_text,assistant_text) "
            "VALUES(?,?,?)",
            (time.time(), user_text, assistant_text),
        )
        con.commit()
        con.close()
    except Exception:
        pass


def load_memories(limit=12):
    try:
        con = db()
        rows = con.execute(
            "SELECT user_text, assistant_text "
            "FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        con.close()
        return list(reversed(rows))
    except Exception:
        return []


def clear_memories():
    try:
        con = db()
        con.execute("DELETE FROM memories")
        con.commit()
        con.close()
        return True
    except Exception:
        return False


# -------------------- Session state --------------------

DEFAULT_STATE = {
    "messages": [],
    "documents": [],
    "datasets": [],
    "request_count": 0,
    "activity": [],
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, list) else value


# -------------------- Clients --------------------

@st.cache_resource
def gemini_client():
    if not GEMINI_API_KEY or genai is None:
        return None
    try:
        return genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        return None


@st.cache_resource
def tavily_client():
    if not TAVILY_API_KEY or TavilyClient is None:
        return None
    try:
        return TavilyClient(api_key=TAVILY_API_KEY)
    except Exception:
        return None


@st.cache_resource
def groq_client():
    if not GROQ_API_KEY or Groq is None:
        return None
    try:
        return Groq(api_key=GROQ_API_KEY)
    except Exception:
        return None


# -------------------- Text helpers --------------------

def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_ai_response(text):
    if not text:
        return ""

    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"<thinking>.*?</thinking>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"<think>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"<thinking>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(
        r"\n\s*(Sources|Source List)\s*:?\s*$.*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return text.strip()


def make_chunks(text, size=1400, overlap=200):
    text = clean_text(text)
    if not text:
        return []

    result = []
    start = 0

    while start < len(text):
        end = min(start + size, len(text))
        result.append(text[start:end])

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return result


# -------------------- File handling --------------------

def replace_document(name, text):
    st.session_state.documents = [
        d for d in st.session_state.documents
        if d["name"] != name
    ]

    for index, chunk in enumerate(make_chunks(text)):
        st.session_state.documents.append(
            {
                "name": name,
                "chunk": index,
                "text": chunk,
            }
        )


def replace_dataset(name, dataframe):
    st.session_state.datasets = [
        d for d in st.session_state.datasets
        if d["name"] != name
    ]

    st.session_state.datasets.append(
        {
            "name": name,
            "data": dataframe,
        }
    )


def read_uploaded_file(uploaded):
    name = uploaded.name
    ext = Path(name).suffix.lower()

    if ext == ".pdf":
        if PdfReader is None:
            return "", "PDF reader is unavailable."

        try:
            uploaded.seek(0)
            reader = PdfReader(uploaded)
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
            return text, None
        except Exception as exc:
            return "", f"PDF could not be read: {exc}"

    if ext in {".txt", ".md"}:
        try:
            return (
                uploaded.getvalue().decode(
                    "utf-8",
                    errors="replace",
                ),
                None,
            )
        except Exception as exc:
            return "", f"Text file could not be read: {exc}"

    if ext == ".csv":
        try:
            uploaded.seek(0)
            df = pd.read_csv(uploaded)
            replace_dataset(name, df)
            return df.head(100).to_csv(index=False), None
        except Exception as exc:
            return "", f"CSV could not be read: {exc}"

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return "", None

    return "", f"Unsupported file type: {ext}"


def index_files(files):
    attached_images = []

    for uploaded in files or []:
        ext = Path(uploaded.name).suffix.lower()

        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            if Image is None:
                st.warning("Pillow is not installed, so images cannot be read.")
                continue

            try:
                uploaded.seek(0)
                image = Image.open(uploaded).convert("RGB")
                attached_images.append((uploaded.name, image))
            except Exception as exc:
                st.warning(
                    f"{uploaded.name}: image could not be read ({exc})."
                )
            continue

        try:
            text, error = read_uploaded_file(uploaded)

            if error:
                st.warning(f"{uploaded.name}: {error}")
                continue

            if text:
                replace_document(uploaded.name, text)

        except Exception as exc:
            st.warning(f"{uploaded.name}: {exc}")

    return attached_images


def retrieve_documents(query, limit=8):
    terms = set(
        re.findall(
            r"[a-zA-Z0-9_]+",
            query.lower(),
        )
    )

    scored = []

    for doc in st.session_state.documents:
        text = str(doc.get("text", ""))
        words = Counter(
            re.findall(
                r"[a-zA-Z0-9_]+",
                text.lower(),
            )
        )
        score = sum(words[t] for t in terms)

        if score:
            scored.append((score, doc))

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [doc for _, doc in scored[:limit]]


def build_dataset_context():
    parts = []

    for dataset in st.session_state.datasets:
        name = str(dataset.get("name", "Dataset"))
        df = dataset.get("data")

        if not isinstance(df, pd.DataFrame):
            continue

        columns = ", ".join(str(c) for c in df.columns)
        rows = len(df)

        try:
            preview = df.head(100).to_csv(index=False)
        except Exception:
            preview = "(preview unavailable)"

        parts.append(
            f"[{name}]\n"
            f"Columns: {columns}\n"
            f"Rows: {rows}\n"
            f"Data:\n{preview}"
        )

    return "\n\n".join(parts)


# -------------------- Dataset analysis --------------------

def dataset_summary():
    if not st.session_state.datasets:
        return "(none)"

    summaries = []

    for dataset in st.session_state.datasets:
        name = dataset["name"]
        df = dataset["data"]

        lines = [
            f"Dataset: {name}",
            f"Columns: {', '.join(map(str, df.columns))}",
            f"Rows: {len(df)}",
        ]

        numeric = df.select_dtypes(include="number")

        if not numeric.empty:
            lines.append(
                "Numeric columns: "
                + ", ".join(map(str, numeric.columns))
            )

            for column in numeric.columns:
                try:
                    lines.append(
                        f"{column}: sum={numeric[column].sum()}, "
                        f"mean={numeric[column].mean()}"
                    )
                except Exception:
                    pass

        summaries.append("\n".join(lines))

    return "\n\n".join(summaries)


# -------------------- Gemini --------------------

async def gemini_text(prompt, images=None):
    client = gemini_client()

    if client is None:
        return (
            "⚠️ Gemini is not connected. "
            "Add GEMINI_API_KEY in Streamlit Secrets."
        )

    contents = [prompt]

    for _, image in images or []:
        contents.append(image)

    max_retries = 2

    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=contents,
            )

            answer = getattr(response, "text", "") or ""
            answer = clean_ai_response(answer)

            if answer:
                return answer

            return "⚠️ Gemini returned an empty response."

        except Exception as exc:
            error_text = str(exc).lower()

            if (
                "429" in error_text
                or "resource_exhausted" in error_text
                or "quota" in error_text
                or "rate limit" in error_text
            ):
                if attempt < max_retries:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue

                return await groq_text(prompt, images)

            if (
                "404" in error_text
                or "not_found" in error_text
                or "not found" in error_text
            ):
                return await groq_text(prompt, images)

            if (
                "503" in error_text
                or "service unavailable" in error_text
                or "unavailable" in error_text
            ):
                if attempt < max_retries:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue

                return await groq_text(prompt, images)

            return await groq_text(prompt, images)

    return "⚠️ NEXUS could not complete the Gemini request."


# -------------------- Groq fallback --------------------

async def groq_text(prompt, images=None):
    if not GROQ_API_KEY:
        return (
            "⚠️ Gemini is unavailable and GROQ_API_KEY "
            "is missing from Streamlit Secrets."
        )

    client = groq_client()

    if client is None:
        return "⚠️ Groq client could not be initialized."

    try:
        prompt = str(prompt)[:12000]

        if images:
            user_content = [
                {
                    "type": "text",
                    "text": prompt,
                }
            ]

            for _, image in images:
                buffer = io.BytesIO()
                image.convert("RGB").save(
                    buffer,
                    format="JPEG",
                    quality=85,
                )

                encoded = base64.b64encode(
                    buffer.getvalue()
                ).decode("utf-8")

                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                "data:image/jpeg;base64,"
                                + encoded
                            )
                        },
                    }
                )
        else:
            user_content = prompt

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="qwen/qwen3.6-27b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NEXUS, an intelligent AI assistant. "
                        "Answer clearly, accurately and directly. "
                        "Do not reveal internal reasoning."
                    ),
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
        )

        if not response.choices:
            return "⚠️ Groq returned no choices."

        answer = response.choices[0].message.content or ""
        answer = clean_ai_response(answer)

        if not answer:
            return "⚠️ Groq returned an empty response."

        return answer

    except Exception as exc:
        return (
            "⚠️ NEXUS could not complete the request through "
            f"Gemini or Groq. ({type(exc).__name__})"
        )


# -------------------- Tavily research --------------------

def should_research(query):
    q = query.lower()

    research_words = [
        "latest",
        "today",
        "current",
        "news",
        "recent",
        "breaking",
        "research",
        "2026",
        "what happened",
        "developments",
        "this week",
    ]

    return bool(TAVILY_API_KEY) and any(
        word in q
        for word in research_words
    )


def research_query_list(query):
    q = query.strip()
    return [
        q,
        f"{q} latest news",
        f"{q} announcement release",
        f"{q} research technology",
    ]


async def research(query):
    client = tavily_client()

    if client is None:
        return {
            "sources": [],
            "error": (
                "Tavily is not connected. "
                "Check TAVILY_API_KEY."
            ),
        }

    all_sources = []

    for search_query in research_query_list(query):
        try:
            result = await asyncio.to_thread(
                client.search,
                query=search_query,
                search_depth="advanced",
                topic="news",
                time_range="week",
                max_results=8,
                include_answer=False,
            )

            for source in result.get("results", []):
                if isinstance(source, dict):
                    all_sources.append(source)

        except Exception:
            continue

    unique = []
    seen_urls = set()

    for source in all_sources:
        url = str(source.get("url", "")).strip()
        normalized = url.rstrip("/").lower()

        if not normalized or normalized in seen_urls:
            continue

        seen_urls.add(normalized)

        title = clean_text(source.get("title", ""))
        content = clean_text(source.get("content", ""))

        if len(title) < 8 or len(content) < 80:
            continue

        unique.append(source)

    return {
        "sources": unique[:20],
        "error": "" if unique else "No relevant results found.",
    }


# -------------------- Research synthesis --------------------

def is_latest_model_request(query):
    q = query.lower()
    return any(
        phrase in q
        for phrase in [
            "latest ai model",
            "latest model",
            "newest ai model",
            "new ai model",
            "ai model released",
            "model released today",
            "model launch",
        ]
    )


async def synthesize_research(query, sources):
    if not sources:
        return ""

    source_parts = []

    for index, source in enumerate(sources[:12], 1):
        title = clean_text(source.get("title", "Untitled"))
        content = clean_text(source.get("content", ""))
        url = str(source.get("url", "")).strip()

        source_parts.append(
            f"ARTICLE {index}\n"
            f"TITLE: {title}\n"
            f"CONTENT: {content[:1800]}\n"
            f"URL: {url}"
        )

    source_context = "\n\n".join(source_parts)

    if is_latest_model_request(query):
        prompt = f"""
You are the NEXUS AI News Editor.

User request:
{query}

Use ONLY the live articles below.

Return exactly ONE latest AI model that was actually released
or officially announced.

Do not confuse a funding round, partnership, conference,
regulation or opinion article with a model release.
Do not invent facts.
Do not include URLs.
Do not include a Sources section.

Format:
[Model name] — [company].
[Short factual explanation.]

LIVE ARTICLES:
{source_context}
"""
    else:
        prompt = f"""
You are the NEXUS AI News Editor.

User request:
{query}

Use ONLY the live articles below.

Return EXACTLY 5 numbered items:
1. ...
2. ...
3. ...
4. ...
5. ...

Each item must be one DISTINCT concrete AI development.
Combine duplicate coverage of the same event.
Do not invent facts.
Ignore unrelated stories, opinion pieces, generic articles,
webinars and ordinary conference announcements.
Do not include URLs.
Do not include a Sources section.
Do not add an introduction or conclusion.

LIVE ARTICLES:
{source_context}
"""

    result = await gemini_text(prompt)
    result = clean_ai_response(result)

    if result and not result.startswith("⚠️"):
        if is_latest_model_request(query):
            return result

        items = re.findall(
            r"(?m)^\s*[1-5][.)]\s+.+",
            result,
        )

        if len(items) == 5:
            return "\n".join(items)

    backup = await groq_text(prompt)
    backup = clean_ai_response(backup)

    if is_latest_model_request(query):
        return backup if backup and not backup.startswith("⚠️") else ""

    items = re.findall(
        r"(?m)^\s*[1-5][.)]\s+.+",
        backup,
    )

    return "\n".join(items) if len(items) == 5 else ""


def evidence_fallback(sources, latest_model=False):
    if not sources:
        return ""

    results = []
    seen = []

    for source in sources:
        title = clean_text(source.get("title", "AI development"))
        content = clean_text(source.get("content", ""))

        if not title:
            continue

        tokens = set(
            re.findall(
                r"[a-zA-Z0-9]+",
                title.lower(),
            )
        )

        duplicate = False

        for old in seen:
            overlap = len(tokens & old)
            similarity = overlap / max(
                len(tokens),
                len(old),
                1,
            )

            if similarity >= 0.60:
                duplicate = True
                break

        if duplicate:
            continue

        seen.append(tokens)

        if latest_model:
            combined = f"{title} {content}".lower()

            if any(
                term in combined
                for term in [
                    "new model",
                    "model released",
                    "model launch",
                    "unveiled",
                    "introduced",
                    "foundation model",
                    "open-weight",
                ]
            ):
                return (
                    f"{title}\n\n"
                    f"{content[:700]}"
                )
        else:
            summary = content[:350].strip()
            results.append(
                f"{len(results) + 1}. {title}"
                + (f": {summary}" if summary else "")
            )

            if len(results) == 5:
                return "\n".join(results)

    return ""


# -------------------- Main answer router --------------------

async def answer_user(query, images=None):
    started = time.perf_counter()
    images = images or []

    st.session_state.activity = [
        "Understanding request",
        "Building context",
    ]

    docs = retrieve_documents(query)

    document_context = "\n\n".join(
        f"[{d['name']}]\n{d['text'][:1200]}"
        for d in docs[:6]
    )

    dataset_context = build_dataset_context()
    memory_rows = load_memories(8)

    memory_context = "\n\n".join(
        f"User: {user}\nNEXUS: {assistant[:600]}"
        for user, assistant in memory_rows
    )

    research_result = {
        "sources": [],
        "error": "",
    }

    if should_research(query):
        st.session_state.activity.append("Deep research")

        research_result = await research(query)
        sources = research_result.get("sources", [])

        if sources:
            st.session_state.activity.append(
                f"Found {len(sources)} research results"
            )

            draft = await synthesize_research(
                query,
                sources,
            )

            if not draft:
                st.session_state.activity.append(
                    "Using evidence fallback"
                )
                draft = evidence_fallback(
                    sources,
                    latest_model=is_latest_model_request(query),
                )

            if not draft:
                draft = (
                    "⚠️ NEXUS found web results, but could not "
                    "produce a reliable synthesis from them."
                )
        else:
            draft = (
                "⚠️ NEXUS could not find enough relevant "
                "AI information from live research. "
                "Please try again."
            )
    else:
        base_prompt = f"""
You are NEXUS, an intelligent AI assistant.

Answer the user's request directly and accurately.
Use uploaded documents when relevant.
Use uploaded datasets when relevant.
Use memory only when relevant.
Do not reveal internal reasoning.

USER:
{query}

UPLOADED KNOWLEDGE:
{document_context or "(none)"}

UPLOADED DATASETS:
{dataset_context or "(none)"}

DATASET SUMMARY:
{dataset_summary()}

RECENT MEMORY:
{memory_context or "(none)"}
"""

        st.session_state.activity.append("AI response")

        draft = await gemini_text(
            base_prompt,
            images=images,
        )

    draft = clean_ai_response(draft)

    if not draft:
        draft = (
            "⚠️ NEXUS could not complete the request. "
            "Please try again."
        )

    st.session_state.activity.extend(
        [
            "Result checked",
            "Memory updated",
        ]
    )

    save_memory(query, draft)
    st.session_state.request_count += 1

    return {
        "answer": draft,
        "sources": research_result.get("sources", []),
        "latency": time.perf_counter() - started,
    }


# -------------------- Styling --------------------

st.markdown(
    """
<style>
#MainMenu, footer {visibility:hidden}

.block-container {
    max-width: 1050px;
    padding-top: 1rem;
    padding-bottom: 5rem;
}

.nexus-logo {
    font-size: 31px;
    font-weight: 800;
    letter-spacing: -1.5px;
}

.nexus-sub {
    color: #8d8d96;
    font-size: 14px;
    margin-top: 4px;
    margin-bottom: 18px;
}

.metric-pill {
    display: inline-block;
    border: 1px solid rgba(128,128,128,.28);
    border-radius: 999px;
    padding: 7px 12px;
    font-size: 12px;
    margin-right: 5px;
    margin-bottom: 6px;
}

[data-testid="stChatMessageAvatar"] {
    display: none;
}

div[data-testid="stChatInput"] {
    border-radius: 18px;
}

div[data-testid="stChatInput"] textarea {
    min-height: 56px;
}
</style>
""",
    unsafe_allow_html=True,
)


# -------------------- Sidebar --------------------

with st.sidebar:
    st.markdown(
        '<div class="nexus-logo">✦ NEXUS</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="nexus-sub">Adaptive agentic workspace</div>',
        unsafe_allow_html=True,
    )

    if st.button(
        "New conversation",
        use_container_width=True,
    ):
        st.session_state.messages = []
        st.session_state.activity = []
        st.rerun()

    st.divider()
    st.markdown("### Connections")

    st.write(
        ("🟢" if GEMINI_API_KEY else "⚪")
        + " Gemini"
    )
    st.write(
        ("🟢" if TAVILY_API_KEY else "⚪")
        + " Tavily"
    )
    st.write(
        ("🟢" if GROQ_API_KEY else "⚪")
        + " Groq"
    )

    st.divider()
    st.markdown("### Persistent memory")

    memory_count = len(load_memories(100000))
    st.caption(f"{memory_count} saved interactions")

    if st.button(
        "Clear persistent memory",
        use_container_width=True,
    ):
        if clear_memories():
            st.success("Memory cleared.")
            st.rerun()
        else:
            st.error("Could not clear memory.")


# -------------------- Main header --------------------

st.markdown(
    '<div class="nexus-logo">✦ NEXUS</div>',
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="nexus-sub">'
    'Research, analyze, reason, create, and work with your knowledge.'
    '</div>',
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f'<span class="metric-pill">Model: {MODEL}</span>',
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f'<span class="metric-pill">'
        f'Memory: {len(load_memories(100000))}'
        f'</span>',
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f'<span class="metric-pill">'
        f'Knowledge: {len(st.session_state.documents)}'
        f'</span>',
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f'<span class="metric-pill">'
        f'Requests: {st.session_state.request_count}'
        f'</span>',
        unsafe_allow_html=True,
    )


# -------------------- Conversation --------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        for image in message.get("images", []):
            st.image(image, width=220)

        st.markdown(message["content"])

        sources = message.get("sources", [])

        if sources:
            with st.expander("Sources"):
                for source in sources:
                    title = source.get(
                        "title",
                        "Source",
                    )
                    url = source.get(
                        "url",
                        "",
                    )

                    st.markdown(f"**{title}**")

                    if url:
                        st.markdown(
                            f"[Open source]({url})"
                        )


if st.session_state.activity:
    with st.expander(
        "NEXUS activity",
        expanded=False,
    ):
        for item in st.session_state.activity:
            st.write("•", item)


# -------------------- Chat input --------------------

try:
    chat_value = st.chat_input(
        "Message NEXUS...",
        accept_file=True,
        file_type=[
            "pdf",
            "txt",
            "md",
            "csv",
            "png",
            "jpg",
            "jpeg",
            "webp",
        ],
    )
except TypeError:
    chat_value = st.chat_input(
        "Message NEXUS..."
    )


if chat_value:
    if hasattr(chat_value, "text"):
        user_text = chat_value.text or ""
        uploaded_files = list(
            chat_value.files or []
        )
    else:
        user_text = str(chat_value)
        uploaded_files = []

    attached_images = index_files(
        uploaded_files
    )

    if not user_text and uploaded_files:
        user_text = (
            "Please analyze the attached file(s)."
        )

    if not user_text:
        st.stop()

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_text,
            "images": [
                image
                for _, image in attached_images
            ],
        }
    )

    with st.chat_message("user"):
        for _, image in attached_images:
            st.image(image, width=260)

        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.status(
            "NEXUS is working...",
            expanded=False,
        ):
            try:
                result = asyncio.run(
                    answer_user(
                        user_text,
                        attached_images,
                    )
                )
            except Exception as exc:
                result = {
                    "answer": (
                        "⚠️ NEXUS encountered an unexpected "
                        f"error: {type(exc).__name__}: {exc}"
                    ),
                    "sources": [],
                    "latency": 0,
                }

        st.markdown(result["answer"])

        if result["sources"]:
            with st.expander("Sources"):
                for source in result["sources"]:
                    title = source.get(
                        "title",
                        "Source",
                    )
                    url = source.get(
                        "url",
                        "",
                    )

                    st.markdown(
                        f"**{title}**"
                    )

                    if url:
                        st.markdown(
                            f"[Open source]({url})"
                        )

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": result["answer"],
                "sources": result["sources"],
            }
        )

    st.rerun()

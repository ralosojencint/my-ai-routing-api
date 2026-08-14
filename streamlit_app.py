import os, re, json, sqlite3, asyncio, time, io, base64
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
# NEXUS — SINGLE FILE
# Chat + inline attachments + memory + document knowledge
# ============================================================

st.set_page_config(page_title="NEXUS", page_icon="✦", layout="wide")

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

MODEL = "gemini-3.5-flash"

# -------------------- Persistent memory --------------------

DB_PATH = Path("nexus_memory.db")

def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at REAL NOT NULL,
            user_text TEXT NOT NULL,
            assistant_text TEXT NOT NULL
        )
    """)
    con.commit()
    return con

def save_memory(user_text, assistant_text):
    try:
        con = db()
        con.execute(
            "INSERT INTO memories(created_at,user_text,assistant_text) VALUES(?,?,?)",
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
            "SELECT user_text, assistant_text FROM memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        con.close()
        return list(reversed(rows))
    except Exception:
        return []

# -------------------- Session state --------------------

if "messages" not in st.session_state:
    st.session_state.messages = []
if "documents" not in st.session_state:
    st.session_state.documents = []
if "datasets" not in st.session_state:
    st.session_state.datasets = []
if "request_count" not in st.session_state:
    st.session_state.request_count = 0
if "activity" not in st.session_state:
    st.session_state.activity = []

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
    if not GROQ_API_KEY:
        return None

    if Groq is None:
        return None

    try:
        return Groq(api_key=GROQ_API_KEY)
    except Exception as exc:
        st.session_state["groq_client_error"] = str(exc)
        return None



async def groq_text(prompt, images=None):
    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY is missing from Streamlit Secrets."

    if Groq is None:
        return "⚠️ Groq package is not installed."

    try:
        client = groq_client()
        if client is None:
            return "⚠️ Groq client could not be initialized."

        response = await asyncio.to_thread(
            
            client.chat.completions.create,
            model="llama-3.3-70b-versatile",
            messages = [
    {
        "role": "system",
        "content": (
            "You are NEXUS, an intelligent AI assistant. "
            "Answer clearly, accurately, and directly."
        ),
    }
]

user_content = [
    {
        "type": "text",
        "text": prompt,
    }
]

for _, image in images or []:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

    user_content.append({
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{encoded}"
        }
    })

messages.append({
    "role": "user",
    "content": user_content,
})
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        if not response.choices:
            return "⚠️ Groq returned no choices."

        answer = response.choices[0].message.content

        if not answer:
            return "⚠️ Groq returned an empty response."

        return answer

    except Exception as exc:
        return f"⚠️ GROQ API ERROR: {exc}"
        
# -------------------- File handling --------------------

def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()

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

def read_uploaded_file(uploaded):
    name = uploaded.name
    ext = Path(name).suffix.lower()

    if ext == ".pdf":
        if PdfReader is None:
            return "", "PDF reader is unavailable."
        reader = PdfReader(uploaded)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        return text, None

    if ext in {".txt", ".md"}:
        return uploaded.getvalue().decode("utf-8", errors="replace"), None

    if ext == ".csv":
        df = pd.read_csv(uploaded)
        st.session_state.datasets.append({"name": name, "data": df})
        return df.head(100).to_csv(index=False), None

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        # Images are handled directly by Gemini when attached to a prompt.
        return "", None

    return "", f"Unsupported file type: {ext}"

def index_files(files):
    attached_images = []

    for uploaded in files or []:
        ext = Path(uploaded.name).suffix.lower()

        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            if Image is not None:
                try:
                    attached_images.append(
                        (uploaded.name, Image.open(uploaded).convert("RGB"))
                    )
                except Exception as exc:
                    print(
                        f"NEXUS IMAGE ERROR: {uploaded.name}: {exc}",
                        flush=True
                    )
                    st.warning(
                        f"{uploaded.name}: couldn't be read as an image ({exc})."
                    )
            continue

        try:
            text, error = read_uploaded_file(uploaded)

            if error:
                st.warning(f"{uploaded.name}: {error}")
                continue

            if text:
                # Replace previous chunks for the same file in this session.
                st.session_state.documents = [
                    d for d in st.session_state.documents
                    if d["name"] != uploaded.name
                ]

                for i, chunk in enumerate(make_chunks(text)):
                    st.session_state.documents.append({
                        "name": uploaded.name,
                        "chunk": i,
                        "text": chunk,
                    })

        except Exception as exc:
            st.warning(f"{uploaded.name}: {exc}")

    return attached_images

def retrieve_documents(query, limit=8):
    terms = set(re.findall(r"[a-zA-Z0-9_]+", query.lower()))
    scored = []

    for doc in st.session_state.documents:
        words = Counter(re.findall(r"[a-zA-Z0-9_]+", doc["text"].lower()))
        score = sum(words[t] for t in terms)
        if score:
            scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:limit]]

# -------------------- Agents --------------------
 
async def gemini_text(prompt, images=None):
    client = gemini_client()

    if client is None:
        return "⚠️ Gemini is not connected. Add GEMINI_API_KEY in Streamlit Secrets."

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

            return response.text or "I received no text response."

        except Exception as exc:
            error_text = str(exc).lower()

            if (
                "429" in error_text
                or "resource_exhausted" in error_text
                or "quota" in error_text
                or "rate limit" in error_text
            ):
                if attempt < max_retries:
                    wait_time = 5 * (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue

                if images:
                    return (
                        "⚠️ Gemini is currently rate-limited, "
                        "so the attached image could not be analyzed. "
                        "Please try again in a moment."
                    )

                return await groq_text(prompt)

            if (
                "503" in error_text
                or "service unavailable" in error_text
                or "unavailable" in error_text
            ):
                if attempt < max_retries:
                    wait_time = 3 * (attempt + 1)
                    await asyncio.sleep(wait_time)
                    continue

                return (
                    "⚠️ **Gemini is temporarily unavailable.**\n\n"
                    "Please try your message again in a moment."
                )

            return f"⚠️ Gemini couldn't complete the request: {exc}"

    return "⚠️ NEXUS couldn't complete the request. Please try again."
async def research(query):
    client = tavily_client()
    if client is None:
        return {"answer": "", "sources": []}

    try:
        result = await asyncio.to_thread(
            client.search,
            query=query,
            search_depth="advanced",
            max_results=6,
            include_answer=True,
        )
        return {
            "answer": result.get("answer", ""),
            "sources": result.get("results", []),
        }
    except Exception as exc:
        return {"answer": f"Research error: {exc}", "sources": []}

def should_research(query):
    q = query.lower()
    return bool(TAVILY_API_KEY) and any(
        word in q for word in
        ["latest", "today", "current", "news", "recent", "research", "2026"]
    )

async def answer_user(query, images=None):
    started = time.perf_counter()
    st.session_state.activity = ["Understanding request", "Building plan"]

    docs = retrieve_documents(query)
    document_context = "\n\n".join(
        f"[{d['name']}]\n{d['text']}" for d in docs
    )

    memories = load_memories()
    memory_context = "\n\n".join(
        f"User: {u}\nNEXUS: {a}" for u, a in memories
    )

    base_prompt = f"""
You are NEXUS, an agentic research and reasoning workspace.

Answer the user's request directly and accurately.
Use uploaded documents when relevant.
Use memory only when it is relevant.
Do not claim that you performed an external action unless you actually did.

USER:
{query}

RELEVANT UPLOADED KNOWLEDGE:
{document_context or "(none)"}

RECENT PERSISTENT MEMORY:
{memory_context or "(none)"}
"""

    jobs = [gemini_text(base_prompt, images=images)]

    if should_research(query):
        jobs.append(research(query))
        st.session_state.activity.append("Deep research")

    results = await asyncio.gather(*jobs, return_exceptions=True)

    draft = ""
    research_result = {"answer": "", "sources": []}

    for result in results:
        if isinstance(result, dict):
            research_result = result
        elif isinstance(result, str):
            draft = result

    if research_result["answer"] or research_result["sources"]:
        st.session_state.activity.append("Research synthesis")

        source_context = "\n\n".join(
    f"Title: {source.get('title', 'Untitled')}\n"
    f"URL: {source.get('url', '')}\n"
    f"Content: {source.get('content', '')[:2500]}"
    for source in research_result["sources"][:6]
)

        draft = await gemini_text(
            f"""
You are NEXUS performing research synthesis.

Answer the user's request using the Tavily research evidence below.

IMPORTANT RULES FOR CURRENT / LATEST / RECENT QUESTIONS:
- Prioritize the newest information in the provided sources.
- Pay close attention to publication dates and event dates.
- Do not present old information as current.
- If a source is from an older year, clearly identify it as historical/background information.
- Prefer recent primary sources and reputable news sources when available.
- Do not use your own prior knowledge to override the provided research.
- Do not invent facts, dates, sources, URLs, citations, or publication details.
- Do not create a "Sources" section in your answer.
- Do not output source URLs or markdown links. The NEXUS interface will display the verified Tavily sources separately.
- If the provided research does not contain enough recent information, say so instead of guessing.
- Answer the user's actual question directly before giving background context.
USER REQUEST:
{query}

TAVILY RESEARCH SUMMARY:
{research_result.get('answer', '')}

TAVILY SOURCES:
{source_context or "(no individual sources returned)"}

INITIAL ANSWER:
{draft}
"""
        )

    st.session_state.activity.extend([
        "Result checked",
        "Memory updated",
    ])

    save_memory(query, draft)
    st.session_state.request_count += 1

    return {
        "answer": draft,
        "sources": research_result.get("sources", []),
        "latency": time.perf_counter() - started,
    }

# -------------------- Styling --------------------

st.markdown("""
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
""", unsafe_allow_html=True)

# -------------------- Sidebar --------------------

with st.sidebar:
    st.markdown('<div class="nexus-logo">✦ NEXUS</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="nexus-sub">Adaptive agentic workspace</div>',
        unsafe_allow_html=True
    )

    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.markdown("### Connections")
    st.write(("🟢" if GEMINI_API_KEY else "⚪") + " Gemini")
    st.write(("🟢" if TAVILY_API_KEY else "⚪") + " Tavily")
    st.write(("🟢" if GROQ_API_KEY else "⚪") + " Groq")

    st.divider()
    st.markdown("### Persistent memory")
    st.caption(f"{len(load_memories(100000))} saved interactions")

    if st.button("Clear persistent memory", use_container_width=True):
        con = db()
        con.execute("DELETE FROM memories")
        con.commit()
        con.close()
        st.success("Memory cleared.")

# -------------------- Main header --------------------

st.markdown('<div class="nexus-logo">✦ NEXUS</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="nexus-sub">Research, analyze, reason, create, and work with your knowledge.</div>',
    unsafe_allow_html=True
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(
        '<span class="metric-pill">Model: gemini-3.5-flash</span>',
        unsafe_allow_html=True
    )
with c2:
    st.markdown(
        f'<span class="metric-pill">Memory: {len(load_memories(100000))}</span>',
        unsafe_allow_html=True
    )
with c3:
    st.markdown(
        f'<span class="metric-pill">Knowledge: {len(st.session_state.documents)}</span>',
        unsafe_allow_html=True
    )
with c4:
    st.markdown(
        f'<span class="metric-pill">Requests: {st.session_state.request_count}</span>',
        unsafe_allow_html=True
    )

# -------------------- Conversation --------------------

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if message.get("images"):
            for image in message["images"]:
                st.image(image, width=220)

        st.markdown(message["content"])

        if message.get("sources"):
            with st.expander("Sources"):
                for source in message["sources"]:
                    title = source.get("title", "Source")
                    url = source.get("url", "")

                    st.markdown(f"**{title}**")

                    if url:
                        st.markdown(url)

if st.session_state.activity:
    with st.expander("NEXUS activity", expanded=False):
        for item in st.session_state.activity:
            st.write("•", item)

# -------------------- INLINE CHAT ATTACHMENTS --------------------
# This is the key fix: Streamlit's native chat input owns the attachment
# button, so files no longer appear in a separate upload box/header.

try:
    chat_value = st.chat_input(
        "Message NEXUS...",
        accept_file=True,
        file_type=[
            "pdf", "txt", "md", "csv",
            "png", "jpg", "jpeg", "webp"
        ],
    )
except TypeError:
    # Older Streamlit fallback. Upgrade via requirements.txt.
    chat_value = st.chat_input("Message NEXUS...")

if chat_value:
    # Newer Streamlit returns a ChatInputValue with .text and .files.
    if hasattr(chat_value, "text"):
        user_text = chat_value.text or ""
        uploaded_files = list(chat_value.files or [])
    else:
        user_text = str(chat_value)
        uploaded_files = []

    attached_images = index_files(uploaded_files)

    if not user_text and uploaded_files:
        user_text = "Please analyze the attached file(s)."
        
    if not user_text:
        st.stop()

    st.session_state.messages.append({
        "role": "user",
        "content": user_text,
        "images": [image for _, image in attached_images],
    })

    with st.chat_message("user"):
        for _, image in attached_images:
            st.image(image, width=260)
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.status("NEXUS is working...", expanded=False):
            result = asyncio.run(answer_user(user_text, attached_images))

        st.markdown(result["answer"])

        if result["sources"]:
            with st.expander("Sources"):
                for source in result["sources"]:
                    title = source.get("title", "Source")
                    url = source.get("url", "")
                    st.markdown(f"**{title}**")
                    if url:
                        st.markdown(url)

        st.session_state.messages.append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
    })

    st.rerun()

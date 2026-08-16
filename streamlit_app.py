import os, re, json, sqlite3, asyncio, time, io, base64
from pathlib import Path
from collections import Counter
from datetime import date, datetime, timezone

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

st.set_page_config(page_title="NEXUS", page_icon="✦", layout="wide")

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

for key, default in {
    "messages": [],
    "documents": [],
    "datasets": [],
    "request_count": 0,
    "activity": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

def clean_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def clean_ai_response(text):
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<thinking>.*$", "", text, flags=re.DOTALL | re.IGNORECASE)
    return text.strip()

async def groq_text(prompt, images=None):
    client = groq_client()
    if client is None:
        if not GROQ_API_KEY:
            return "⚠️ GROQ_API_KEY is missing from Streamlit Secrets."
        return "⚠️ Groq client could not be initialized."
    try:
        user_content = [{"type": "text", "text": str(prompt)[:12000]}]
        for _, image in images or []:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=85)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}
            })

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="qwen/qwen3.6-27b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NEXUS, an intelligent AI assistant. "
                        "Answer clearly, accurately and directly. "
                        "Do not reveal private chain-of-thought. "
                        "For images, describe only visible evidence. "
                        "Never invent names, identities, facts, or events."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        )
        if not response.choices:
            return "⚠️ Groq returned no choices."
        answer = clean_ai_response(response.choices[0].message.content or "")
        return answer or "⚠️ Groq returned an empty response."
    except Exception:
        return "⚠️ NEXUS is temporarily unable to complete the request. Please try again in a few minutes."

def make_chunks(text, size=1400, overlap=200):
    text = clean_text(text)
    if not text:
        return []
    result, start = [], 0
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
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return text, None

    if ext in {".txt", ".md"}:
        return uploaded.getvalue().decode("utf-8", errors="replace"), None

    if ext == ".csv":
        uploaded.seek(0)
        df = pd.read_csv(uploaded)
        st.session_state.datasets = [
            d for d in st.session_state.datasets if d["name"] != name
        ]
        st.session_state.datasets.append({"name": name, "data": df})
        return df.head(100).to_csv(index=False), None

    if ext in {".png", ".jpg", ".jpeg", ".webp"}:
        return "", None

    return "", f"Unsupported file type: {ext}"

def index_files(files):
    attached_images = []
    for uploaded in files or []:
        ext = Path(uploaded.name).suffix.lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp"}:
            if Image is not None:
                try:
                    uploaded.seek(0)
                    attached_images.append((uploaded.name, Image.open(uploaded).convert("RGB")))
                except Exception as exc:
                    st.warning(f"{uploaded.name}: couldn't be read as an image ({exc}).")
            continue
        try:
            text, error = read_uploaded_file(uploaded)
            if error:
                st.warning(f"{uploaded.name}: {error}")
                continue
            if text:
                st.session_state.documents = [
                    d for d in st.session_state.documents if d["name"] != uploaded.name
                ]
                for i, chunk in enumerate(make_chunks(text)):
                    st.session_state.documents.append({
                        "name": uploaded.name, "chunk": i, "text": chunk
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

def build_dataset_context():
    parts = []
    for d in st.session_state.datasets:
        df = d["data"]
        parts.append(
            f"[{d['name']}]\n"
            f"Columns: {', '.join(map(str, df.columns))}\n"
            f"Rows: {len(df)}\n"
            f"Data:\n{df.head(100).to_csv(index=False)}"
        )
    return "\n\n".join(parts)

def dataset_summary():
    if not st.session_state.datasets:
        return "(none)"
    return "\n\n".join(
        f"Dataset: {d['name']}\n"
        f"Columns: {', '.join(map(str, d['data'].columns))}\n"
        f"Rows: {len(d['data'])}"
        for d in st.session_state.datasets
    )

async def gemini_text(prompt, images=None):
    client = gemini_client()
    if client is None:
        return "⚠️ Gemini is not connected. Add GEMINI_API_KEY in Streamlit Secrets."

    contents = [prompt] + [image for _, image in images or []]

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=contents,
            )
            answer = clean_ai_response(getattr(response, "text", "") or "")
            if answer:
                return answer
            return await groq_text(prompt, images)
        except Exception as exc:
            error_text = str(exc).lower()
            if any(x in error_text for x in ["429", "resource_exhausted", "quota", "rate limit"]):
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                return await groq_text(prompt, images)
            if any(x in error_text for x in ["404", "not_found", "not found"]):
                return await groq_text(prompt, images)
            if "503" in error_text or "service unavailable" in error_text:
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
            return await groq_text(prompt, images)
    return await groq_text(prompt, images)

# -------------------- Targeted research fix --------------------

RESEARCH_AI_TERMS = {
    "artificial intelligence", "machine learning", "generative ai",
    "ai model", "ai system", "ai agent", "ai research", "ai chip",
    "ai hardware", "ai infrastructure", "ai regulation", "ai policy",
    "ai safety", "ai startup", "ai coding", "ai software", "openai",
    "anthropic", "google deepmind", "gemini", "meta ai", "microsoft",
    "nvidia", "mistral", "robotics", "large language model", "llm",
    "foundation model", "open-weight", "open source model", "agentic",
}

RESEARCH_NOISE_TERMS = {
    "horoscope", "weather", "sports", "flight", "admissions", "insurance",
    "real estate", "celebrity", "recipe", "travel", "cosmetics",
    "veterinary", "murder", "arrest", "crime", "criminal", "police",
    "stock market", "price target", "investor outlook", "webinar",
    "opinion", "editorial",
}

DEVELOPMENT_TERMS = {
    "launched", "launches", "released", "release", "unveiled",
    "announced", "announces", "introduced", "deployed", "deployment",
    "partnered", "partnership", "acquired", "acquisition", "funding",
    "raised", "investment", "model", "research", "breakthrough",
    "regulation", "legislation", "chips", "data center", "infrastructure",
    "robotics", "agent", "update", "available", "general availability",
}

PRIMARY_DOMAINS = {
    "openai.com", "anthropic.com", "blog.google", "deepmind.google",
    "ai.meta.com", "about.fb.com", "nvidia.com", "microsoft.com",
    "mistral.ai", "huggingface.co", "deepseek.com", "z.ai",
}

def source_domain(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1).lower().removeprefix("www.") if m else ""

def source_date(source):
    raw = str(source.get("published_date") or source.get("date") or "").strip()
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None

def is_relevant_ai_source(source):
    combined = f"{clean_text(source.get('title',''))} {clean_text(source.get('content',''))}".lower()
    if not any(term in combined for term in RESEARCH_AI_TERMS):
        return False
    if any(term in combined for term in RESEARCH_NOISE_TERMS):
        return False
    return len(clean_text(source.get("title",""))) >= 10 and len(clean_text(source.get("content",""))) >= 100

def research_score(source, today):
    title = clean_text(source.get("title",""))
    content = clean_text(source.get("content",""))
    combined = f"{title} {content}".lower()
    score = sum(2 for t in DEVELOPMENT_TERMS if t in combined)
    score += sum(4 for t in DEVELOPMENT_TERMS if t in title.lower())
    if len(content) >= 500: score += 2
    if len(content) >= 1000: score += 2
    if source_domain(source.get("url","")) in PRIMARY_DOMAINS: score += 8
    published = source_date(source)
    if published:
        age = (today - published).days
        if age == 0: score += 20
        elif age == 1: score += 12
        elif age <= 3: score += 6
        elif age <= 7: score += 2
        else: score -= 20
    return score

def event_duplicate(title, content, seen):
    tokens = set(re.findall(r"[a-zA-Z0-9]+", f"{title} {content[:1000]}".lower()))
    tokens -= {"ai","artificial","intelligence","technology","new","latest","today","news","company","industry","system","report","reports","says","said","will","could","may","according","model"}
    if not tokens:
        return True
    for old in seen:
        if len(tokens & old) / max(len(tokens), len(old), 1) >= 0.45:
            return True
    seen.append(tokens)
    return False

async def research(query):
    client = tavily_client()
    if client is None:
        return {"sources": [], "error": "Tavily client is not available. Check TAVILY_API_KEY."}

    today = date.today()
    queries = [
        f"{query} latest AI developments today",
        f"AI artificial intelligence latest developments {today.isoformat()}",
        f"AI model release launch announcement {today.isoformat()}",
        f"OpenAI Anthropic Google Gemini Meta AI latest {today.isoformat()}",
        f"NVIDIA AI chips infrastructure latest {today.isoformat()}",
        f"AI agents robotics latest development {today.isoformat()}",
        f"AI research breakthrough latest {today.isoformat()}",
        f"AI regulation policy government latest {today.isoformat()}",
    ]

    all_sources = []
    for q in queries:
        try:
            result = await asyncio.to_thread(
                client.search, query=q, search_depth="advanced",
                topic="news", time_range="day", max_results=8,
                include_answer=False,
            )
            all_sources.extend(x for x in result.get("results", []) if isinstance(x, dict))
        except Exception:
            continue

    # Controlled week fallback only when today's feed is sparse.
    if len(all_sources) < 10:
        for q in queries[:5]:
            try:
                result = await asyncio.to_thread(
                    client.search, query=q, search_depth="advanced",
                    topic="news", time_range="week", max_results=6,
                    include_answer=False,
                )
                all_sources.extend(x for x in result.get("results", []) if isinstance(x, dict))
            except Exception:
                continue

    unique, seen_urls = [], set()
    for source in all_sources:
        url = str(source.get("url","")).strip()
        key = url.rstrip("/").lower()
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        if is_relevant_ai_source(source):
            unique.append(source)

    ranked = sorted(unique, key=lambda s: research_score(s, today), reverse=True)
    final, seen_events = [], []
    for source in ranked:
        if event_duplicate(clean_text(source.get("title","")), clean_text(source.get("content","")), seen_events):
            continue
        final.append(source)
        if len(final) >= 15:
            break

    return {"sources": final, "error": ""}

def should_research(query):
    q = query.lower()
    return bool(TAVILY_API_KEY) and any(
        word in q for word in [
            "latest", "today", "current", "news", "recent",
            "breaking", "developments", "what happened", "this week",
        ]
    )

def is_latest_model_request(query):
    q = query.lower()
    return any(x in q for x in [
        "latest ai model", "latest model", "newest ai model",
        "new ai model", "model released", "model launch",
    ])

async def synthesize_research(query, sources):
    if not sources:
        return ""
    articles = "\n\n".join(
        f"ARTICLE {i}\nTITLE: {clean_text(s.get('title','Untitled'))}\n"
        f"DATE: {s.get('published_date','Unknown')}\n"
        f"CONTENT: {clean_text(s.get('content',''))[:1800]}\n"
        f"URL: {s.get('url','')}"
        for i, s in enumerate(sources[:12], 1)
    )

    if is_latest_model_request(query):
        prompt = f"""You are the NEXUS AI News Editor.

User request:
{query}

LIVE RESEARCH:
{articles}

Return exactly ONE latest AI model that is actually supported by the supplied articles.

Rules:
- Prefer an actual release or official announcement.
- Prefer today's dated evidence.
- Do not confuse funding, partnerships, conferences, regulation, commentary, or marketing with a model release.
- If the evidence does not establish a model release, say that clearly instead of guessing.
- Do not invent facts.
- No URLs, Sources section, introduction, or conclusion.

Format:
[Model name] — [company].
[2-3 concise factual sentences.]
"""
    else:
        prompt = f"""You are the NEXUS AI News Editor.

User request:
{query}

LIVE RESEARCH:
{articles}

Return EXACTLY 5 numbered AI developments.

Rules:
1. Each item must be a distinct concrete event.
2. Prefer today, then yesterday, then the most recent reliable evidence.
3. Combine duplicate coverage of the same event.
4. Reject unrelated stories, stale stories, generic company pages, opinion pieces, and stock-market commentary.
5. Prefer primary sources and reputable reporting.
6. Do not invent facts.
7. Use only the supplied research.
8. No URLs, Sources section, introduction, or conclusion.
"""
    result = clean_ai_response(await gemini_text(prompt))
    if is_latest_model_request(query):
        return result if result and not result.startswith("⚠️") else clean_ai_response(await groq_text(prompt))

    items = re.findall(r"(?m)^\s*[1-5][.)]\s+.+", result or "")
    if len(items) == 5:
        return "\n".join(items)

    backup = clean_ai_response(await groq_text(prompt))
    items = re.findall(r"(?m)^\s*[1-5][.)]\s+.+", backup or "")
    return "\n".join(items) if len(items) == 5 else ""

def evidence_fallback(sources):
    results, seen = [], []
    for source in sources:
        title = clean_text(source.get("title","AI development"))
        content = clean_text(source.get("content",""))
        tokens = set(re.findall(r"[a-zA-Z0-9]+", title.lower()))
        if any(len(tokens & old) / max(len(tokens), len(old), 1) >= 0.6 for old in seen):
            continue
        seen.append(tokens)
        results.append(f"{len(results)+1}. **{title}** — {content[:350]}")
        if len(results) == 5:
            return "\n".join(results)
    return ""

async def answer_user(query, images=None):
    started = time.perf_counter()
    images = images or []
    st.session_state.activity = ["Understanding request", "Building context"]

    docs = retrieve_documents(query)
    document_context = "\n\n".join(f"[{d['name']}]\n{d['text'][:1200]}" for d in docs[:6])
    dataset_context = build_dataset_context()
    memory_context = "\n\n".join(
        f"User: {u}\nNEXUS: {a[:600]}" for u, a in load_memories(8)
    )

    research_result = {"sources": [], "error": ""}
    if should_research(query):
        st.session_state.activity.append("Deep research")
        research_result = await research(query)
        sources = research_result["sources"]
        if sources:
            st.session_state.activity.append(f"Found {len(sources)} relevant sources")
            draft = await synthesize_research(query, sources)
            if not draft:
                st.session_state.activity.append("Using evidence fallback")
                draft = evidence_fallback(sources)
            if not draft:
                draft = "⚠️ NEXUS found web results, but could not produce a reliable synthesis from them."
        else:
            draft = "⚠️ NEXUS could not find enough relevant current AI information from live research. Please try again."
    else:
        prompt = f"""You are NEXUS, an intelligent AI assistant.

Answer directly, accurately, and concisely.
Use uploaded documents and datasets when relevant.
Use memory only when relevant.
Do not reveal private chain-of-thought.
Do not invent facts.

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
        draft = await gemini_text(prompt, images=images)

    draft = clean_ai_response(draft) or "⚠️ NEXUS could not complete the request. Please try again."
    st.session_state.activity.extend(["Result checked", "Memory updated"])
    save_memory(query, draft)
    st.session_state.request_count += 1
    return {"answer": draft, "sources": research_result["sources"], "latency": time.perf_counter() - started}

st.markdown("""
<style>
#MainMenu, footer {visibility:hidden}
.block-container {max-width:1050px;padding-top:1rem;padding-bottom:5rem}
.nexus-logo {font-size:31px;font-weight:800;letter-spacing:-1.5px}
.nexus-sub {color:#8d8d96;font-size:14px;margin-top:4px;margin-bottom:18px}
.metric-pill {display:inline-block;border:1px solid rgba(128,128,128,.28);border-radius:999px;padding:7px 12px;font-size:12px;margin-right:5px;margin-bottom:6px}
[data-testid="stChatMessageAvatar"] {display:none}
div[data-testid="stChatInput"] {border-radius:18px}
div[data-testid="stChatInput"] textarea {min-height:56px}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="nexus-logo">✦ NEXUS</div>', unsafe_allow_html=True)
    st.markdown('<div class="nexus-sub">Adaptive agentic workspace</div>', unsafe_allow_html=True)

    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.activity = []
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

st.markdown('<div class="nexus-logo">✦ NEXUS</div>', unsafe_allow_html=True)
st.markdown('<div class="nexus-sub">Research, analyze, reason, create, and work with your knowledge.</div>', unsafe_allow_html=True)

c1,c2,c3,c4 = st.columns(4)
with c1: st.markdown(f'<span class="metric-pill">Model: {MODEL}</span>', unsafe_allow_html=True)
with c2: st.markdown(f'<span class="metric-pill">Memory: {len(load_memories(100000))}</span>', unsafe_allow_html=True)
with c3: st.markdown(f'<span class="metric-pill">Knowledge: {len(st.session_state.documents)}</span>', unsafe_allow_html=True)
with c4: st.markdown(f'<span class="metric-pill">Requests: {st.session_state.request_count}</span>', unsafe_allow_html=True)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        for image in message.get("images", []):
            st.image(image, width=220)
        st.markdown(message["content"])
        if message.get("sources"):
            with st.expander("Sources"):
                for source in message["sources"]:
                    title = source.get("title","Source")
                    url = source.get("url","")
                    st.markdown(f"**{title}**")
                    if url:
                        st.markdown(f"[Open source]({url})")

if st.session_state.activity:
    with st.expander("NEXUS activity", expanded=False):
        for item in st.session_state.activity:
            st.write("•", item)

try:
    chat_value = st.chat_input(
        "Message NEXUS...", accept_file=True,
        file_type=["pdf","txt","md","csv","png","jpg","jpeg","webp"],
    )
except TypeError:
    chat_value = st.chat_input("Message NEXUS...")

if chat_value:
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
        "role":"user","content":user_text,
        "images":[image for _,image in attached_images],
    })

    with st.chat_message("user"):
        for _, image in attached_images:
            st.image(image, width=260)
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.status("NEXUS is working...", expanded=False):
            try:
                result = asyncio.run(answer_user(user_text, attached_images))
            except Exception as exc:
                result = {
                    "answer": f"⚠️ NEXUS encountered an unexpected error: {type(exc).__name__}: {exc}",
                    "sources": [], "latency": 0,
                }
        st.markdown(result["answer"])

        if result["sources"]:
            with st.expander("Sources"):
                for source in result["sources"]:
                    title = source.get("title","Source")
                    url = source.get("url","")
                    st.markdown(f"**{title}**")
                    if url:
                        st.markdown(f"[Open source]({url})")

        st.session_state.messages.append({
            "role":"assistant","content":result["answer"],
            "sources":result["sources"],
        })

    st.rerun()

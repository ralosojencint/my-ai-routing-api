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

# ============================================================
# NEXUS AI — STABLE SINGLE FILE
# Chat + attachments + memory + datasets + documents + research
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

for key, default in {
    "messages": [],
    "documents": [],
    "datasets": [],
    "request_count": 0,
    "activity": [],
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

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

async def groq_text(prompt, images=None):
    client = groq_client()
    if client is None:
        if not GROQ_API_KEY:
            return "⚠️ GROQ_API_KEY is missing from Streamlit Secrets."
        return "⚠️ Groq client could not be initialized."

    try:
        user_content = [{"type": "text", "text": prompt[:7000]}]

        for _, image in images or []:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG")
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}
            })

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NEXUS, an intelligent AI assistant. "
                        "Answer clearly, accurately and directly. "
                        "Do not reveal private chain-of-thought. "
                        "For images, describe only visible evidence. "
                        "Never guess a person, character, series, or identity unless the user provides it or it is visibly supported."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
        )

        if not response.choices:
            return "⚠️ Groq returned no choices."

        answer = clean_ai_response(response.choices[0].message.content or "")
        if answer:
            return answer

        if images:
            retry_content = [{
                "type": "text",
                "text": (
                    "Describe the attached image using only visible details. "
                    "Identify the main objects, colors, clothing, setting, and expression. "
                    "Do not guess names or identities. Return a concise description."
                ),
            }]
            for _, image in images:
                buffer = io.BytesIO()
                image.convert("RGB").save(buffer, format="JPEG", quality=80)
                encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                retry_content.append({"type":"image_url", "image_url":{"url":"data:image/jpeg;base64," + encoded}})
            retry = await asyncio.to_thread(
                client.chat.completions.create,
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role":"system", "content":"Describe images accurately. Do not invent identities."},
                    {"role":"user", "content":retry_content},
                ],
            )
            if retry.choices:
                retry_answer = clean_ai_response(retry.choices[0].message.content or "")
                if retry_answer:
                    return retry_answer

        return "⚠️ Groq returned an empty response."

    except Exception:
        return (
            "⚠️ NEXUS is temporarily unable to complete "
            "the request. Please try again in a few minutes."
        )

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
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
        return text, None

    if ext in {".txt", ".md"}:
        return uploaded.getvalue().decode(
            "utf-8", errors="replace"
        ), None

    if ext == ".csv":
        uploaded.seek(0)
        df = pd.read_csv(uploaded)

        st.session_state.datasets = [
            d for d in st.session_state.datasets
            if d["name"] != name
        ]

        st.session_state.datasets.append({
            "name": name,
            "data": df
        })

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
                    attached_images.append(
                        (
                            uploaded.name,
                            Image.open(uploaded).convert("RGB")
                        )
                    )
                except Exception as exc:
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
    terms = set(
        re.findall(r"[a-zA-Z0-9_]+", query.lower())
    )
    scored = []

    for doc in st.session_state.documents:
        words = Counter(
            re.findall(r"[a-zA-Z0-9_]+", doc["text"].lower())
        )
        score = sum(words[t] for t in terms)

        if score:
            scored.append((score, doc))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:limit]]

# -------------------- AI cleanup --------------------

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

    return text.strip()

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

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=contents,
            )
            return clean_ai_response(
                response.text or "I received no text response."
            )

        except Exception as exc:
            error_text = str(exc).lower()

            if any(x in error_text for x in [
                "429", "resource_exhausted", "quota", "rate limit"
            ]):
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                return await groq_text(prompt, images=images)

            if any(x in error_text for x in [
                "404", "not_found", "not found"
            ]):
                return await groq_text(prompt, images=images)

            if any(x in error_text for x in [
                "503", "service unavailable"
            ]):
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue

            return await groq_text(prompt, images=images)

    return "⚠️ NEXUS couldn't complete the request. Please try again."

# -------------------- Research helpers --------------------

RESEARCH_AI_TERMS = {
    "artificial intelligence", "artificial-intelligence",
    "machine learning", "generative ai", "ai model", "ai system",
    "ai agent", "ai research", "ai chip", "ai hardware",
    "ai infrastructure", "ai regulation", "ai policy", "ai safety",
    "ai startup", "ai coding", "ai software", "openai", "anthropic",
    "google deepmind", "gemini", "meta ai", "microsoft", "nvidia",
    "mistral", "z.ai", "robotics", "large language model", "llm",
    "foundation model", "open-weight", "open source model",
    "autonomous", "agentic",
}

RESEARCH_NOISE_TERMS = {
    "horoscope", "weather", "sports", "flight", "admissions",
    "insurance", "real estate", "celebrity", "recipe", "travel",
    "cosmetics", "veterinary", "petvivo", "murder", "arrest",
    "crime", "criminal", "police", "fbi", "stock market",
    "stock analysis", "price target", "investor outlook",
    "conference registration", "webinar", "opinion", "editorial",
}

DEVELOPMENT_TERMS = {
    "launched", "launches", "released", "release", "unveiled",
    "announced", "announces", "introduced", "deployed",
    "deployment", "partnered", "partnership", "acquired",
    "acquisition", "funding", "raised", "investment", "model",
    "research", "breakthrough", "regulation", "legislation",
    "chips", "data center", "infrastructure", "robotics", "agent",
    "update", "available", "general availability",
}

PRIMARY_DOMAINS = {
    "openai.com", "anthropic.com", "blog.google",
    "deepmind.google", "ai.meta.com", "about.fb.com",
    "nvidia.com", "microsoft.com", "mistral.ai",
    "qwenlm.ai", "huggingface.co", "deepseek.com",
    "z.ai",
}

def source_domain(url):
    match = re.search(r"https?://([^/]+)", url or "")
    if not match:
        return ""
    return match.group(1).lower().removeprefix("www.")

def source_date(source):
    raw = str(
        source.get("published_date")
        or source.get("date")
        or ""
    ).strip()

    if not raw:
        return None

    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if match:
        try:
            return date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            return None

    return None

def source_combined(source):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    return f"{title} {content}".lower()

def is_relevant_ai_source(source):
    combined = source_combined(source)

    if not any(term in combined for term in RESEARCH_AI_TERMS):
        return False

    if any(term in combined for term in RESEARCH_NOISE_TERMS):
        return False

    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))

    return len(title) >= 10 and len(content) >= 100

def research_score(source, today):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    combined = f"{title} {content}".lower()
    score = 0

    for term in DEVELOPMENT_TERMS:
        if term in combined:
            score += 2
        if term in title.lower():
            score += 4

    if len(content) >= 500:
        score += 2
    if len(content) >= 1000:
        score += 2

    domain = source_domain(source.get("url", ""))
    if domain in PRIMARY_DOMAINS:
        score += 8

    published = source_date(source)
    if published:
        age = (today - published).days
        if age == 0:
            score += 20
        elif age == 1:
            score += 12
        elif age <= 3:
            score += 6
        elif age <= 7:
            score += 2
        else:
            score -= 20

    return score

def distinct_event_duplicate(title, content, seen):
    tokens = set(
        re.findall(
            r"[a-zA-Z0-9]+",
            f"{title} {content[:1000]}".lower()
        )
    )

    generic = {
        "ai", "artificial", "intelligence", "technology",
        "new", "latest", "today", "news", "company",
        "industry", "system", "report", "reports", "says",
        "said", "will", "could", "may", "according", "model",
    }
    tokens -= generic

    if not tokens:
        return True

    for old in seen:
        overlap = len(tokens & old)
        similarity = overlap / max(len(tokens), len(old), 1)
        if similarity >= 0.45:
            return True

    seen.append(tokens)
    return False

# -------------------- Live research --------------------

async def research(query):
    client = tavily_client()

    if client is None:
        return {
            "sources": [],
            "error": "Tavily client is not available. Check TAVILY_API_KEY.",
        }

    today = date.today()
    date_text = today.isoformat()

    queries = [
        f"AI artificial intelligence latest developments {date_text}",
        f"AI model release launch announcement {date_text}",
        f"OpenAI Anthropic Google Gemini Meta AI latest {date_text}",
        f"NVIDIA AI chips infrastructure latest {date_text}",
        f"AI agents robotics latest development {date_text}",
        f"AI research breakthrough latest {date_text}",
        f"AI regulation policy government latest {date_text}",
    ]

    all_sources = []

    # First pass: today. This is the important freshness fix.
    for q in queries:
        try:
            result = await asyncio.to_thread(
                client.search,
                query=q,
                search_depth="advanced",
                topic="news",
                time_range="day",
                max_results=8,
                include_answer=False,
            )

            for item in result.get("results", []):
                all_sources.append(item)

        except Exception:
            continue

    # Second pass: week, only as a controlled fallback.
    # This prevents a totally empty result when today's news feed
    # is sparse, while scoring today's articles much higher.
    if len(all_sources) < 10:
        for q in queries[:5]:
            try:
                result = await asyncio.to_thread(
                    client.search,
                    query=q,
                    search_depth="advanced",
                    topic="news",
                    time_range="week",
                    max_results=6,
                    include_answer=False,
                )

                for item in result.get("results", []):
                    all_sources.append(item)

            except Exception:
                continue

    # URL deduplication.
    unique = []
    seen_urls = set()

    for source in all_sources:
        url = str(source.get("url", "")).strip()
        key = url.rstrip("/").lower()

        if not key or key in seen_urls:
            continue

        seen_urls.add(key)
        unique.append(source)

    filtered = [
        source for source in unique
        if is_relevant_ai_source(source)
    ]

    ranked = sorted(
        filtered,
        key=lambda source: research_score(source, today),
        reverse=True,
    )

    # Event-level deduplication.
    final = []
    seen_events = []

    for source in ranked:
        title = clean_text(source.get("title", ""))
        content = clean_text(source.get("content", ""))

        if distinct_event_duplicate(
            title, content, seen_events
        ):
            continue

        final.append(source)

        if len(final) >= 15:
            break

    return {
        "sources": final,
        "error": "",
    }

def should_research(query):
    q = query.lower()

    research_words = [
        "latest", "today", "current", "news", "recent",
        "breaking", "developments", "what happened",
    ]

    return bool(TAVILY_API_KEY) and any(
        word in q for word in research_words
    )

# -------------------- Main answer router --------------------

async def answer_user(query, images=None):
    started = time.perf_counter()

    st.session_state.activity = [
        "Understanding request",
        "Building context",
    ]

    docs = retrieve_documents(query)

    document_context = "\n\n".join(
        f"[{d['name']}]\n{d['text'][:1000]}"
        for d in docs[:6]
    )

    dataset_context = "\n\n".join(
        f"[{d['name']}]\n"
        f"Columns: {', '.join(str(c) for c in d['data'].columns)}\n"
        f"Rows: {len(d['data'])}\n"
        f"Data:\n{d['data'].head(100).to_csv(index=False)}"
        for d in st.session_state.datasets
    )

    memories = load_memories()

    memory_context = "\n\n".join(
        f"User: {u}\nNEXUS: {a[:500]}"
        for u, a in memories[-8:]
    )

    base_prompt = f"""
You are NEXUS, an intelligent AI assistant.

Answer the user's request directly and accurately.
Use uploaded documents and datasets when relevant.
Use memory only when relevant.
Do not reveal private chain-of-thought.

USER:
{query}

UPLOADED KNOWLEDGE:
{document_context or "(none)"}

UPLOADED DATASETS:
{dataset_context or "(none)"}

RECENT MEMORY:
{memory_context or "(none)"}
"""

    if should_research(query):
        st.session_state.activity.append("Deep research")

        research_result = await research(query)
        sources = research_result.get("sources", [])
        draft = ""

        q_lower = query.lower()
        asks_latest_model = any(
            phrase in q_lower
            for phrase in [
                "latest ai model", "latest model",
                "newest ai model", "new ai model",
                "model released", "model launch",
            ]
        )

        if sources:
            st.session_state.activity.append(
                f"Found {len(sources)} relevant sources"
            )

            evidence = []

            for i, source in enumerate(sources[:12], 1):
                evidence.append(
                    f"ARTICLE {i}\n"
                    f"TITLE: {clean_text(source.get('title', 'Untitled'))}\n"
                    f"DATE: {source.get('published_date', 'Unknown')}\n"
                    f"CONTENT: {clean_text(source.get('content', ''))[:1800]}\n"
                    f"URL: {source.get('url', '')}"
                )

            source_context = "\n\n".join(evidence)

            if asks_latest_model:
                synthesis_prompt = f"""
You are the NEXUS AI News Editor.

User request:
{query}

LIVE RESEARCH:
{source_context}

Return exactly ONE latest AI model that is supported by the
research.

Rules:
- Prefer an actual release or official announcement.
- Prefer today's dated evidence.
- Do not confuse funding, partnerships, conferences,
  regulation, commentary, or product marketing with a model release.
- If sources disagree, choose the most recent well-supported event.
- Use only the supplied research.
- Do not invent facts.
- No URLs.
- No Sources section.
- No introduction.
- No conclusion.

Format:
[Model name] — [company].
[2-3 sentence concise explanation.]
"""
            else:
                synthesis_prompt = f"""
You are the NEXUS AI News Editor.

User request:
{query}

LIVE RESEARCH:
{source_context}

Return EXACTLY 5 numbered AI developments.

Rules:
1. Use 1. through 5.
2. Each item must be a DISTINCT real event.
3. Prefer the newest events, especially today and yesterday.
4. Do not use articles from months or years ago unless the event
   itself is genuinely current.
5. Prefer primary sources and major reputable news sources.
6. Do not use sports/legal/stock/entertainment stories unless
   the AI event itself is the main subject.
7. Do not use generic company profile pages.
8. Do not repeat the same event reported by multiple outlets.
9. Do not invent facts.
10. Use only the supplied research.
11. No URLs.
12. No Sources section.
13. No introduction or conclusion.

Each item should be concise:
1. **Headline** — what happened and why it matters.
2. ...
"""

            st.session_state.activity.append("Research synthesis")

            synthesized = clean_ai_response(
                await gemini_text(synthesis_prompt)
            )

            if asks_latest_model:
                if synthesized and not synthesized.startswith("⚠️"):
                    draft = synthesized
            else:
                items = re.findall(
                    r"(?m)^\s*[1-5][.)]\s+.+",
                    synthesized or "",
                )
                if len(items) == 5:
                    draft = "\n".join(items)

            # Backup synthesis with Groq.
            if not draft:
                st.session_state.activity.append(
                    "Backup research synthesis"
                )

                backup_prompt = f"""
Create the requested answer using ONLY these live articles.

User request:
{query}

Requirements:
- If the user asks for 5 developments: exactly 5 numbered items.
- Each item must be a distinct current AI event.
- Prefer today's and yesterday's events.
- Reject stale, unrelated and duplicate stories.
- Do not invent facts.
- No URLs.
- No sources section.

LIVE ARTICLES:
{source_context}
"""

                backup = clean_ai_response(
                    await groq_text(backup_prompt)
                )

                if asks_latest_model:
                    if backup and not backup.startswith("⚠️"):
                        draft = backup
                else:
                    items = re.findall(
                        r"(?m)^\s*[1-5][.)]\s+.+",
                        backup or "",
                    )
                    if len(items) == 5:
                        draft = "\n".join(items)

            # Deterministic fallback. It never invents content.
            if not draft and not asks_latest_model:
                fallback = []
                for source in sources:
                    title = clean_text(source.get("title", ""))
                    content = clean_text(source.get("content", ""))

                    if not title:
                        continue

                    fallback.append(
                        f"{len(fallback) + 1}. **{title}** — "
                        f"{content[:350]}"
                    )

                    if len(fallback) == 5:
                        break

                if len(fallback) == 5:
                    draft = "\n".join(fallback)

        if not draft:
            draft = (
                "⚠️ NEXUS could not find enough relevant current "
                "AI information from live research. Please try again."
            )

    else:
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

    st.session_state.activity.extend([
        "Result checked",
        "Memory updated",
    ])

    save_memory(query, draft)
    st.session_state.request_count += 1

    return {
        "answer": draft,
        "sources": (
            research_result.get("sources", [])
            if should_research(query)
            else []
        ),
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
    st.markdown(
        '<div class="nexus-logo">✦ NEXUS</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="nexus-sub">Adaptive agentic workspace</div>',
        unsafe_allow_html=True,
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
    st.caption(
        f"{len(load_memories(100000))} saved interactions"
    )

    if st.button(
        "Clear persistent memory",
        use_container_width=True,
    ):
        con = db()
        con.execute("DELETE FROM memories")
        con.commit()
        con.close()
        st.success("Memory cleared.")

# -------------------- Main header --------------------

st.markdown(
    '<div class="nexus-logo">✦ NEXUS</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="nexus-sub">Research, analyze, reason, create, and work with your knowledge.</div>',
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
        f'<span class="metric-pill">Memory: {len(load_memories(100000))}</span>',
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f'<span class="metric-pill">Knowledge: {len(st.session_state.documents)}</span>',
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f'<span class="metric-pill">Requests: {st.session_state.request_count}</span>',
        unsafe_allow_html=True,
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

# -------------------- Inline attachments --------------------

try:
    chat_value = st.chat_input(
        "Message NEXUS...",
        accept_file=True,
        file_type=[
            "pdf", "txt", "md", "csv",
            "png", "jpg", "jpeg", "webp",
        ],
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
        "role": "user",
        "content": user_text,
        "images": [image for _, image in attached_images],
    })

    with st.chat_message("user"):
        for _, image in attached_images:
            st.image(image, width=260)
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.status(
            "NEXUS is working...",
            expanded=False,
        ):
            result = asyncio.run(
                answer_user(
                    user_text,
                    attached_images,
                )
            )

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

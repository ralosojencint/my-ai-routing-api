import os, re, json, sqlite3, asyncio, time, io, base64
from pathlib import Path
from collections import Counter
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

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
            image.convert("RGB").save(buffer, format="JPEG", quality=90)
            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
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
                        "Never guess a person, character, series, or identity "
                        "unless the user provides it or it is visibly supported."
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

        return "⚠️ Groq returned an empty response."

    except Exception as exc:
        return f"⚠️ GROQ VISION ERROR: {type(exc).__name__}: {exc}"

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
        if images:
            groq_answer = await groq_text(prompt, images=images)
            if not groq_answer.startswith("⚠️"):
                return groq_answer
            return groq_answer
        return (
            "⚠️ Gemini is not connected. "
            "Add GEMINI_API_KEY in Streamlit Secrets."
        )

    contents = [prompt]

    # Send images as explicit Gemini inline-data parts instead of passing
    # PIL objects directly. This makes the vision payload deterministic.
    for _, image in images or []:
        try:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG", quality=90)
            contents.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": buffer.getvalue(),
                }
            })
        except Exception as exc:
            return f"⚠️ Could not prepare image: {type(exc).__name__}: {exc}"

    last_gemini_error = None

    for attempt in range(3):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL,
                contents=contents,
            )

            answer = clean_ai_response(getattr(response, "text", "") or "")

            # A successful HTTP call with no text is still a failed vision
            # response, so immediately use the vision fallback.
            if answer:
                return answer

            last_gemini_error = "Gemini returned no text in its response."
            break

        except Exception as exc:
            last_gemini_error = f"{type(exc).__name__}: {exc}"
            error_text = str(exc).lower()

            if any(x in error_text for x in [
                "429", "resource_exhausted", "quota", "rate limit"
            ]):
                if attempt < 2:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                break

            if any(x in error_text for x in [
                "503", "service unavailable", "temporarily unavailable"
            ]):
                if attempt < 2:
                    await asyncio.sleep(3 * (attempt + 1))
                    continue
                break

            # 404/model compatibility, invalid payloads, and other Gemini
            # errors all go to the same vision fallback with the real error
            # preserved if the fallback also fails.
            break

    # Vision fallback: Groq receives the exact same image(s), not a text-only
    # request. This was the critical failure in the previous implementation.
    if images:
        groq_answer = await groq_text(prompt, images=images)
        if groq_answer and not groq_answer.startswith("⚠️"):
            return groq_answer

        return (
            "⚠️ Vision request failed.\n\n"
            f"Gemini: {last_gemini_error or 'No response.'}\n"
            f"{groq_answer or 'Groq returned no response.'}"
        )

    if last_gemini_error:
        return f"⚠️ Gemini couldn't complete the request: {last_gemini_error}"

    return "⚠️ NEXUS couldn't complete the request. Please try again."

# -------------------- Live research --------------------

# Research is intentionally strict. A news item is only allowed into
# the answer when it is current, AI-related, event-based, and distinct.
RESEARCH_AI_TERMS = {
    "artificial intelligence", "generative ai", "machine learning",
    "ai model", "ai models", "large language model", "llm",
    "foundation model", "ai agent", "ai agents", "robotics",
    "openai", "anthropic", "gemini", "deepmind", "meta ai",
    "microsoft ai", "nvidia", "mistral", "deepseek", "hugging face",
    "huggingface", "qwen", "z.ai", "ai chip", "ai chips",
}

RESEARCH_NOISE_TERMS = {
    "stock market", "stock analysis", "share price", "price target",
    "earnings preview", "earnings outlook", "investor outlook",
    "investor sentiment", "market outlook", "funding outlook",
    "horoscope", "weather", "sports", "flight", "admissions",
    "insurance", "real estate", "celebrity", "recipe", "travel",
    "cosmetics", "veterinary", "murder", "arrest", "crime",
    "criminal", "police", "fbi", "conference registration",
    "webinar", "opinion", "editorial", "commentary", "analysis",
    "preview", "forecast", "prediction", "price forecast",
}

EVENT_TERMS = {
    "launched", "launches", "launch", "released", "release",
    "unveiled", "announced", "announces", "introduced", "deployed",
    "deployment", "available", "general availability", "published",
    "publishes", "revealed", "reveals", "reports", "study", "research",
    "acquired", "acquisition", "partnered", "partnership", "signed",
    "approved", "passes", "passed", "regulation", "policy",
    "opens", "opened", "ships", "rolled out", "rolls out",
}

PRIMARY_DOMAINS = {
    "openai.com", "anthropic.com", "blog.google", "deepmind.google",
    "ai.meta.com", "about.fb.com", "nvidia.com", "microsoft.com",
    "mistral.ai", "huggingface.co", "deepseek.com", "z.ai",
}

SECONDARY_TRUSTED_DOMAINS = {
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theverge.com",
    "techcrunch.com", "technologyreview.com", "arstechnica.com",
    "wired.com", "venturebeat.com", "cnbc.com", "bloomberg.com",
}


def source_domain(url):
    match = re.search(r"https?://([^/]+)", url or "")
    if not match:
        return ""
    return match.group(1).lower().removeprefix("www.")


def local_today():
    """Return today's date in the app's intended user timezone."""
    try:
        return datetime.now(ZoneInfo("Asia/Manila")).date()
    except Exception:
        return datetime.now(timezone.utc).date()


def source_date(source):
    """Parse common Tavily publication-date formats safely."""
    raw = str(
        source.get("published_date")
        or source.get("published")
        or source.get("date")
        or ""
    ).strip()
    if not raw:
        return None

    # ISO/RFC-like timestamps: 2026-08-17, 2026-08-17T12:30:00Z, etc.
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    # A few feeds use month names instead of numeric dates.
    match = re.search(
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+(\d{1,2}),?\s+(20\d{2})",
        raw,
        flags=re.IGNORECASE,
    )
    if match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months[match.group(0).split()[0][:3].lower()]
        try:
            return date(int(match.group(2)), month, int(match.group(1).rstrip(',')))
        except ValueError:
            return None
    return None


def source_combined(source):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    return f"{title} {content}".lower()


# These are strong signals that a page is commentary rather than a new event.
COMMENTARY_TITLE_TERMS = {
    "ceo says", "ceo rejects", "ceo warns", "ceo argues", "ceo believes",
    "says ai", "says that", "rejects claim", "rejects claims", "comments on",
    "weighs in", "op-ed", "opinion", "editorial", "analysis", "commentary",
    "imperative", "why ai", "what ai means", "should ai", "could ai",
    "ai backlash", "public trust in ai", "ai accountability",
}

ROUNDUP_TITLE_TERMS = {
    "roundup", "bonus features", "newsletter", "this week in", "weekly roundup",
    "top stories", "latest stories", "more stories", "what you missed",
}

HARD_NOISE_TITLE_TERMS = {
    "prediction market", "prediction markets", "release date odds", "odds",
    "kalshi", "polymarket", "coupon", "horoscope", "weather", "recipe",
    "flight", "real estate", "insurance", "celebrity gossip",
}

AI_TITLE_TERMS = {
    "artificial intelligence", "generative ai", " ai ", "ai model", "ai models",
    "ai agent", "ai agents", "ai chip", "ai chips", "llm", "language model",
    "foundation model", "machine learning", "robotics", "openai", "anthropic",
    "gemini", "deepmind", "meta ai", "microsoft ai", "nvidia", "mistral",
    "deepseek", "hugging face", "huggingface", "qwen", "z.ai", "claude",
    "chatgpt", "gpt-", "llama",
}

DEVELOPMENT_TITLE_TERMS = {
    "launch", "launched", "launches", "release", "released", "releases",
    "unveil", "unveiled", "unveils", "announce", "announced", "announces",
    "introduce", "introduced", "introduces", "debut", "deploy", "deployed",
    "rolls out", "rolled out", "ships", "shipped", "available", "partnership",
    "partners", "partnered", "acquire", "acquired", "acquisition", "deal",
    "agreement", "approved", "passes", "passed", "policy", "regulation",
    "law", "research", "study", "breakthrough", "chip", "infrastructure",
    "investment", "invests", "funding", "fund", "opens", "opened", "builds",
    "built", "expands", "expanded", "scales", "scaled",
}

CONCRETE_ACTION_TERMS = {
    "launched", "launches", "released", "releases", "unveiled", "announced",
    "introduced", "deployed", "rolled out", "ships", "partnered", "acquired",
    "acquisition", "approved", "passed", "signed", "opens", "opened",
    "published", "study", "research", "breakthrough", "investment", "funding",
    "builds", "built", "expands", "expanded",
}


def is_relevant_ai_source(source, today):
    """Keep only fresh, substantive AI developments.

    Tavily's day-scoped search is the primary freshness signal. Missing
    publication metadata is allowed, but a known date must be recent enough
    for a "today/latest" request. The headline must make AI central to the
    story; a stray AI mention in article boilerplate is not enough.
    """
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    title_lower = title.lower()
    content_lower = content.lower()
    published = source_date(source)

    if len(title) < 12 or len(content) < 80:
        return False

    # Tavily's topic=news + time_range=day is the primary gate. Some publishers
    # expose yesterday's date because of timezone differences, so allow a
    # narrow 36-hour window rather than rejecting a genuinely current story.
    if published is not None:
        age_days = (today - published).days
        if age_days < 0 or age_days > 1:
            return False

    if any(term in title_lower for term in HARD_NOISE_TITLE_TERMS):
        return False
    if any(term in title_lower for term in ROUNDUP_TITLE_TERMS):
        return False
    if any(term in title_lower for term in COMMENTARY_TITLE_TERMS):
        return False

    # AI must be central to the headline. Allow major AI companies/models and
    # clearly AI-specific products, but never promote a generic tech headline
    # merely because its body contains the word "AI".
    ai_title_terms = set(AI_TITLE_TERMS) | {
        "siri", "copilot", "gemini", "claude", "chatgpt", "grok",
        "perplexity", "cursor", "ai pc", "ai phone", "ai assistant",
    }
    ai_in_title = any(term in f" {title_lower} " for term in ai_title_terms)
    if not ai_in_title:
        return False

    # Executive statements are not developments unless the headline also
    # reports a concrete action.
    executive_commentary = (
        any(term in title_lower for term in
            ("ceo", "executive", "founder", "chief"))
        and any(term in title_lower for term in
            ("says", "said", "rejects", "argues", "warns", "believes",
             "comments", "discusses"))
    )
    concrete_headline = any(
        term in title_lower for term in DEVELOPMENT_TITLE_TERMS
    )
    if executive_commentary and not concrete_headline:
        return False

    # A development signal must appear in the headline OR immediately in the
    # article opening. This prevents navigation/related-story boilerplate from
    # qualifying an otherwise unrelated headline.
    opening = content_lower[:1000]
    title_has_development = concrete_headline
    opening_has_action = any(
        term in opening for term in CONCRETE_ACTION_TERMS
    )
    if not title_has_development and not opening_has_action:
        return False

    # Reject generic opinion/explainer framing even when an AI company is named.
    generic_framing = (
        "why " in title_lower
        or title_lower.startswith("how ")
        or title_lower.startswith("what ")
        or "explained" in title_lower
        or "imperative" in title_lower
        or "boardroom" in title_lower
    )
    if generic_framing and not concrete_headline:
        return False

    return True


def research_score(source, today):
    """Rank already-filtered candidates by freshness, substance and source quality."""
    title = clean_text(source.get("title", "")).lower()
    content = clean_text(source.get("content", "")).lower()
    domain = source_domain(source.get("url", ""))
    published = source_date(source)
    score = 0

    if domain in PRIMARY_DOMAINS:
        score += 110
    elif domain in SECONDARY_TRUSTED_DOMAINS:
        score += 90
    else:
        score += 45

    if published == today:
        score += 120
    elif published is None:
        score += 80
    else:
        score += 45

    # Concrete developments are much more important than merely mentioning AI.
    title_actions = sum(
        1 for term in DEVELOPMENT_TITLE_TERMS if term in title
    )
    opening_actions = sum(
        1 for term in CONCRETE_ACTION_TERMS if term in content[:1200]
    )
    score += min(title_actions * 18, 72)
    score += min(opening_actions * 5, 25)

    if any(term in title for term in
           ("launch", "release", "released", "announced", "unveiled",
            "deployed", "rolls out", "ships")):
        score += 35
    if any(term in title for term in
           ("research", "study", "breakthrough")):
        score += 28
    if any(term in title for term in
           ("partnership", "partnered", "acquisition", "deal", "agreement")):
        score += 20
    if any(term in title for term in
           ("chip", "infrastructure", "data center", "model")):
        score += 12

    # Penalize commentary/rumor framing even if it survived the basic gate.
    if any(term in title for term in
           ("reportedly", "rumor", "rumored", "could", "may", "might")):
        score -= 18

    # Useful article text is positive, but giant scraped pages are not.
    score += min(len(content), 1800) // 300
    return score


def event_tokens(source):
    title = clean_text(source.get("title", "")).lower()
    content = clean_text(source.get("content", "")).lower()[:700]
    text = f"{title} {content}"
    tokens = set(re.findall(r"[a-z0-9]+", text))
    generic = {
        "ai", "artificial", "intelligence", "new", "latest", "today",
        "news", "company", "technology", "system", "report", "reports",
        "says", "said", "will", "could", "may", "according", "model",
        "models", "research", "study", "industry", "the", "and", "for",
        "with", "from", "this", "that", "into", "after", "over",
    }
    return tokens - generic


def same_event(a, b):
    ta = event_tokens(a)
    tb = event_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    return overlap >= 0.55


def select_distinct_sources(sources, limit=5):
    selected = []
    for source in sources:
        if any(same_event(source, old) for old in selected):
            continue
        selected.append(source)
        if len(selected) >= limit:
            break
    return selected


async def research(query):
    client = tavily_client()
    if client is None:
        return {"sources": [], "error": "Tavily client is not available. Check TAVILY_API_KEY."}

    today = local_today()
    date_text = today.isoformat()

    # Search several concrete development categories. Keep enough candidates
    # to rank across categories instead of letting one story dominate.
    queries = [
        f"latest AI news developments today {date_text}",
        f"AI model product launch announcement {date_text}",
        f"OpenAI Anthropic Google Gemini Meta AI new announcement {date_text}",
        f"AI research study breakthrough published {date_text}",
        f"AI agent robotics product deployment launch {date_text}",
        f"AI regulation policy government action {date_text}",
        f"AI chips data center infrastructure investment announcement {date_text}",
    ]

    all_sources = []
    for q in queries:
        try:
            result = await asyncio.to_thread(
                client.search,
                query=q,
                search_depth="advanced",
                topic="news",
                time_range="day",
                max_results=12,
                include_answer=False,
            )
            all_sources.extend(result.get("results", []))
        except Exception:
            continue

    unique = []
    seen_urls = set()
    for source in all_sources:
        url = str(source.get("url", "")).strip()
        key = url.rstrip("/").lower()
        if not key or key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(source)

    filtered = [s for s in unique if is_relevant_ai_source(s, today)]
    ranked = sorted(filtered, key=lambda s: research_score(s, today), reverse=True)
    final = select_distinct_sources(ranked, limit=5)

    return {"sources": final, "error": ""}

def should_research(query):
    q = query.lower()
    research_words = [
        "latest", "today", "current", "news", "recent", "breaking",
        "developments", "what happened",
    ]
    return bool(TAVILY_API_KEY) and any(word in q for word in research_words)


def source_grounded_summary(source):
    """Create a concise summary from the source text without inventing facts."""
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    if not title:
        return ""

    # Tavily snippets can contain navigation/boilerplate. Prefer the first few
    # complete sentences and cap the result so one source cannot overwhelm the list.
    snippet = content[:900].strip()
    sentences = re.split(r"(?<=[.!?])\s+", snippet)
    useful = []
    total = 0
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 35:
            continue
        if total + len(sentence) > 520:
            break
        useful.append(sentence)
        total += len(sentence)
        if len(useful) >= 2:
            break

    summary = " ".join(useful).strip() or snippet[:520].strip()
    if summary and summary[-1] not in ".!?":
        summary += "…"
    return f"**{title}** — {summary}" if summary else f"**{title}**"

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
                "latest ai model", "latest model", "newest ai model",
                "new ai model", "model released", "model launch",
            ]
        )

        if sources:
            st.session_state.activity.append(
                f"Verified {len(sources)} current sources"
            )

            if asks_latest_model:
                model_sources = [
                    s for s in sources
                    if any(term in clean_text(s.get("title", "")).lower()
                           for term in ["model", "gemini", "llama", "claude", "gpt", "deepseek", "mistral"])
                    and any(term in clean_text(s.get("title", "")).lower()
                            for term in ["launch", "release", "released", "announ", "unveil"])
                ]
                if model_sources:
                    chosen = model_sources[0]
                    title = clean_text(chosen.get("title", ""))
                    content = clean_text(chosen.get("content", ""))
                    draft = f"**{title}**\n\n{content[:650]}"
                    sources = [chosen]
            else:
                # IMPORTANT: do not ask another model to invent/synthesize
                # the news list. Build the answer directly from verified
                # same-day sources. This prevents unsupported claims such as
                # a model launch that is absent from the actual source set.
                verified = []
                for source in sources:
                    summary = source_grounded_summary(source)
                    if summary:
                        verified.append(summary)
                    if len(verified) == 5:
                        break

                if len(verified) >= 1:
                    draft = "\n\n".join(
                        f"{i}. {item}" for i, item in enumerate(verified, 1)
                    )
                else:
                    draft = (
                        "⚠️ NEXUS could not verify any current AI developments "
                        "from today's research results."
                    )

        if not draft:
            draft = (
                "⚠️ NEXUS could not verify enough current AI information "
                "from today's research results."
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

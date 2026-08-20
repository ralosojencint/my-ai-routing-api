import os, re, json, sqlite3, asyncio, time, io, base64
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo
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

MODEL = "gemini-3.5-flash"  # Stable Gemini 3.5 Flash model ID

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
    """
    Primary Gemini pipeline with a real Groq fallback for BOTH text and vision.

    Important Phase-2 reliability rule:
    a Gemini 429/503/404/empty response must never terminate a normal
    text request before the fallback gets a chance to answer.
    """
    client = gemini_client()
    last_gemini_error = None

    # Prepare the multimodal payload once so retries and the Groq fallback
    # receive the same logical request.
    contents = [prompt]
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
            last_gemini_error = (
                f"Could not prepare image: {type(exc).__name__}: {exc}"
            )
            break

    # If Gemini is unavailable before a request can even be sent, do not
    # abandon the request. Groq is the secondary provider for every route
    # that reaches this function.
    if client is None:
        last_gemini_error = (
            "Gemini client is unavailable. "
            "Check GEMINI_API_KEY and the google-genai package."
        )
    elif not any("Could not prepare image:" in str(x) for x in [last_gemini_error]):
        for attempt in range(3):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=MODEL,
                    contents=contents,
                )

                answer = clean_ai_response(
                    getattr(response, "text", "") or ""
                )

                if answer:
                    return answer

                last_gemini_error = "Gemini returned no text in its response."
                break

            except Exception as exc:
                last_gemini_error = f"{type(exc).__name__}: {exc}"
                error_text = str(exc).lower()

                # Retry transient provider failures, then fall through to Groq.
                if any(x in error_text for x in (
                    "429", "resource_exhausted", "quota", "rate limit",
                    "503", "service unavailable", "temporarily unavailable",
                    "deadline exceeded", "timeout", "connection reset",
                )):
                    if attempt < 2:
                        if "503" in error_text or "service unavailable" in error_text:
                            await asyncio.sleep(2 * (attempt + 1))
                        else:
                            await asyncio.sleep(3 * (attempt + 1))
                        continue

                # Non-transient errors (including model/payload errors) should
                # immediately use the secondary provider instead of exposing a
                # Gemini-only failure to the user.
                break

    # CRITICAL FIX:
    # Groq fallback now runs for normal text requests as well as vision.
    # Previously this block only ran when images were attached, which is why
    # Test 1 exposed the raw Gemini 503 instead of recovering.
    groq_answer = await groq_text(prompt, images=images)
    if groq_answer and not groq_answer.startswith("⚠️"):
        return groq_answer

    # Preserve both provider failures so debugging is actionable.
    if images:
        return (
            "⚠️ NEXUS could not complete the vision request.\n\n"
            f"Gemini: {last_gemini_error or 'No response.'}\n"
            f"Groq: {groq_answer or 'No response.'}"
        )

    return (
        "⚠️ NEXUS could not complete the request.\n\n"
        f"Gemini: {last_gemini_error or 'No response.'}\n"
        f"Groq: {groq_answer or 'No response.'}"
    )

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


def normalize_url(url):
    """Canonicalize URLs so AMP/tracking variants count as the same source."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        host = parts.netloc.lower().removeprefix("www.")
        path = re.sub(r"/+(?:amp|amp/?)$", "", parts.path.rstrip("/"), flags=re.I)
        path = re.sub(r"/amp(?:/)?$", "", path, flags=re.I)
        tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid", "mc_cid", "mc_eid"}
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in tracking]
        return urlunsplit((parts.scheme.lower() or "https", host, path or "/", urlencode(query), "")).lower()
    except Exception:
        return raw.rstrip("/").lower()


def source_domain(url):
    try:
        return urlsplit(str(url or "")).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def source_date(source):
    """Parse publication dates from Tavily metadata and article text."""
    if not isinstance(source, dict):
        return None

    values = []
    keys = (
        "published_date", "publication_date", "published", "date",
        "publishedAt", "published_at", "pub_date", "timestamp",
    )
    for k in keys:
        v = source.get(k)
        if v not in (None, ""):
            values.append(str(v).strip())
    for container_key in ("metadata", "meta"):
        c = source.get(container_key)
        if isinstance(c, dict):
            for k in keys:
                v = c.get(k)
                if v not in (None, ""):
                    values.append(str(v).strip())

    # Tavily may expose the publication date only in the article text/title.
    # Keep this as a fallback so valid same-day articles are not discarded just
    # because the provider omitted a dedicated date field.
    for k in ("title", "content", "raw_content"):
        v = source.get(k)
        if v not in (None, ""):
            values.append(str(v).strip())

    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    short = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"

    for raw in values:
        # ISO dates and timestamps.
        m = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", raw)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass

        # Month-first with year: August 20, 2026 / Aug 20 2026.
        m = re.search(rf"\b({months}|{short})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", raw, re.I)
        if m:
            mon = m.group(1).title()
            mon = "Sep" if mon == "Sept" else mon
            for fmt in ("%B %d %Y", "%b %d %Y"):
                try:
                    return datetime.strptime(f"{mon} {m.group(2)} {m.group(3)}", fmt).date()
                except ValueError:
                    pass

        # Day-first with year: 20 August 2026 / 20 Aug 2026.
        m = re.search(rf"\b(\d{{1,2}})\s+({months}|{short}),?\s+(20\d{{2}})\b", raw, re.I)
        if m:
            mon = m.group(2).title()
            mon = "Sep" if mon == "Sept" else mon
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    return datetime.strptime(f"{m.group(1)} {mon} {m.group(3)}", fmt).date()
                except ValueError:
                    pass

        # News copy frequently says "August 20" or "20 August" without the
        # year. Use the current research year, then let the caller enforce the
        # exact target date.
        m = re.search(rf"\b({months}|{short})\s+(\d{{1,2}})\b", raw, re.I)
        if m:
            mon = m.group(1).title()
            mon = "Sep" if mon == "Sept" else mon
            try:
                return datetime.strptime(
                    f"{mon} {m.group(2)} {datetime.now(ZoneInfo('Asia/Manila')).year}",
                    "%B %d %Y",
                ).date()
            except ValueError:
                try:
                    return datetime.strptime(
                        f"{mon} {m.group(2)} {datetime.now(ZoneInfo('Asia/Manila')).year}",
                        "%b %d %Y",
                    ).date()
                except ValueError:
                    pass

        m = re.search(rf"\b(\d{{1,2}})\s+({months}|{short})\b", raw, re.I)
        if m:
            mon = m.group(2).title()
            mon = "Sep" if mon == "Sept" else mon
            for fmt in ("%d %B %Y", "%d %b %Y"):
                try:
                    return datetime.strptime(
                        f"{m.group(1)} {mon} {datetime.now(ZoneInfo('Asia/Manila')).year}",
                        fmt,
                    ).date()
                except ValueError:
                    pass

    return None


def source_combined(source):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    return f"{title} {content}".lower()


def is_relevant_ai_source(source, today, target_date=None):
    """High-precision gate for real current AI developments."""
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    title_lower = title.lower()
    content_lower = content.lower()
    combined = f"{title_lower} {content_lower}"
    published = source_date(source)

    if len(title) < 12 or len(content) < 80:
        return False

    # Tavily already used topic=news + time_range=day. Missing publication
    # metadata therefore must NOT reject an otherwise valid result.
    # With a date present, allow today plus the immediately previous calendar
    # day because news APIs can expose UTC/publisher dates around midnight.
    if published is not None:
        if target_date is not None:
            if published != target_date:
                return False
        else:
            age = (today - published).days
            if age < 0 or age > 1:
                return False

    # AI must be central to the headline, not merely mentioned somewhere in
    # a scraped article body (e.g. an iPhone story that mentions Siri once).
    headline_ai = any(term in title_lower for term in RESEARCH_AI_TERMS)
    named_ai_company = any(term in title_lower for term in (
        "openai", "anthropic", "gemini", "deepmind", "meta ai", "microsoft ai",
        "nvidia", "mistral", "deepseek", "hugging face", "huggingface", "qwen",
    ))
    ai_topic_words = any(term in title_lower for term in (
        "artificial intelligence", "generative ai", "machine learning", "ai model",
        "ai models", "language model", "llm", "foundation model", "ai agent",
        "ai agents", "ai chip", "ai chips", "robotics", "robot", "siri",
    ))
    if not (headline_ai or named_ai_company or ai_topic_words):
        return False

    # Reject activism/protest coverage. These can mention OpenAI/AI heavily but
    # are not themselves AI developments for a "latest developments" query.
    activism_terms = (
        "protest", "protester", "protesters", "activist", "activism",
        "demonstration", "demonstrators", "direct-action", "march",
        "rally", "boycott", "anti-ai", "anti ai",
    )
    if any(term in title_lower for term in activism_terms):
        return False

    # Reject stories whose primary purpose is finance, prediction, opinion or
    # generic consumer-tech noise. Concrete AI company actions can still pass
    # if the headline contains a genuine event verb.
    hard_noise = (
        "horoscope", "weather", "sports", "flight", "admissions", "insurance",
        "real estate", "celebrity", "recipe", "travel", "cosmetics", "murder",
        "arrest", "crime", "criminal", "police", "fbi", "conference registration",
        "webinar", "earnings preview", "earnings outlook", "price target",
        "stock forecast", "share price forecast", "prediction market", "odds",
    )
    if any(term in title_lower for term in hard_noise):
        return False

    financial_title = any(term in title_lower for term in (
        "stock", "shares", "share price", "bitcoin", "investor", "investment",
        "debt deal", "market outlook", "price target", "valuation", "analyst",
        "funding round", "funding outlook", "bullish", "bearish",
    ))
    opinion_title = any(term in title_lower for term in (
        "says", "argues", "opinion", "editorial", "commentary", "analysis",
        "why ", "what to expect", "could ", "might ", "predicts", "forecast",
    ))

    # An actual event signal must exist in the headline or opening content.
    event_area = f"{title_lower} {content_lower[:1800]}"
    has_event = any(term in event_area for term in EVENT_TERMS)
    if not has_event:
        return False

    # For opinion/finance-style headlines, require the concrete action to be
    # in the headline itself. A buried word such as "signed" in scraped body
    # boilerplate must not turn commentary into a development.
    # IMPORTANT: compute this BEFORE using it below.
    concrete_title_event = any(term in title_lower for term in (
        "launch", "release", "released", "announc", "unveil", "introduc",
        "deploy", "deployed", "acquir", "partner", "approved", "regulation",
        "policy", "rolls out", "rolled out", "ships", "opens", "opened",
        "publishes", "published", "signed",
    ))
    # A headline that is purely a market move is not a development even if
    # the article discusses AI extensively.
    if financial_title and not any(term in title_lower for term in (
        "ai infrastructure", "ai data center", "ai chip", "ai chips", "ai model",
        "ai platform", "ai system", "artificial intelligence",
    )) and not concrete_title_event:
        return False

    return True


def is_relaxed_current_ai_source(source, today):
    """Second-stage gate used only when strict filtering cannot reach the requested count.
    It still requires a verifiable publication date of today and a genuinely AI-centered
    story, but does not require a particular event verb in the headline."""
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    low = f"{title} {content[:2200]}".lower()
    published = source_date(source)
    if published != today or len(title) < 12 or len(content) < 80:
        return False

    ai_terms = (
        "artificial intelligence", "generative ai", " ai ", "ai model", "ai models",
        "llm", "language model", "foundation model", "ai agent", "ai agents",
        "machine learning", "robotics", "humanoid robot", "ai chip", "ai chips",
        "openai", "anthropic", "gemini", "deepmind", "meta ai", "mistral",
        "deepseek", "nvidia", "hugging face", "huggingface", "qwen",
    )
    if not any(term in low for term in ai_terms):
        return False

    noise = (
        "horoscope", "weather", "sports", "flight", "recipe", "celebrity",
        "murder", "arrest", "crime", "police", "stock forecast", "price target",
        "prediction market", "odds", "conference registration", "webinar",
    )
    if any(term in title.lower() for term in noise):
        return False
    return True

def research_score(source, today):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    title_lower = title.lower()
    combined = f"{title_lower} {content.lower()}"
    domain = source_domain(source.get("url", ""))
    published = source_date(source)
    score = 0

    # Source quality matters, but never enough to rescue an irrelevant story.
    if domain in PRIMARY_DOMAINS:
        score += 90
    elif domain in SECONDARY_TRUSTED_DOMAINS:
        score += 65
    else:
        score += 20

    if published == today:
        score += 40
    elif published == today.fromordinal(today.toordinal() - 1):
        score += 18
    else:
        score += 10  # missing metadata is acceptable because Tavily was day-scoped

    # Highest priority: concrete, substantive AI developments.
    priority_events = {
        "launched": 38, "launches": 38, "launch": 34,
        "released": 38, "release": 34, "unveiled": 36, "announced": 34,
        "announces": 34, "introduced": 32, "deployed": 32, "deployment": 30,
        "general availability": 34, "available": 24, "acquired": 28,
        "acquisition": 28, "partnership": 27, "partnered": 27,
        "approved": 30, "regulation": 30, "policy": 27, "rolled out": 30,
        "rolls out": 30, "research": 25, "study": 22, "breakthrough": 30,
    }
    for term, points in priority_events.items():
        if term in title_lower:
            score += points

    # Penalize low-value finance/commentary even when relevant.
    if any(term in title_lower for term in ("stock", "shares", "share price", "bitcoin", "investor", "investment", "debt deal", "analyst")):
        score -= 35
    if any(term in title_lower for term in ("says", "argues", "opinion", "commentary", "analysis", "forecast", "prediction", "odds")):
        score -= 28

    # Reward specificity: models, products, deployments, research and policy.
    if any(term in title_lower for term in ("model", "agent", "robot", "chip", "data center", "research", "study", "policy", "regulation")):
        score += 15

    score += min(len(content), 1600) // 400
    return score


def event_tokens(source):
    title = clean_text(source.get("title", "")).lower()
    content = clean_text(source.get("content", "")).lower()[:700]
    text = f"{title} {content}"
    tokens = set(re.findall(r"[a-z0-9]+", text))
    generic = {
        "ai", "artificial", "intelligence", "new", "latest", "today", "news",
        "company", "technology", "system", "report", "reports", "says", "said",
        "will", "could", "may", "according", "model", "models", "research",
        "study", "industry", "the", "and", "for", "with", "from", "that",
        "this", "its", "into", "over", "after", "about", "more", "than",
    }
    return tokens - generic


def same_event(a, b):
    # Canonical URL is the strongest duplicate signal.
    ua = normalize_url(a.get("url", ""))
    ub = normalize_url(b.get("url", ""))
    if ua and ub and ua == ub:
        return True

    ta = event_tokens(a)
    tb = event_tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / max(1, min(len(ta), len(tb)))
    # Headlines from different outlets often share generic AI vocabulary.
    # Require a stronger overlap before treating them as the same event.
    return overlap >= 0.88


def select_distinct_sources(sources, limit=5):
    """Select exactly the requested number of distinct, event-level sources."""
    selected = []
    seen_domains = {}
    for source in sources:
        if any(same_event(source, old) for old in selected):
            continue
        # Avoid filling the whole list with copies from one outlet, while still
        # allowing a second article when it is clearly a different event.
        domain = source_domain(source.get("url", ""))
        if seen_domains.get(domain, 0) >= 2:
            continue
        selected.append(source)
        seen_domains[domain] = seen_domains.get(domain, 0) + 1
        if len(selected) >= limit:
            break
    return selected[:max(0, limit)]


def requested_development_count(query, default=5):
    """Extract an explicit requested development count, otherwise use default."""
    text = clean_text(query).lower()
    word_counts = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }

    # Match a number/number-word appearing within a short phrase before
    # "development(s)". This covers: "3 developments", "3 current AI
    # developments", "five most important developments", etc.
    count_pattern = r"\b([1-9]|10|one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s+\w+){0,5}\s+developments?\b"
    matches = list(re.finditer(count_pattern, text))
    if matches:
        raw = matches[-1].group(1)
        return int(raw) if raw.isdigit() else word_counts[raw]

    return default


def requires_exact_today(query):
    """Whether the user explicitly requires evidence published today."""
    q = clean_text(query).lower()
    return bool(re.search(r"\b(?:today|published today|reported today)\b", q))


def requested_research_date(query, today):
    text = clean_text(query)
    patterns = (
        r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            if pattern.startswith(r"\b(20"):
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            return datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%B %d %Y").date()
        except ValueError:
            pass
    return None


async def research(query):
    """Phase-2 research with iterative candidate recovery and hard exact-count enforcement."""
    client = tavily_client()
    requested_count = max(1, requested_development_count(query, default=5))
    if client is None:
        return {"sources": [], "requested_count": requested_count,
                "error": "Tavily client is not available. Check TAVILY_API_KEY."}

    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    exact_today = requires_exact_today(query)
    target_date = requested_research_date(query, today) or (today if exact_today else None)
    date_text = (target_date or today).isoformat()
    pretty_date = (target_date or today).strftime("%B %d, %Y")
    focus = clean_text(query)[:500]

    queries = [
        f"{focus} {pretty_date}",
        f"AI artificial intelligence news {pretty_date}",
        f"AI model product launch release announcement {pretty_date}",
        f"AI company announcement partnership deployment {pretty_date}",
        f"AI research study science breakthrough {pretty_date}",
        f"AI agents enterprise software deployment {pretty_date}",
        f"humanoid robotics robot AI deployment {pretty_date}",
        f"AI chips semiconductor data center infrastructure {pretty_date}",
        f"AI regulation policy government {pretty_date}",
        f"generative AI business product technology {pretty_date}",
        f"OpenAI Anthropic Google Gemini Meta AI NVIDIA Mistral {pretty_date}",
        f"DeepMind DeepSeek Qwen Hugging Face AI {pretty_date}",
    ]

    async def search_one(q, time_range="day", domains=None, max_results=15):
        kwargs={"query":q,"search_depth":"advanced","topic":"news","max_results":max_results,"include_answer":False}
        if time_range: kwargs["time_range"]=time_range
        if domains: kwargs["include_domains"]=domains
        try:
            result=await asyncio.to_thread(client.search,**kwargs)
            return [x for x in result.get("results",[]) if isinstance(x,dict)]
        except Exception:
            return []

    def unique(items):
        out=[]; seen=set()
        for item in items:
            key=normalize_url(item.get("url",""))
            if not key or key in seen: continue
            seen.add(key); out.append(item)
        return out

    def strict_valid(items):
        out=[]
        for item in items:
            if not is_relevant_ai_source(item,today,target_date=target_date): continue
            if exact_today or target_date==today:
                if source_date(item)!=today: continue
            out.append(item)
        return out

    all_sources=[]
    first=await asyncio.gather(*(search_one(q,"day" if (exact_today or target_date==today) else None) for q in queries))
    for batch in first: all_sources.extend(batch)
    candidates=unique(all_sources)
    filtered=strict_valid(candidates)

    # Recovery 1: category + outlet searches. These are deliberately different
    # from the first-pass queries so one dominant story cannot consume the pool.
    if len(select_distinct_sources(sorted(filtered,key=lambda x:research_score(x,today),reverse=True), requested_count)) < requested_count and (exact_today or target_date==today):
        recovery_queries=[
            f"AI news {pretty_date}", f"AI announcement {pretty_date}",
            f"AI launch {pretty_date}", f"AI research {pretty_date}",
            f"AI agents {pretty_date}", f"AI robotics {pretty_date}",
            f"AI chips {pretty_date}", f"AI policy {pretty_date}",
            f"AI enterprise {pretty_date}", f"AI startup {pretty_date}",
        ]
        outlets=[
            ["reuters.com","apnews.com"],
            ["techcrunch.com","theverge.com"],
            ["cnbc.com","venturebeat.com"],
            ["arstechnica.com","technologyreview.com"],
            ["counterpointresearch.com","ibm.com"],
            ["opensourceforu.com","siliconangle.com"],
        ]
        jobs=[search_one(q,"day",max_results=15) for q in recovery_queries]
        jobs += [search_one(f"{q} {pretty_date}","day",domains=d,max_results=10) for q in recovery_queries[:8] for d in outlets]
        recovery=await asyncio.gather(*jobs)
        for batch in recovery: all_sources.extend(batch)
        candidates=unique(all_sources)
        filtered=strict_valid(candidates)

    # Recovery 2: retain the strict publication-date requirement but relax only
    # the headline event-verb gate. This is critical for headlines such as
    # research reports, survey findings, launches described without "launch",
    # and company actions phrased in non-standard ways.
    strict_ranked=sorted(filtered,key=lambda x:research_score(x,today),reverse=True)
    final=select_distinct_sources(strict_ranked,limit=requested_count)
    if len(final)<requested_count and (exact_today or target_date==today):
        relaxed=[x for x in candidates if is_relaxed_current_ai_source(x,today)]
        merged=unique(strict_ranked+relaxed)
        # Prefer strong strict candidates, then high-quality relaxed candidates.
        merged=sorted(merged,key=lambda x:(research_score(x,today),len(clean_text(x.get("content","")))),reverse=True)
        final=select_distinct_sources(merged,limit=requested_count)

    err="" if len(final)>=requested_count else f"Only {len(final)} independently verified current AI development(s) were available; {requested_count} requested."
    return {"sources":final,"requested_count":requested_count,"target_date":target_date.isoformat() if target_date else None,"error":err}


def is_forex_query(query):
    q = clean_text(query).lower()
    forex_terms = (
        "forex factory", "forexfactory", "forex", "fx calendar",
        "forex calendar", "economic calendar", "economic news",
        "high impact news", "high impact forex", "forex news",
        "fx news", "currency news", "currency calendar",
    )
    return any(term in q for term in forex_terms)


async def forex_research(query):
    """Retrieve Forex Factory economic-calendar results without using the AI-news pipeline."""
    client = tavily_client()
    if client is None:
        return {
            "sources": [],
            "error": "Tavily client is not available. Check TAVILY_API_KEY.",
        }

    today = datetime.now(ZoneInfo("Asia/Manila")).date()
    date_text = today.isoformat()

    queries = [
        f"site:forexfactory.com/calendar Forex Factory high impact economic calendar {date_text}",
        f"site:forexfactory.com/calendar high impact red folder news {date_text}",
        f"site:forexfactory.com/calendar {query} {date_text}",
    ]

    all_sources = []
    for q in queries:
        try:
            result = await asyncio.to_thread(
                client.search,
                query=q,
                search_depth="advanced",
                max_results=8,
                include_answer=False,
                include_domains=["forexfactory.com"],
            )
            all_sources.extend(result.get("results", []))
        except Exception:
            continue

    unique = []
    seen_urls = set()
    for source in all_sources:
        url = str(source.get("url", "")).strip()
        domain = source_domain(url)
        if not url or not (domain == "forexfactory.com" or domain.endswith(".forexfactory.com")):
            continue
        key = normalize_url(url)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        unique.append(source)

    # Calendar pages are not ordinary news articles and often have no
    # publication date, so do NOT apply the AI-news date/content gate here.
    ranked = sorted(
        unique,
        key=lambda source: (
            1 if "calendar" in str(source.get("url", "")).lower() else 0,
            len(clean_text(source.get("content", ""))),
        ),
        reverse=True,
    )

    return {"sources": ranked[:8], "error": ""}

def should_research(query):
    q = query.lower()

    # Forex/economic-calendar requests must never enter the AI-news pipeline.
    if is_forex_query(query):
        return bool(TAVILY_API_KEY)

    research_words = [
        "latest", "today", "current", "news", "recent", "breaking",
        "developments", "what happened",
    ]
    return bool(TAVILY_API_KEY) and any(word in q for word in research_words)


def source_grounded_summary(source):
    """Build a short source-grounded summary from the most relevant sentences."""
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    if not title:
        return ""
    if not content:
        return f"**{title}**"

    title_tokens = set(re.findall(r"[a-z0-9]{3,}", title.lower()))
    boilerplate = {
        "home", "menu", "login", "sign", "subscribe", "recommended",
        "read", "more", "share", "copyright", "advertisement",
        "latest", "today", "real", "time", "breaking",
    }
    sentences = re.split(r"(?<=[.!?])\s+", content)
    candidates = []
    for sentence in sentences:
        sentence = sentence.strip(" -—|•")
        if len(sentence) < 45:
            continue
        low = sentence.lower()
        if sum(1 for word in boilerplate if word in low) >= 2:
            continue
        overlap = len(title_tokens & set(re.findall(r"[a-z0-9]{3,}", low)))
        event_bonus = 12 if any(term in low for term in EVENT_TERMS) else 0
        score = overlap * 3 + event_bonus - max(0, len(sentence) - 320) / 80
        candidates.append((score, sentence))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        snippet = candidates[0][1]
    else:
        snippet = content[:320].strip()

    if len(snippet) > 420:
        snippet = snippet[:417].rsplit(" ", 1)[0] + "…"
    elif snippet and snippet[-1] not in ".!?…":
        snippet += "…"
    return f"**{title}** — {snippet}"

# -------------------- Phase 2 — Multi-Agent Router --------------------

ROUTE_RESEARCH = "research"
ROUTE_FOREX = "forex"
ROUTE_DATA = "data"
ROUTE_DOCUMENTS = "documents"
ROUTE_VISION = "vision"
ROUTE_GENERAL = "general"


def detect_route(query, images=None):
    """Deterministic Phase-2 router.

    The router only decides which EXISTING specialist pipeline should handle
    the request. It does not call another AI model to classify the request.
    """
    q = clean_text(query).lower()

    if is_forex_query(query):
        return ROUTE_FOREX

    data_terms = (
        "csv", "dataset", "data", "spreadsheet", "table", "column", "row",
        "sales", "revenue", "units", "average", "median", "total", "trend",
        "calculate", "calculate", "analyze the data", "analyse the data",
    )
    if st.session_state.datasets and any(term in q for term in data_terms):
        return ROUTE_DATA

    document_terms = (
        "document", "pdf", "file", "uploaded", "attachment", "according to",
        "based on the document", "based on the file", "in the pdf", "in the file",
        "summarize the document", "summarise the document", "what does the document",
    )
    if st.session_state.documents and any(term in q for term in document_terms):
        return ROUTE_DOCUMENTS

    if images:
        return ROUTE_VISION

    # If knowledge/data exists and the user asks a short follow-up, prefer the
    # matching context pipeline instead of silently treating it as unrelated.
    if st.session_state.datasets and any(
        term in q for term in ("this data", "these data", "the dataset", "those numbers", "the csv")
    ):
        return ROUTE_DATA

    if st.session_state.documents and any(
        term in q for term in ("this document", "this file", "the document", "the file", "above")
    ):
        return ROUTE_DOCUMENTS

    # Current research should still run when the session contains old uploads.
    # Only explicit data/document intent should take precedence.
    if should_research(query) and not images:
        return ROUTE_RESEARCH

    return ROUTE_GENERAL


def route_label(route):
    return {
        ROUTE_RESEARCH: "Research Agent",
        ROUTE_FOREX: "Forex Agent",
        ROUTE_DATA: "Data Agent",
        ROUTE_DOCUMENTS: "Document/RAG Agent",
        ROUTE_VISION: "Vision Agent",
        ROUTE_GENERAL: "General Reasoning Agent",
    }.get(route, "General Reasoning Agent")


def build_context(query):
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
    return base_prompt


async def research_synthesis(query, sources):
    """Synthesize only the selected source set and keep source identity explicit."""
    if not sources:
        return ""

    requested_count = requested_development_count(query, default=len(sources))
    selected_sources = sources[:requested_count]

    evidence = []
    for i, source in enumerate(selected_sources, 1):
        title = clean_text(source.get("title", ""))
        content = clean_text(source.get("content", ""))
        published = source_date(source)
        published_text = published.isoformat() if published else "publication date not provided"
        if title:
            evidence.append(
                f"SOURCE {i}\nTITLE: {title}\nPUBLISHED: {published_text}\n"
                f"URL: {source.get('url', '')}\nCONTENT: {content[:1800]}"
            )

    if not evidence:
        return ""

    prompt = f"""You are the research synthesis layer of NEXUS.

Answer the user's question using ONLY the selected source evidence below.
The source list has already been filtered and selected by NEXUS. Do not add
other sources, facts, or developments from your own knowledge.

IMPORTANT OUTPUT RULES:
- Follow the exact number requested by the user. If the user asks for 3, output exactly 3 developments.
- Use exactly ONE source for each development: the source assigned to that numbered item below.
- Do not introduce a source that is not in the selected evidence.
- Every factual claim about a development must be supported by its assigned source.
- Put the source marker immediately after the evidence for each development, using exactly [Source N].
- If the user asks for publication dates, use only the PUBLISHED field supplied below.
- Include a final Sources section containing ONLY the selected sources, one per development, in the same order.
- In the Sources section, use the source title and URL exactly as supplied. Do not add any other source.
- If the evidence is insufficient for the requested count, say so instead of inventing a development.

USER QUESTION:
{query}

SELECTED SOURCE EVIDENCE:
\n\n""" + "\n\n".join(evidence)

    client = gemini_client()
    if client is None:
        return ""

    try:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=[prompt],
        )
        answer = clean_ai_response(getattr(response, "text", "") or "")
        return answer
    except Exception:
        # Research remains usable through the deterministic source summaries
        # if the synthesis model is unavailable or rate-limited.
        return ""


def render_exact_research_output(query,sources):
    """Produce an exact, one-source-per-development answer without model drift."""
    n=requested_development_count(query,default=len(sources)); selected=sources[:n]
    if len(selected)<n: return ""
    items=[]; source_lines=[]
    for i,src in enumerate(selected,1):
        title=clean_text(src.get("title","")); summary=source_grounded_summary(src); url=str(src.get("url","")).strip()
        if not title or not summary or not url: return ""
        summary = re.sub(r"\s*#+\s*Sources.*$", "", summary, flags=re.I|re.S).strip()
        items.append(f"{i}. {summary} [Source {i}]")
        source_lines.append(f"{i}. {title} — {url}")
    return "\n\n".join(items)+"\n\n### Sources\n"+"\n".join(source_lines)


async def research_pipeline(query):
    research_result=await research(query)
    sources=research_result.get("sources",[])
    n=requested_development_count(query,default=len(sources))
    st.session_state.activity.append(f"Selected {len(sources)} source(s) for the requested research output")
    exact_contract=(n>=1 and (requires_exact_today(query) or "exactly one source" in query.lower() or "sources section" in query.lower()))
    if exact_contract:
        draft=render_exact_research_output(query,sources)
        if draft:
            st.session_state.activity.append("Exact research output contract passed")
            return draft,sources,research_result.get("error","")
    draft=await research_synthesis(query,sources) if sources else ""
    if draft:
        st.session_state.activity.append("Research synthesis completed")
    if not draft and sources and n<=len(sources):
        draft=render_exact_research_output(query,sources)
    if not draft:
        draft="⚠️ NEXUS could not verify enough current AI information from today's research results."
    return draft,sources,research_result.get("error","")


async def forex_pipeline(query):
    """Existing Forex Factory pipeline, isolated behind the router."""
    research_result = await forex_research(query)
    sources = research_result.get("sources", [])
    verified = []

    for source in sources:
        title = clean_text(source.get("title", ""))
        content = clean_text(source.get("content", ""))
        if not title and not content:
            continue
        summary = content[:500].strip()
        if len(content) > 500:
            summary = summary.rsplit(" ", 1)[0] + "…"
        if title and summary:
            verified.append(f"**{title}** — {summary}")
        elif title:
            verified.append(f"**{title}**")
        if len(verified) == 5:
            break

    if verified:
        return "**Forex Factory — High Impact / Economic Calendar**\n\n" + "\n\n".join(
            f"{i}. {item}" for i, item in enumerate(verified, 1)
        ), sources, research_result.get("error", "")

    return (
        "⚠️ NEXUS found Forex Factory results, but could not extract the calendar details from them."
        if sources else
        "⚠️ NEXUS could not find usable Forex Factory economic-calendar results for this request.",
        sources,
        research_result.get("error", ""),
    )


async def knowledge_pipeline(query, images=None):
    """Existing document/data/general Gemini pipeline."""
    return await gemini_text(build_context(query), images=images), [], ""


async def answer_user(query, images=None):
    started = time.perf_counter()
    st.session_state.activity = ["Understanding request"]

    route = detect_route(query, images=images)
    st.session_state.activity.append(f"Route: {route_label(route)}")

    if route == ROUTE_RESEARCH:
        st.session_state.activity.append("Deep research")
        draft, sources, error = await research_pipeline(query)
    elif route == ROUTE_FOREX:
        st.session_state.activity.append("Forex Factory research")
        draft, sources, error = await forex_pipeline(query)
    elif route == ROUTE_DATA:
        st.session_state.activity.append("Dataset analysis")
        draft, sources, error = await knowledge_pipeline(query, images=images)
    elif route == ROUTE_DOCUMENTS:
        st.session_state.activity.append("Document retrieval")
        draft, sources, error = await knowledge_pipeline(query, images=images)
    elif route == ROUTE_VISION:
        st.session_state.activity.append("Vision analysis")
        draft, sources, error = await knowledge_pipeline(query, images=images)
    else:
        st.session_state.activity.append("General reasoning")
        draft, sources, error = await knowledge_pipeline(query, images=images)

    draft = clean_ai_response(draft)
    if not draft:
        draft = "⚠️ NEXUS could not complete the request. Please try again."

    st.session_state.activity.extend(["Result checked", "Memory updated"])
    save_memory(query, draft)
    st.session_state.request_count += 1

    return {
        "answer": draft,
        "sources": sources,
        "route": route,
        "latency": time.perf_counter() - started,
        "error": error,
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

        if message.get("sources") and "sources" not in str(message.get("content", "")).lower():
            with st.expander("Sources"):
                for source in message["sources"]:
                    title = source.get("title", "Source")
                    url = source.get("url", "")
                    published = source_date(source)
                    if published:
                        st.markdown(f"**{title}** — Published: {published.isoformat()}")
                    else:
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

        if result["sources"] and "sources" not in str(result.get("answer", "")).lower():
            with st.expander("Sources"):
                for source in result["sources"]:
                    title = source.get("title", "Source")
                    url = source.get("url", "")
                    published = source_date(source)
                    if published:
                        st.markdown(f"**{title}** — Published: {published.isoformat()}")
                    else:
                        st.markdown(f"**{title}**")
                    if url:
                        st.markdown(url)

        st.session_state.messages.append({
            "role": "assistant",
            "content": result["answer"],
            "sources": result["sources"],
        })

    st.rerun()

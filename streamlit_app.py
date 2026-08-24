import os, re, json, sqlite3, asyncio, time, io, base64, hashlib, uuid, subprocess, sys, html, ast
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree as ET
from email.utils import parsedate_to_datetime
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
    """Parse common Tavily/provider publication-date representations."""
    if not isinstance(source, dict):
        return None
    values=[]
    keys=("published_date","publication_date","published","date","publishedAt","published_at","pub_date","timestamp")
    for k in keys:
        v=source.get(k)
        if v not in (None, ""):
            values.append(str(v).strip())
    for container_key in ("metadata","meta"):
        c=source.get(container_key)
        if isinstance(c,dict):
            for k in keys:
                v=c.get(k)
                if v not in (None, ""):
                    values.append(str(v).strip())
    months="January|February|March|April|May|June|July|August|September|October|November|December"
    short="Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    for raw in values:
        try:
            parsed = parsedate_to_datetime(raw)
            if parsed is not None:
                return parsed.date()
        except (TypeError, ValueError, OverflowError):
            pass
        m=re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?=\b|T|\s|$)",raw)
        if m:
            try: return date(int(m.group(1)),int(m.group(2)),int(m.group(3)))
            except ValueError: pass
        m=re.search(rf"\b({months}|{short})\s+(\d{{1,2}}),?\s+(20\d{{2}})\b",raw,re.I)
        if m:
            mon=m.group(1).title(); mon="Sep" if mon=="Sept" else mon
            for fmt in ("%B %d %Y","%b %d %Y"):
                try: return datetime.strptime(f"{mon} {m.group(2)} {m.group(3)}",fmt).date()
                except ValueError: pass
        m=re.search(rf"\b(\d{{1,2}})\s+({months}|{short}),?\s+(20\d{{2}})\b",raw,re.I)
        if m:
            mon=m.group(2).title(); mon="Sep" if mon=="Sept" else mon
            for fmt in ("%d %B %Y","%d %b %Y"):
                try: return datetime.strptime(f"{m.group(1)} {mon} {m.group(3)}",fmt).date()
                except ValueError: pass
    return None


def source_combined(source):
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    return f"{title} {content}".lower()


def is_relevant_ai_source(source, today, target_date=None):
    """High-precision gate for real current AI developments.

    RSS fallback records can have short descriptions, so a concrete event
    headline is allowed when the provider supplies a valid publication date.
    """
    title = clean_text(source.get("title", ""))
    content = clean_text(source.get("content", ""))
    title_lower = title.lower()
    content_lower = content.lower()
    published = source_date(source)

    if len(title) < 12:
        return False
    concrete_title_event = any(term in title_lower for term in (
        "launch", "release", "released", "announc", "unveil", "introduc",
        "deploy", "deployed", "acquir", "partner", "approved", "regulation",
        "policy", "rolls out", "rolled out", "ships", "opens", "opened",
        "publishes", "published", "signed", "expands", "cuts", "raises",
        "builds", "opens", "backs", "joins",
    ))
    if len(content) < 40 and not concrete_title_event:
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
    headline_ai = any(term in title_lower for term in RESEARCH_AI_TERMS) or bool(re.search(r"\bai\b", title_lower))
    named_ai_company = any(term in title_lower for term in (
        "openai", "anthropic", "gemini", "deepmind", "meta ai", "microsoft ai",
        "xai", "x.ai", "spacexai", "nvidia", "mistral", "deepseek",
        "hugging face", "huggingface", "qwen",
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
    """Return distinctive headline tokens for event-level deduplication."""
    title = clean_text(source.get("title", "")).lower()
    tokens = {t for t in re.findall(r"[a-z0-9]+", title) if not t.isdigit()}
    generic = {
        "ai", "artificial", "intelligence", "new", "latest", "today", "news",
        "company", "technology", "system", "report", "reports", "says", "said",
        "will", "could", "may", "according", "model", "models", "research",
        "study", "industry", "the", "and", "for", "with", "from", "that",
        "this", "its", "into", "over", "after", "about", "more", "than",
        "launch", "launches", "launched", "release", "released", "announced",
        "announces", "unveiled", "introduced", "deploy", "deployed", "deployment",
        "available", "opens", "opened", "published", "publishes", "newly",
        "product", "products", "distinct", "first", "announced", "launches",
    }
    return tokens - generic


EVENT_ANCHOR_TERMS = {
    "launch", "release", "model", "agent", "product", "platform",
    "deployment", "partnership", "acquisition", "acquired", "research",
    "study", "chip", "chips", "infrastructure", "data", "center",
    "placement", "funding", "investment", "financing", "shares", "share",
    "listing", "ipo", "raise", "raising", "spending", "contract",
    "regulation", "policy", "approval", "robot", "robotics",
}

def _event_title_tokens(source):
    """Return normalized, non-generic headline tokens used for event matching."""
    tokens = event_tokens(source)
    return {token for token in tokens if len(token) >= 3}

def same_event(a, b):
    """Determine whether two headlines describe the same underlying event.

    Different publishers often paraphrase the same event heavily. URL equality
    is definitive; otherwise require meaningful headline overlap plus at least
    one concrete event anchor. This prevents two unrelated AI stories from
    being merged merely because they share a company name and generic AI terms.
    """
    ua = normalize_url(a.get("url", ""))
    ub = normalize_url(b.get("url", ""))
    if ua and ub and ua == ub:
        return True

    ta = _event_title_tokens(a)
    tb = _event_title_tokens(b)
    shared = ta & tb
    if len(shared) < 3:
        return False

    anchors = shared & EVENT_ANCHOR_TERMS
    if not anchors:
        return False

    containment = len(shared) / max(1, min(len(ta), len(tb)))
    jaccard = len(shared) / max(1, len(ta | tb))

    # Paraphrased reports of one event commonly preserve several distinctive
    # nouns (e.g. Alibaba + Hong Kong + share + placement), while unrelated
    # stories generally do not.
    if len(shared) >= 5 and containment >= 0.50 and jaccard >= 0.30:
        return True

    # Keep the original stricter rule as a high-confidence fallback.
    return containment >= 0.80 and jaccard >= 0.55


def source_outlet_key(source):
    """Return the real publishing outlet for diversity checks.

    Google News RSS URLs all use news.google.com even though each RSS item
    represents a different publisher. Using the URL hostname here therefore
    incorrectly capped the fallback at two Google News results.
    """
    if not isinstance(source, dict):
        return ""
    provider = clean_text(source.get("source_provider", "")).lower()
    publisher = clean_text(source.get("publisher", ""))
    if provider == "google_news_rss" and publisher:
        return re.sub(r"[^a-z0-9]+", "-", publisher.lower()).strip("-")
    return source_domain(source.get("url", ""))


def select_distinct_sources(sources, limit=5):
    """Select the requested number of distinct events with outlet diversity."""
    selected = []
    seen_outlets = {}
    for source in sources:
        if any(same_event(source, old) for old in selected):
            continue
        # Limit repeated articles from the same actual publisher, not from the
        # Google News transport domain used by the RSS fallback.
        outlet = source_outlet_key(source)
        if outlet and seen_outlets.get(outlet, 0) >= 2:
            continue
        selected.append(source)
        if outlet:
            seen_outlets[outlet] = seen_outlets.get(outlet, 0) + 1
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

    # Prefer an explicit count whose intervening words describe the
    # developments themselves. Do not let phrases such as "one source for
    # each development" override the requested development count.
    count_pattern = r"\b([1-9]|10|one|two|three|four|five|six|seven|eight|nine|ten)\b(?:\s+(?!source\b|sources\b|per\b|each\b)\w+){0,5}\s+developments?\b"
    matches = list(re.finditer(count_pattern, text))
    if matches:
        raw = matches[0].group(1)
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


# -------------------- Phase 2/3 — Research Provider Abstraction --------------------

class ResearchProvider:
    name = "base"
    async def search(self, query, *, today, max_results=10, day_scoped=True):
        raise NotImplementedError


class TavilyResearchProvider(ResearchProvider):
    name = "tavily"
    def __init__(self, client):
        self.client = client

    async def search(self, query, *, today, max_results=10, day_scoped=True):
        kwargs={"query":query,"search_depth":"advanced","topic":"news","max_results":max_results,"include_answer":False}
        if day_scoped: kwargs["time_range"]="day"
        try:
            result=await asyncio.to_thread(self.client.search,**kwargs)
            return [x for x in (result.get("results",[]) if isinstance(result,dict) else []) if isinstance(x,dict)]
        except Exception as exc:
            text=str(exc).lower()
            # Do not hide provider failures behind a second identical request.
            # In particular, a Tavily 403 must immediately reach the
            # orchestrator so the configured fallback provider is attempted.
            if "forbidden" in text or "403" in text:
                raise PermissionError("Tavily rejected the request (Forbidden/403).") from exc
            if "429" in text or "rate limit" in text or "quota" in text:
                raise RuntimeError("Tavily rate limit/quota reached.") from exc

            # Some Tavily deployments reject optional news/time-range arguments.
            # A single simplified retry is safe for those non-auth failures.
            fallback={"query":query,"search_depth":"advanced","max_results":max_results,"include_answer":False}
            try:
                result=await asyncio.to_thread(self.client.search,**fallback)
                return [x for x in (result.get("results",[]) if isinstance(result,dict) else []) if isinstance(x,dict)]
            except Exception as retry_exc:
                retry_text=str(retry_exc).lower()
                if "forbidden" in retry_text or "403" in retry_text:
                    raise PermissionError("Tavily rejected the request (Forbidden/403).") from retry_exc
                if "429" in retry_text or "rate limit" in retry_text or "quota" in retry_text:
                    raise RuntimeError("Tavily rate limit/quota reached.") from retry_exc
                raise RuntimeError(f"Tavily search failed: {type(retry_exc).__name__}") from retry_exc


class GoogleNewsRSSProvider(ResearchProvider):
    name="google_news_rss"
    endpoint="https://news.google.com/rss/search"
    async def search(self, query, *, today, max_results=10, day_scoped=True):
        # RSS is the deterministic fallback when Tavily is unavailable. Keep
        # the query current, but allow a 48-hour window because RSS publication
        # timestamps can straddle midnight between UTC and Asia/Manila.
        rss_query = f"{query} when:2d" if day_scoped else query
        url=self.endpoint+"?"+urlencode({"q":rss_query,"hl":"en-US","gl":"US","ceid":"US:en"})
        def fetch():
            req=Request(url,headers={"User-Agent":"NEXUS-AI/phase2-research","Accept":"application/rss+xml, application/xml;q=0.9, */*;q=0.8"})
            with urlopen(req,timeout=12) as response: return response.read()
        try:
            root=ET.fromstring(await asyncio.to_thread(fetch))
        except HTTPError as exc: raise RuntimeError(f"Google News RSS HTTP {exc.code}") from exc
        except (URLError,ET.ParseError,TimeoutError,OSError) as exc: raise RuntimeError(f"Google News RSS unavailable: {type(exc).__name__}") from exc
        results=[]
        for item in root.findall('.//item')[:max_results]:
            title=clean_text(html.unescape(item.findtext('title','')))
            link=clean_text(item.findtext('link',''))
            desc=html.unescape(item.findtext('description','') or '')
            desc=re.sub(r"<[^>]+>", " ", desc)
            desc=clean_text(desc)
            pub=clean_text(item.findtext('pubDate',''))
            publisher=clean_text(html.unescape(item.findtext("source", "")))
            if title and link:
                results.append({"title":title,"url":link,"content":desc,"published_date":pub,"source_provider":self.name,"publisher":publisher})
        return results


class ResearchOrchestrator:
    """Provider failover with bounded retries and explicit diagnostics."""
    def __init__(self):
        self.providers=[]
        client=tavily_client()
        if client is not None: self.providers.append(TavilyResearchProvider(client))
        self.providers.append(GoogleNewsRSSProvider())

    async def search(self, queries, *, today, day_scoped=True, max_results=10):
        all_sources=[]; errors=[]
        for provider in self.providers:
            batch_all=[]; failed=False
            for query in queries:
                try:
                    batch_all.extend(await provider.search(query,today=today,max_results=max_results,day_scoped=day_scoped))
                    if len(batch_all)>=max_results*2: break
                except PermissionError:
                    errors.append(f"{provider.name}: ForbiddenError"); failed=True; break
                except Exception as exc:
                    errors.append(f"{provider.name}: {type(exc).__name__}"); failed=True; break
            if batch_all:
                all_sources.extend(batch_all)
                st.session_state.activity.append(f"Research provider: {provider.name} returned {len(batch_all)} candidate(s)")
            if failed:
                st.session_state.activity.append(f"Research provider failed: {provider.name}; trying next provider")
            if all_sources and provider.name != "tavily": break
        return all_sources,errors


async def research(query):
    requested_count=max(1,requested_development_count(query,default=5))
    today=datetime.now(ZoneInfo("Asia/Manila")).date(); exact_today=requires_exact_today(query)
    target_date=requested_research_date(query,today) or (today if exact_today else None); date_text=(target_date or today).isoformat(); focus=clean_text(query)[:500]
    current_queries=[
        focus,
        "AI latest developments launch release announcement",
        "OpenAI Anthropic Google Gemini Meta AI NVIDIA AI announcement launch",
        "AI model release launch unveiled announced",
        "AI agents robotics product deployment announcement",
        "AI research breakthrough study published",
        "AI regulation policy government announcement",
        "AI chips data center infrastructure announcement",
        "generative AI enterprise product deployment announcement",
    ]
    if exact_today or target_date==today:
        queries=current_queries
    else:
        queries=[f"{q} {date_text}" for q in current_queries]
    day_scoped=bool(exact_today or target_date==today)
    all_sources,provider_errors=await ResearchOrchestrator().search(queries,today=today,day_scoped=day_scoped,max_results=10)
    def unique(items):
        out=[]; seen=set()
        for item in items:
            key=normalize_url(item.get("url",""))
            if key and key not in seen: seen.add(key); out.append(item)
        return out
    allowed_dates={today}
    if exact_today or target_date==today: allowed_dates.add(today.fromordinal(today.toordinal()-1))
    def valid(items):
        out=[]
        for item in items:
            if not is_relevant_ai_source(item,today,target_date=None if (exact_today or target_date==today) else target_date): continue
            published=source_date(item)
            if exact_today or target_date==today:
                if published is not None and published not in allowed_dates: continue
            elif target_date is not None and published is not None and published!=target_date: continue
            out.append(item)
        return out
    unique_sources=unique(all_sources); filtered=valid(unique_sources)

    # Phase-2 fallback hardening: if the first current-news pass cannot produce
    # enough verified developments, make one broader RSS pass using concrete
    # event categories. This is especially important when Tavily returns 403
    # and Google News becomes the sole research provider.
    if len(filtered)<requested_count and day_scoped:
        supplemental_queries=[
            "AI company launches new model",
            "AI company announces new product",
            "AI research breakthrough AI study",
            "AI agents robotics new deployment",
            "AI chips data center new project",
            "AI policy regulation government new",
        ]
        supplemental_sources,supplemental_errors=await ResearchOrchestrator().search(
            supplemental_queries,today=today,day_scoped=True,max_results=12
        )
        if supplemental_sources:
            all_sources.extend(supplemental_sources)
            unique_sources=unique(all_sources)
            filtered=valid(unique_sources)
        provider_errors.extend(supplemental_errors)

    if len(filtered)<requested_count and (exact_today or target_date==today):
        relaxed_terms=("openai","anthropic","google","gemini","deepmind","meta ai","microsoft","xai","x.ai","spacexai","nvidia","mistral","deepseek","hugging face","huggingface","qwen","artificial intelligence","generative ai","machine learning","language model","llm","foundation model","ai agent","ai agents","ai chip","ai chips","robotics","robot")
        relaxed_noise=("horoscope","weather","sports","celebrity","recipe","travel","stock forecast","price target","prediction market","odds","protest","activist","boycott")
        existing={normalize_url(x.get("url","")) for x in filtered}
        for item in sorted(unique_sources,key=lambda x:research_score(x,today),reverse=True):
            published=source_date(item); title=clean_text(item.get("title","")); content=clean_text(item.get("content","")); low=title.lower()
            if published is not None and published not in allowed_dates: continue
            ai_signal = any(t in low for t in relaxed_terms) or bool(re.search(r"\bai\b", low))
            if len(title)<12 or len(content)<40 or not ai_signal or any(t in low for t in relaxed_noise): continue
            key=normalize_url(item.get("url",""))
            if key and key not in existing: filtered.append(item); existing.add(key)
    ranked=sorted(filtered,key=lambda x:research_score(x,today),reverse=True); final=select_distinct_sources(ranked,limit=requested_count)
    st.session_state.activity.append(f"Research diagnostic: requested={requested_count} raw={len(all_sources)} unique={len(unique(all_sources))} verified={len(filtered)} selected={len(final)}")
    if provider_errors: st.session_state.activity.append("Research provider diagnostics: "+", ".join(provider_errors[:4]))
    error="" if len(final)>=requested_count else f"Only {len(final)} independently verified current AI development(s) were available; {requested_count} requested."
    return {"sources":final,"requested_count":requested_count,"target_date":target_date.isoformat() if target_date else None,"error":error}


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
    """Route current-information requests even when the primary provider is unavailable."""
    q = clean_text(query).lower()
    if is_forex_query(query):
        return True
    research_words = (
        "latest", "today", "current", "news", "recent", "breaking",
        "developments", "what happened", "this week", "as of today",
    )
    return any(word in q for word in research_words)


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

# ============================================================
# PHASE 4–10 — Real foundations inside the current single-file deployment
# ============================================================

class SecurityPolicy:
    BLOCKED_PROMPT_PATTERNS=(r"ignore\s+(?:all\s+)?previous\s+instructions",r"reveal\s+(?:the\s+)?system\s+prompt",r"show\s+(?:me\s+)?(?:your|the)\s+api\s+key",r"print\s+(?:the\s+)?environment\s+variables?")
    @classmethod
    def inspect_prompt(cls,text):
        low=clean_text(text).lower(); violations=[p for p in cls.BLOCKED_PROMPT_PATTERNS if re.search(p,low)]
        return {"allowed":not violations,"violations":violations}
    @staticmethod
    def validate_remote_url(url):
        try:
            p=urlsplit(str(url).strip()); host=(p.hostname or "").lower()
            return p.scheme in {"http","https"} and bool(host) and not p.username and not p.password and host not in {"localhost","127.0.0.1","::1"} and not host.endswith((".local",".internal"))
        except Exception: return False

class UsageManager:
    def __init__(self,daily_limit=100): self.daily_limit=max(1,int(daily_limit))
    def _state(self):
        today=date.today().isoformat(); st.session_state.setdefault("usage_day",today); st.session_state.setdefault("usage_count",0)
        if st.session_state["usage_day"]!=today: st.session_state["usage_day"]=today; st.session_state["usage_count"]=0
        return st.session_state
    def can_consume(self,amount=1): return self._state()["usage_count"]+amount<=self.daily_limit
    def consume(self,amount=1):
        if not self.can_consume(amount): return False
        self._state()["usage_count"]+=amount; return True
    def remaining(self): return max(0,self.daily_limit-self._state()["usage_count"])

class ExecutionSandbox:
    ALLOWED=False
    @staticmethod
    def validate_python(code):
        if not isinstance(code,str) or not code.strip(): return False,"Empty code."
        if len(code)>12000: return False,"Code exceeds sandbox input limit."
        blocked=("import os","import subprocess","import socket","import shutil","import pathlib","import ctypes","__import__","eval(","exec(","open(")
        if any(x in code.lower() for x in blocked): return False,"Potentially unsafe operation rejected."
        try: tree=ast.parse(code,mode="exec")
        except SyntaxError as exc: return False,f"Syntax error: {exc}"
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)): return False,"Imports are disabled in the embedded sandbox."
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {"eval","exec","open","__import__"}: return False,f"Call to {node.func.id} is blocked."
        return True,"Code passed static safety checks."
    @classmethod
    def run(cls,code,timeout_seconds=3):
        if not cls.ALLOWED: return {"ok":False,"output":"","error":"Embedded execution is disabled; use an isolated worker/container."}
        ok,msg=cls.validate_python(code)
        if not ok: return {"ok":False,"output":"","error":msg}
        try:
            p=subprocess.run([sys.executable,"-I","-S","-c",code],capture_output=True,text=True,timeout=max(1,min(int(timeout_seconds),10)),check=False)
            return {"ok":p.returncode==0,"output":p.stdout[-8000:],"error":p.stderr[-4000:]}
        except subprocess.TimeoutExpired: return {"ok":False,"output":"","error":"Execution timed out."}
        except Exception as exc: return {"ok":False,"output":"","error":f"{type(exc).__name__}: {exc}"}

class TaskPlanner:
    def plan(self,query,route):
        return {"task_id":uuid.uuid4().hex,"route":route,"goal":clean_text(query),"steps":[{"id":1,"action":"understand","status":"pending"},{"id":2,"action":"retrieve_or_execute","status":"pending"},{"id":3,"action":"validate","status":"pending"},{"id":4,"action":"respond","status":"pending"}],"status":"planned"}

class AgentRegistry:
    def __init__(self): self.agents={ROUTE_RESEARCH:"Research Agent",ROUTE_FOREX:"Forex Agent",ROUTE_DATA:"Data Agent",ROUTE_DOCUMENTS:"Document/RAG Agent",ROUTE_VISION:"Vision Agent",ROUTE_GENERAL:"General Reasoning Agent"}
    def describe(self): return dict(self.agents)

class Observability:
    @staticmethod
    def event(name,**fields):
        payload={"event":name,"timestamp":datetime.now(timezone.utc).isoformat(),**fields}; st.session_state.setdefault("telemetry",[]).append(payload); st.session_state["telemetry"]=st.session_state["telemetry"][-200:]; return payload
    @staticmethod
    def health(): return {"gemini":bool(GEMINI_API_KEY and gemini_client()),"tavily":bool(TAVILY_API_KEY and tavily_client()),"groq":bool(GROQ_API_KEY and groq_client()),"research_fallback":True,"documents":len(st.session_state.documents),"datasets":len(st.session_state.datasets)}

class WorkspaceContext:
    def __init__(self,workspace_id="local"): self.workspace_id=clean_text(workspace_id) or "local"; st.session_state.setdefault("workspace_id",self.workspace_id)
    def scoped_key(self,key): return f"{self.workspace_id}:{key}"

class ProductionArchitecture:
    SERVICES=("api","agent_orchestrator","research","rag","memory","execution_worker","usage_billing","observability")
    @classmethod
    def manifest(cls): return {"services":list(cls.SERVICES),"high_availability":"requires external deployment infrastructure","multi_region_database":"requires external database/service","billing":"requires payment-provider integration","global_routing":"requires edge/load-balancing infrastructure"}

def initialize_phase_state():
    defaults={"telemetry":[],"usage_day":date.today().isoformat(),"usage_count":0,"workspace_id":"local","agent_log":[],"last_plan":None,"last_execution":None,"total_latency":0.0}
    for key,value in defaults.items(): st.session_state.setdefault(key,value)

initialize_phase_state()

# -------------------- Phase 2 — Multi-Agent Router --------------------

ROUTE_RESEARCH = "research"
ROUTE_FOREX = "forex"
ROUTE_DATA = "data"
ROUTE_DOCUMENTS = "documents"
ROUTE_VISION = "vision"
ROUTE_GENERAL = "general"

# Instantiate components only after route constants exist because the registry
# stores those symbolic route identifiers.
USAGE=UsageManager(); AGENTS=AgentRegistry(); PLANNER=TaskPlanner(); WORKSPACE=WorkspaceContext()

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
- Aim for the requested number of distinct developments, but if fewer can be supported by the selected evidence, explicitly say how many were verified and do not invent or duplicate a development.
- Use exactly ONE source for each verified development: the source assigned to that numbered item below.
- Do not introduce a source that is not in the selected evidence.
- Every factual claim about a development must be supported by its assigned source.
- For each verified development, explicitly cover: what happened, the organizations involved, why it matters (only when the source supports that significance), and the publication date.
- Put [Source N] immediately after each sentence or factual claim supported by that source. Do not place a citation only at the end of a paragraph containing multiple unsupported claims.
- If the source does not support a requested detail, say that the source does not provide that detail instead of guessing.
- If the user asks for publication dates, use only the PUBLISHED field supplied below.
- Include exactly one final Sources section containing ONLY the sources actually cited in the answer, one per verified development, in the same order.
- In the Sources section, use the source title and URL exactly as supplied. Do not add any other source or duplicate the section.

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


def validate_research_output(draft, query, sources):
    """Validate the minimum Phase 3 evidence-integrity contract."""
    text=clean_ai_response(draft)
    if not text:
        return False

    requested=requested_development_count(query, default=len(sources))
    source_markers=[int(x) for x in re.findall(r"\[Source\s+(\d+)\]", text, flags=re.I)]
    headings=re.findall(r"(?im)^\s*#{2,6}\s+Sources\s*$", text)
    if len(headings) != 1:
        return False

    if any(index < 1 or index > len(sources) for index in source_markers):
        return False

    lower=text.lower()
    verified_count=min(requested, len(sources))
    insufficient=verified_count < requested

    # A legitimate insufficiency response must explicitly acknowledge that the
    # requested count could not be verified rather than silently padding it.
    if insufficient and not re.search(r"\b(?:only|fewer than|less than|could not verify|unable to verify)\b", lower):
        return False

    if verified_count:
        # Require the evidence fields for each verified development.
        body=text.split("### Sources",1)[0]
        numbered_blocks=re.split(r"(?m)^\s*(?=(?:[1-9]|10)\.\s)", body)
        for index in range(1, verified_count + 1):
            match=re.search(rf"(?ms)^\s*{index}\.\s+(.*?)(?=^\s*(?:[1-9]|10)\.\s+|\Z)", body)
            if not match:
                return False
            block=match.group(0).lower()
            required=("what happened", "organizations involved", "why it matters", "publication date")
            if not all(label in block for label in required):
                return False
            block_sources={int(x) for x in re.findall(r"\[Source\s+(\d+)\]", block, flags=re.I)}
            if block_sources != {index}:
                return False

    # The Sources section may contain only the sources actually cited, once
    # each, and in the same order as the verified developments.
    sources_section=text.split("### Sources",1)[1]
    listed_numbers=[int(x) for x in re.findall(r"(?m)^\s*(\d+)\.\s", sources_section)]
    if listed_numbers != list(range(1, verified_count + 1)):
        return False

    return True


def render_exact_research_output(query,sources):
    """Produce an exact, one-source-per-development answer without model drift."""
    n=requested_development_count(query,default=len(sources)); selected=sources[:n]
    if len(selected)<n: return ""
    items=[]; source_lines=[]
    for i,src in enumerate(selected,1):
        title=clean_text(src.get("title",""))
        summary=source_grounded_summary(src)
        url=str(src.get("url","")).strip()
        published=source_date(src)
        if not title or not summary or not url: return ""
        published_text=published.isoformat() if published else "not provided by the source"
        items.append(
            f"{i}. **{title}**\n"
            f"- What happened: {summary} [Source {i}]\n"
            f"- Organizations involved: The source does not provide enough structured evidence to reliably extract this detail. [Source {i}]\n"
            f"- Why it matters: The source does not independently establish broader significance. [Source {i}]\n"
            f"- Publication date: {published_text} [Source {i}]"
        )
        source_lines.append(f"{i}. {title} — {url}")
    return "\n\n".join(items)+"\n\n### Sources\n"+"\n".join(source_lines)


async def research_pipeline(query):
    research_result=await research(query)
    sources=research_result.get("sources",[])
    n=requested_development_count(query,default=len(sources))
    st.session_state.activity.append(f"Selected {len(sources)} source(s) for the requested research output")
    exact_contract=(n>=1 and (requires_exact_today(query) or "exactly one source" in query.lower() or "sources section" in query.lower()))
    if exact_contract:
        # Phase 3 evidence-integrity requests must use the source-aware
        # synthesis layer first. The deterministic renderer remains only as a
        # fallback when the synthesis model is unavailable.
        draft=await research_synthesis(query,sources) if sources else ""
        if draft and validate_research_output(draft, query, sources):
            st.session_state.activity.append("Evidence-integrity research output contract passed")
            return draft,sources,research_result.get("error","")
        if draft:
            st.session_state.activity.append("Research synthesis failed output validation; using deterministic fallback")
    else:
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
    if not USAGE.consume():
        Observability.event("request_rejected", reason="daily_quota")
        return {"answer":"⚠️ NEXUS daily usage limit reached.","sources":[],"route":ROUTE_GENERAL,"latency":0.0,"error":"daily_quota"}
    security=SecurityPolicy.inspect_prompt(query)
    if not security["allowed"]:
        st.session_state.activity.append("Safety Agent: request blocked by input policy")
        Observability.event("request_rejected", reason="security_policy")
        return {"answer":"⚠️ NEXUS blocked this request because it attempts to override system controls or expose protected information.","sources":[],"route":ROUTE_GENERAL,"latency":0.0,"error":"security_policy"}
    route = detect_route(query, images=images)
    plan=PLANNER.plan(query,route); st.session_state.last_plan=plan
    st.session_state.agent_log.append({"task_id":plan["task_id"],"route":route,"status":"started","created_at":datetime.now(timezone.utc).isoformat()})
    Observability.event("request_started",route=route,task_id=plan["task_id"])
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
    latency=time.perf_counter()-started
    st.session_state.total_latency += latency
    st.session_state.activity.extend(["Result checked", "Memory updated"])
    save_memory(query, draft)
    st.session_state.request_count += 1
    Observability.event("request_completed",route=route,latency=round(latency,4),source_count=len(sources),error=bool(error))
    if st.session_state.agent_log: st.session_state.agent_log[-1].update({"status":"completed","latency":latency})

    return {
        "answer": draft,
        "sources": sources,
        "route": route,
        "latency": latency,
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
    st.write("🟢 Research fallback: Google News RSS")
    st.divider()
    st.markdown("### Usage")
    st.caption(f"{USAGE.remaining()} requests remaining today")

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
        health=Observability.health()
        st.caption("Health: "+", ".join(f"{k}={'up' if v else 'down'}" for k,v in health.items()))

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

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

                # Keep fallback requests compact enough for Groq's TPM limit.
        prompt = prompt[:6000]
        user_content = [
            {
                "type": "text",
                "text": prompt,
            }
        ]

        for _, image in images or []:
            buffer = io.BytesIO()
            image.convert("RGB").save(buffer, format="JPEG")
            image_data = base64.b64encode(
                buffer.getvalue()
            ).decode("utf-8")

            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}"
                    },
                }
            )

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="qwen/qwen3.6-27b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NEXUS, an intelligent AI assistant. "
                        "Answer clearly, accurately, and directly. "
                        "Do not reveal internal reasoning or thinking."
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

        answer = response.choices[0].message.content

        if not answer:
            return "⚠️ Groq returned an empty response."

        answer = re.sub(
            r"<think>.*?</think>",
            "",
            answer,
            flags=re.DOTALL | re.IGNORECASE
        ).strip()

        if not answer:
            return "⚠️ Groq returned an empty response."

        return answer

    except Exception as exc:
        return "⚠️ NEXUS is temporarily unable to complete the request. Please try again in a few minutes."
        
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

def clean_ai_response(text):
    if not text:
        return ""

    # Remove normal completed thinking blocks
    text = re.sub(
        r"<think>.*?</think>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<thinking>.*?</thinking>",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    # If the model starts a thinking block but never closes it,
    # discard everything from <think> onward.
    text = re.sub(
        r"<think>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    text = re.sub(
        r"<thinking>.*$",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    # Remove accidental "Sources" sections because NEXUS
    # displays Tavily sources separately.
    text = re.sub(
        r"\n\s*(Sources|Source List)\s*:?\s*$.*",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE
    )

    return text.strip()
 
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

            answer = clean_ai_response(response.text or "I received no text response.")
            return answer
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

                return await groq_text(prompt, images=images)

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

                        
    return "⚠️ NEXUS couldn't complete the request. Please try again."
async def research(query):
    client = tavily_client()

    if client is None:
        return {
            "answer": "",
            "sources": [],
            "error": "Tavily client is not available. Check TAVILY_API_KEY."
        }

    try:
        from datetime import date

        current_date = date.today().isoformat()

        # -------------------- Focused AI news searches --------------------

        search_queries = [
            f"AI artificial intelligence breaking news {current_date}",
            f"AI model launch release announced {current_date}",
            f"OpenAI Anthropic Google Gemini Meta Microsoft AI announcement {current_date}",
            f"NVIDIA AI chips data centers infrastructure {current_date}",
            f"AI startup funding acquisition partnership {current_date}",
            f"AI research technology breakthrough {current_date}",
            f"AI regulation government policy {current_date}",
            f"robotics AI agents autonomous systems {current_date}",
        ]

        all_sources = []

        for search_query in search_queries:
            try:
                result = await asyncio.to_thread(
                    client.search,
                    query=search_query,
                    search_depth="advanced",
                    topic="news",
                    time_range="day",
                    max_results=8,
                    include_answer=False,
                )

                for source in result.get("results", []):
                    all_sources.append(source)

            except Exception:
                continue

        # -------------------- Remove duplicate URLs --------------------

        unique_sources = []
        seen_urls = set()

        for source in all_sources:

            url = str(
                source.get("url", "")
            ).strip()

            if not url:
                continue

            normalized_url = url.rstrip("/").lower()

            if normalized_url in seen_urls:
                continue

            seen_urls.add(normalized_url)
            unique_sources.append(source)

        # -------------------- AI relevance filtering --------------------

        ai_terms = [
            "artificial intelligence",
            "artificial-intelligence",
            "machine learning",
            "generative ai",
            "ai model",
            "ai system",
            "ai agent",
            "ai research",
            "ai chip",
            "ai hardware",
            "ai infrastructure",
            "ai regulation",
            "ai policy",
            "ai safety",
            "ai startup",
            "ai coding",
            "ai software",
            "openai",
            "anthropic",
            "google deepmind",
            "gemini",
            "meta ai",
            "microsoft",
            "nvidia",
            "mistral",
            "z.ai",
            "glm",
            "robotics",
            "large language model",
            "llm",
            "foundation model",
            "open-weight",
            "open source model",
            "autonomous",
        ]

        # -------------------- Reject obvious noise --------------------

        irrelevant_terms = [
            "horoscope",
            "weather",
            "sports",
            "flight",
            "admissions",
            "insurance",
            "real estate",
            "celebrity",
            "recipe",
            "travel",
            "cosmetics",
            "veterinary",
            "petvivo",
            "quarterly earnings",
            "fiscal results",
            "share price",
            "stock market",
            "stock analysis",
            "investor outlook",
            "price target",
            "murder",
            "arrest",
            "crime",
            "criminal",
            "police",
            "fbi",
        ]

        # These are usually commentary/promotional pages rather
        # than primary AI developments.
        weak_source_terms = [
            "opinion",
            "commentary",
            "editorial",
            "why i created",
            "top 100",
            "weekly horoscope",
            "webinar",
            "conference registration",
            "conference announced",
        ]

        filtered_sources = []

        for source in unique_sources:

            title = str(
                source.get("title", "")
            ).strip()

            content = str(
                source.get("content", "")
            ).strip()

            published = str(
                source.get("published_date", "")
            ).strip()

            combined = (
                title.lower()
                + " "
                + content.lower()
                + " "
                + published.lower()
            )

            # Must actually discuss AI.
            if not any(
                term in combined
                for term in ai_terms
            ):
                continue

            # Reject obvious unrelated stories.
            if any(
                term in combined
                for term in irrelevant_terms
            ):
                continue

            # Reject obvious opinion/promotional pages.
            if any(
                term in combined
                for term in weak_source_terms
            ):
                continue

            if len(title) < 10:
                continue

            if len(content) < 100:
                continue

            filtered_sources.append(source)

        # -------------------- Prefer concrete developments --------------------

        development_terms = [
            "launched",
            "launches",
            "released",
            "release",
            "unveiled",
            "announced",
            "announces",
            "introduced",
            "deployed",
            "deployment",
            "partnered",
            "partnership",
            "acquired",
            "acquisition",
            "funding",
            "raised",
            "investment",
            "model",
            "research",
            "breakthrough",
            "regulation",
            "legislation",
            "chips",
            "data center",
            "infrastructure",
            "robotics",
            "agent",
        ]

        ranked_sources = []

        for source in filtered_sources:

            title = str(
                source.get("title", "")
            ).strip()

            content = str(
                source.get("content", "")
            ).strip()

            combined = (
                title.lower()
                + " "
                + content.lower()
            )

            score = 0

            for term in development_terms:
                if term in combined:
                    score += 2

            # Title matches are more important.
            title_lower = title.lower()

            for term in development_terms:
                if term in title_lower:
                    score += 4

            # Prefer sources with more substantive article text.
            if len(content) >= 500:
                score += 2

            if len(content) >= 1000:
                score += 2

            ranked_sources.append(
                (score, source)
            )

        ranked_sources.sort(
            key=lambda item: item[0],
            reverse=True
        )

        # -------------------- Deduplicate similar headlines --------------------

        final_sources = []
        seen_title_tokens = []

        for _, source in ranked_sources:

            title = str(
                source.get("title", "")
            ).strip()

            title_tokens = set(
                re.findall(
                    r"[a-zA-Z0-9]+",
                    title.lower()
                )
            )

            if not title_tokens:
                continue

            duplicate = False

            for previous_tokens in seen_title_tokens:

                overlap = len(
                    title_tokens & previous_tokens
                )

                similarity = (
                    overlap
                    / max(
                        len(title_tokens),
                        len(previous_tokens),
                        1
                    )
                )

                if similarity >= 0.60:
                    duplicate = True
                    break

            if duplicate:
                continue

            final_sources.append(source)
            seen_title_tokens.append(title_tokens)

            # Keep a reasonably large evidence pool.
            if len(final_sources) >= 15:
                break

        return {
            "answer": "",
            "sources": final_sources,
            "error": "",
        }

    except Exception as exc:
        return {
            "answer": "",
            "sources": [],
            "error": f"{type(exc).__name__}: {exc}",
        }
                    
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
    ]

    return bool(TAVILY_API_KEY) and any(
        word in q for word in research_words
    )
async def answer_user(query, images=None):
    started = time.perf_counter()

    st.session_state.activity = [
        "Understanding request",
        "Building plan"
    ]

    # -------------------- Local knowledge --------------------

    docs = retrieve_documents(query)

    document_context = "\n\n".join(
        f"[{d['name']}]\n{d['text'][:1000]}"
        for d in docs[:6]
    )

    memories = load_memories()

    memory_context = "\n\n".join(
        f"User: {u}\nNEXUS: {a[:500]}"
        for u, a in memories[-8:]
    )

    # -------------------- Normal AI prompt --------------------

    base_prompt = f"""
You are NEXUS, an intelligent AI assistant.

Answer the user's request directly and accurately.
Use uploaded documents when relevant.
Use memory only when relevant.
Do not reveal internal reasoning.

USER:
{query}

UPLOADED KNOWLEDGE:
{document_context or "(none)"}

RECENT MEMORY:
{memory_context or "(none)"}
"""

    # -------------------- Request routing --------------------

    if should_research(query):

        q_lower = query.lower()

        asks_latest_model = any(
            phrase in q_lower
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

        st.session_state.activity.append("Deep research")

        research_result = await research(query)

        if research_result.get("error"):
            st.session_state.activity.append("Research error")

        sources = research_result.get("sources", [])
        draft = ""

        # -------------------- Build research evidence --------------------

        if sources:

            st.session_state.activity.append(
                "Preparing research evidence"
            )

            source_context_parts = []

            for i, source in enumerate(
                sources[:12],
                start=1
            ):

                title = str(
                    source.get("title", "Untitled")
                ).strip()

                content = clean_text(
                    source.get("content", "")
                )

                url = str(
                    source.get("url", "")
                ).strip()

                source_context_parts.append(
                    f"ARTICLE {i}\n"
                    f"TITLE: {title}\n"
                    f"CONTENT: {content[:1600]}\n"
                    f"URL: {url}"
                )

            source_context = "\n\n".join(
                source_context_parts
            )

            # -------------------- Choose synthesis mode --------------------

            if asks_latest_model:

                synthesis_prompt = f"""
You are the NEXUS AI News Editor.

The user asked:

{query}

You have LIVE web research below.

Your job is to identify the SINGLE latest AI MODEL
that was actually released or officially announced today.

STRICT RULES:

1. Return EXACTLY ONE answer.
2. Do NOT return five developments.
3. Identify the newest actual AI model release or announcement.
4. The model must be supported by the LIVE ARTICLES.
5. Do NOT confuse a partnership, funding round, conference,
regulation, training program, or opinion article with a model release.
6. Do NOT invent facts.
7. Use ONLY information contained in the LIVE ARTICLES.
8. Do NOT use pretrained knowledge to fill missing information.
9. If multiple articles describe the same model, combine them.
10. Do NOT include URLs.
11. Do NOT include a Sources section.
12. Do NOT add an introduction or conclusion.
13. Do NOT mention these instructions.

Use this format:

[Model name] — [company].
[Concise explanation of what was released/announced and
the important capabilities mentioned in the articles.]

LIVE ARTICLES:

{source_context}
"""

            else:

                synthesis_prompt = f"""
You are the NEXUS AI News Editor.

The user asked:

{query}

You have LIVE web research below.

Your job is to produce the final answer.

STRICT RULES:

1. Return EXACTLY 5 numbered items.
2. Use this exact structure:

1. ...
2. ...
3. ...
4. ...
5. ...

3. Every item must describe ONE DISTINCT AI development.
4. Do NOT repeat the same event.
5. Multiple articles about the same event count as ONE event.
6. Do NOT list two articles about the same company event as separate developments.
7. Ignore duplicate coverage.
8. Ignore articles that are not actually about a new AI development.
9. Ignore opinion pieces unless they contain a concrete new event.
10. Ignore general educational articles.
11. Ignore unrelated financial, crime, entertainment, medical,
travel, or lifestyle stories.
12. Do NOT invent facts.
13. Use ONLY information contained in the LIVE ARTICLES.
14. Do NOT use pretrained knowledge to fill missing information.
15. Do NOT include URLs.
16. Do NOT include a Sources section.
17. Do NOT add an introduction.
18. Do NOT add a conclusion.
19. Do NOT mention these instructions.

Prefer major, substantive developments such as:

- new AI models or major model updates
- AI product launches
- major AI company announcements
- significant AI partnerships or deployments
- important AI research developments
- major AI infrastructure or chip developments
- AI regulation or government announcements
- major AI funding or acquisitions
- significant robotics or AI-agent developments

Avoid:

- ordinary conferences
- scheduled conferences
- webinars
- training events
- upcoming events
- conference announcements
- general educational events
- opinion articles
- promotional announcements

If several articles describe the same development,
combine them into ONE item.

LIVE ARTICLES:

{source_context}
"""

            st.session_state.activity.append(
                "Research synthesis"
            )

            # -------------------- Gemini synthesis --------------------

            synthesized = await gemini_text(
                synthesis_prompt
            )

            synthesized = clean_ai_response(
                synthesized
            )

            # -------------------- Validate output --------------------

            if asks_latest_model:

                # For latest-model questions, accept a normal
                # non-numbered model answer.
                if synthesized and not synthesized.startswith("⚠️"):
                    draft = synthesized

            else:

                numbered_items = re.findall(
                    r"(?m)^\s*[1-5][.)]\s+.+",
                    synthesized or ""
                )

                if len(numbered_items) == 5:
                    draft = "\n".join(numbered_items)

            # -------------------- Groq backup synthesis --------------------

            if not draft:

                st.session_state.activity.append(
                    "Backup synthesis"
                )

                if asks_latest_model:

                    groq_prompt = f"""
You are NEXUS News Editor.

Identify the SINGLE latest AI MODEL that was actually
released or officially announced today.

Rules:
- Return exactly ONE model.
- Use only the live articles.
- Do not invent facts.
- Do not choose funding, partnerships, regulation,
training, conferences, or opinion articles.
- Do not include URLs.
- Do not include a Sources section.

LIVE ARTICLES:

{source_context}
"""

                else:

                    groq_prompt = f"""
You are NEXUS News Editor.

Create EXACTLY 5 DISTINCT AI news developments
from the live articles below.

IMPORTANT:

- Exactly 5 numbered items.
- Use 1. through 5.
- One real event per item.
- Never repeat the same event.
- Combine duplicate coverage.
- Do not invent facts.
- Use only the articles.
- No introduction.
- No conclusion.
- No sources.
- No URLs.

LIVE ARTICLES:

{source_context}
"""

                synthesized = await groq_text(
                    groq_prompt
                )

                synthesized = clean_ai_response(
                    synthesized
                )

                if asks_latest_model:

                    if synthesized and not synthesized.startswith("⚠️"):
                        draft = synthesized

                else:

                    numbered_items = re.findall(
                        r"(?m)^\s*[1-5][.)]\s+.+",
                        synthesized or ""
                    )

                    if len(numbered_items) == 5:
                        draft = "\n".join(numbered_items)

            # -------------------- Evidence-based fallback --------------------

            if not draft:

                st.session_state.activity.append(
                    "Building evidence-based fallback"
                )

                if asks_latest_model:

                    for source in sources:

                        title = clean_text(
                            source.get("title", "")
                        )

                        content = clean_text(
                            source.get("content", "")
                        )

                        combined = (
                            title + " " + content
                        ).lower()

                        if any(
                            term in combined
                            for term in [
                                "model released",
                                "model launch",
                                "new model",
                                "unveiled",
                                "introduced",
                                "open-weight",
                                "foundation model",
                            ]
                        ):

                            draft = (
                                f"{title}\n\n"
                                f"{content[:600]}"
                            )

                            break

                else:

                    fallback_items = []
                    seen_events = []

                    for source in sources:

                        title = clean_text(
                            source.get(
                                "title",
                                "AI development"
                            )
                        )

                        content = clean_text(
                            source.get(
                                "content",
                                ""
                            )
                        )

                        if not title:
                            continue

                        title_tokens = set(
                            re.findall(
                                r"[a-zA-Z0-9]+",
                                title.lower()
                            )
                        )

                        duplicate = False

                        for previous in seen_events:

                            overlap = len(
                                title_tokens & previous
                            )

                            similarity = (
                                overlap /
                                max(
                                    len(title_tokens),
                                    len(previous),
                                    1
                                )
                            )

                            if similarity >= 0.55:
                                duplicate = True
                                break

                        if duplicate:
                            continue

                        seen_events.append(
                            title_tokens
                        )

                        if content:

                            summary = content[:300].strip()

                            fallback_items.append(
                                f"{len(fallback_items) + 1}. "
                                f"{title}: {summary}"
                            )

                        else:

                            fallback_items.append(
                                f"{len(fallback_items) + 1}. "
                                f"{title}"
                            )

                        if len(fallback_items) == 5:
                            break

                    if len(fallback_items) == 5:
                        draft = "\n".join(
                            fallback_items
                        )

        # -------------------- No research results --------------------

        if not draft:

            draft = (
                "⚠️ NEXUS could not find enough "
                "relevant AI information from today's "
                "live research. Please try again."
            )

    else:

        # -------------------- Normal Gemini request --------------------

        draft = await gemini_text(
            base_prompt,
            images=images
        )

        draft = clean_ai_response(
            draft
        )

    # -------------------- Final cleanup --------------------

    draft = clean_ai_response(
        draft
    )

    if not draft:

        draft = (
            "⚠️ NEXUS could not complete the request. "
            "Please try again."
        )

    st.session_state.activity.extend([
        "Result checked",
        "Memory updated"
    ])

    save_memory(
        query,
        draft
    )

    st.session_state.request_count += 1

    return {
        "answer": draft,
        "sources": (
            research_result.get("sources", [])
            if should_research(query)
            else []
        ),
        "latency": (
            time.perf_counter() - started
        ),
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

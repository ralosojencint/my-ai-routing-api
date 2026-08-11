import io
import os
import requests
import streamlit as st
from fpdf import FPDF
from PIL import Image

st.set_page_config(page_title="NEXUS", page_icon="✦", layout="centered")

# ------------------------------------------------------------
# KEYS
# ------------------------------------------------------------
def get_secret(name):
    try:
        value = st.secrets.get(name, "")
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, "")

GROQ_API_KEY = get_secret("GROQ_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")

# ------------------------------------------------------------
# STATE
# ------------------------------------------------------------
if "chats" not in st.session_state:
    st.session_state.chats = {
        "chat_1": {"title": "New conversation", "messages": []}
    }

if "chat_id" not in st.session_state:
    st.session_state.chat_id = "chat_1"

chat = st.session_state.chats[st.session_state.chat_id]

# ------------------------------------------------------------
# STYLE
# ------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {max-width: 820px; padding-top: 35px; padding-bottom: 220px;}
    .nexus-title {text-align:center; font-size:34px; font-weight:800; letter-spacing:8px; margin-bottom:6px;}
    .nexus-sub {text-align:center; color:#777; font-size:13px; margin-bottom:42px;}
    .user-row {display:flex; justify-content:flex-end; margin:18px 0;}
    .user-bubble {max-width:78%; background:#19191d; border:1px solid #2b2b31; padding:12px 16px; border-radius:18px 18px 5px 18px;}
    .ai-label {font-size:10px; letter-spacing:2px; color:#777; margin-bottom:7px;}
    .ai-block {margin:24px 0 34px; line-height:1.7;}
    .source {border-top:1px solid #25252a; padding:9px 0; font-size:12px;}
    .source a {color:#ddd; text-decoration:none;}
    .source-url {color:#666; font-size:10px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
    .composer-wrap {margin-top:35px; padding:10px; border:1px solid #303035; border-radius:18px; background:#151518;}
    div[data-testid="stForm"] {
        position:fixed !important;
        left:50% !important;
        bottom:12px !important;
        top:auto !important;
        transform:translateX(-50%) !important;
        width:min(760px, calc(100vw - 24px)) !important;
        z-index:999999 !important;
        background:#151518 !important;
        border:1px solid #303035 !important;
        border-radius:18px !important;
        padding:10px !important;
        box-shadow:0 12px 40px rgba(0,0,0,.65) !important;
    }

    div[data-testid="stForm"] > div {
        background:transparent !important;
    }
    div[data-testid="stTextInput"] input {background:#151518 !important; color:#eee !important; border:1px solid #303035 !important; border-radius:13px !important;}
    div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {background:#19191d !important; border:1px solid #303035 !important; border-radius:10px !important;}
    [data-testid="stSidebar"] {background:#0e0e10;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------------------------------------------------
# SIDEBAR / HISTORY
# ------------------------------------------------------------
with st.sidebar:
    st.markdown("## NEXUS")

    if st.button("＋ New chat", use_container_width=True):
        number = len(st.session_state.chats) + 1
        new_id = "chat_" + str(number)
        st.session_state.chats[new_id] = {"title": "New conversation", "messages": []}
        st.session_state.chat_id = new_id
        st.rerun()

    st.divider()
    st.caption("HISTORY")

    for cid, item in reversed(list(st.session_state.chats.items())):
        title = item["title"][:36]
        if st.button(title, key="history_" + cid, use_container_width=True):
            st.session_state.chat_id = cid
            st.rerun()

    st.divider()
    if st.button("Clear current chat", use_container_width=True):
        chat["messages"] = []
        chat["title"] = "New conversation"
        st.rerun()

# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------
st.markdown('<div class="nexus-title">NEXUS</div>', unsafe_allow_html=True)
st.markdown('<div class="nexus-sub">Research first. Answer second.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# WEB SEARCH
# ------------------------------------------------------------
def web_search(query, deep=False):
    if not TAVILY_API_KEY:
        return []

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "advanced" if deep else "basic",
                "topic": "general",
                "max_results": 8 if deep else 4,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=35,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        results = []
        for item in data.get("results", []):
            results.append(
                {
                    "title": item.get("title", "Source"),
                    "url": item.get("url", ""),
                    "content": item.get("content", "")[:900],
                }
            )
        return results
    except Exception:
        return []

# ------------------------------------------------------------
# SMART RESEARCH ROUTER
# ------------------------------------------------------------
def needs_web_search(question, deep=False):
    if deep:
        return True

    q = " ".join(question.lower().strip().split())

    casual_exact = {
        "hi", "hello", "hey", "yo", "sup", "hiya",
        "thanks", "thank you", "thx", "ok", "okay",
        "good morning", "good afternoon", "good evening",
        "good night", "lol", "lmao", "haha", "how are you",
        "what's up", "whats up"
    }

    if q in casual_exact:
        return False

    if q.startswith((
        "hi ", "hello ", "hey ", "yo ", "thanks ",
        "thank you ", "good morning ", "good afternoon "
    )):
        return False

    web_triggers = (
        "latest", "today", "current", "right now", "this week",
        "this month", "recent", "news", "price", "prices",
        "weather", "score", "scores", "stock", "stocks",
        "who won", "what happened", "search the web",
        "look it up", "research", "sources", "according to",
        "2026", "2025"
    )

    return any(trigger in q for trigger in web_triggers)

# ------------------------------------------------------------
# GROQ
# ------------------------------------------------------------
def ask_ai(question, sources, deep):
    if not GROQ_API_KEY:
        return "GROQ_API_KEY is missing. Add it to Streamlit Secrets."

    evidence = ""
    for i, source in enumerate(sources, 1):
        evidence += (
            f"\nSOURCE {i}\n"
            f"Title: {source['title']}\n"
            f"URL: {source['url']}\n"
            f"Evidence: {source['content']}\n"
        )

    recent = ""
    for message in chat["messages"][-6:]:
        recent += f"\n{message['role']}: {message['content'][:500]}"

    mode = "DEEP RESEARCH" if deep else ("WEB RESEARCH" if sources else "NORMAL CHAT")
    prompt = f"""
You are NEXUS, a professional AI assistant with a natural personality.

MODE: {mode}

USER QUESTION:
{question}

WEB EVIDENCE:
{evidence if evidence else "No web research was requested for this message. Answer naturally from your knowledge."}

RECENT CHAT:
{recent}

Rules:
- If there is no web evidence, do NOT pretend that you researched anything.
- Never invent sources or citations.
- Only use [1], [2], etc. when actual sources are provided.
- Be clear, useful and direct.
- For casual conversation, respond like a normal intelligent person.
- Have natural, quick humor when it fits.
- Do not explain obvious greetings.
- Never sound robotic, childish, or cringe.
- If current information is needed but no research was performed, say so rather than pretending.
"""

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are NEXUS."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.4,
                "max_completion_tokens": 1800,
            },
            timeout=90,
        )

        if response.status_code == 413:
            return "The research package was too large. Try a shorter question."
        if response.status_code != 200:
            return "NEXUS AI error: " + response.text
        return response.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return "NEXUS error: " + str(exc)

# ------------------------------------------------------------
# CHAT DISPLAY
# ------------------------------------------------------------
for message in chat["messages"]:
    if message["role"] == "user":
        st.markdown(
            '<div class="user-row"><div class="user-bubble">'
            + message["content"]
            + '</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="ai-block"><div class="ai-label">NEXUS</div>', unsafe_allow_html=True)
        st.markdown(message["content"])
        st.markdown('</div>', unsafe_allow_html=True)

        sources = message.get("sources", [])
        if sources:
            st.caption("SOURCES")
            for i, source in enumerate(sources, 1):
                st.markdown(
                    '<div class="source"><b>['
                    + str(i)
                    + ']</b> <a href="'
                    + source["url"]
                    + '" target="_blank">'
                    + source["title"]
                    + '</a><div class="source-url">'
                    + source["url"]
                    + '</div></div>',
                    unsafe_allow_html=True,
                )

# ------------------------------------------------------------
# COMPOSER - THIS IS THE LAST UI ELEMENT, SO IT STAYS AT BOTTOM
# ------------------------------------------------------------
st.markdown('<div class="composer-wrap">', unsafe_allow_html=True)

with st.form("nexus_composer", clear_on_submit=True):
    question = st.text_input(
        "Question",
        placeholder="Ask NEXUS anything...",
        label_visibility="collapsed",
    )

    left, right = st.columns([3, 1])
    with left:
        mode = st.selectbox(
            "Research mode",
            ["Quick", "Deep Research"],
            label_visibility="collapsed",
        )
    with right:
        send = st.form_submit_button("↑ Send", use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# PROCESS
# ------------------------------------------------------------
if send and question.strip():
    question = question.strip()
    deep = mode == "Deep Research"

    if chat["title"] == "New conversation":
        chat["title"] = question[:36]

    chat["messages"].append({"role": "user", "content": question})

    q = " ".join(question.lower().split())

    # Hard bypass: greetings never touch Tavily or web search.
    casual_replies = {
        "hi": "Hey! 👋 What’s up?",
        "hello": "Hey! 👋 How can I help?",
        "hey": "Hey! 😎 What are we working on?",
        "yo": "Yo! 😎 What’s up?",
        "sup": "Not much — just waiting for you to break something interesting. 😂 What’s up?",
        "thanks": "Anytime! 😎",
        "thank you": "Anytime! 😎",
        "good morning": "Good morning! ☀️ Let’s make it a productive one.",
        "good night": "Good night! 🌙 Don’t start another project at 2 AM. 😂",
        "lol": "😂 I’ll take that as a good sign.",
        "lmao": "😂 Okay, we’re off to a good start."
    }

    if not deep and q in casual_replies:
        sources = []
        answer = casual_replies[q]
    else:
        do_research = needs_web_search(question, deep)

        if do_research:
            with st.spinner("Deep researching..." if deep else "Checking the web..."):
                sources = web_search(question, deep)
                answer = ask_ai(question, sources, deep)
        else:
            sources = []
            answer = ask_ai(question, sources, False)

    chat["messages"].append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })

    st.rerun()

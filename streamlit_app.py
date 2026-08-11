import os
import requests
import streamlit as st
import html

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered"
)

# ============================================================
# NEXUS — RESEARCH ENGINE
# ============================================================

# ---------- SECRETS ----------

def secret(name):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, "")

GROQ_API_KEY = secret("GROQ_API_KEY")
TAVILY_API_KEY = secret("TAVILY_API_KEY")


# ---------- SESSION ----------

if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# PROFESSIONAL UI
# ============================================================

st.markdown("""
<style>

html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont,
    "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.stApp {
    background: #0b0b0d;
    color: #eeeeef;
}

.block-container {
    max-width: 780px;
    padding-top: 55px;
    padding-bottom: 120px;
}

/* Remove Streamlit decoration */

header {
    background: transparent !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

/* Logo */

.nexus-brand {
    text-align: center;
    margin-bottom: 8px;
}

.nexus-name {
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 8px;
    color: #f5f5f5;
}

.nexus-line {
    width: 28px;
    height: 2px;
    background: #eeeeee;
    margin: 13px auto 0 auto;
    opacity: .7;
}

.nexus-description {
    text-align: center;
    color: #77777d;
    font-size: 13px;
    margin-top: 13px;
    margin-bottom: 45px;
}

/* Custom chat */

.user-message {
    display: flex;
    justify-content: flex-end;
    margin: 20px 0;
}

.user-bubble {
    max-width: 78%;
    background: #1c1c20;
    border: 1px solid #29292e;
    border-radius: 18px 18px 5px 18px;
    padding: 12px 16px;
    color: #eeeeef;
    line-height: 1.55;
}

.ai-message {
    margin: 25px 0 35px 0;
}

.ai-label {
    color: #88888f;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 9px;
}

.ai-content {
    color: #eeeeef;
    line-height: 1.7;
    font-size: 15px;
}

/* Research status */

.research-status {
    color: #85858b;
    font-size: 13px;
    margin: 15px 0;
}

/* Sources */

.sources-title {
    color: #77777d;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-top: 24px;
    margin-bottom: 10px;
}

.source {
    border-top: 1px solid #222226;
    padding: 12px 0;
}

.source-number {
    color: #55555b;
    font-size: 11px;
}

.source-title {
    color: #dddddf;
    font-size: 13px;
    margin-top: 3px;
}

.source-url {
    color: #66666c;
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* Bottom input */

[data-testid="stChatInput"] {
    background: transparent;
}

[data-testid="stChatInput"] textarea {
    background: #151518 !important;
    border: 1px solid #303035 !important;
    border-radius: 18px !important;
    color: #eeeeef !important;
}

[data-testid="stChatInput"] textarea:focus {
    border-color: #55555c !important;
    box-shadow: none !important;
}

/* Sidebar */

[data-testid="stSidebar"] {
    background: #0e0e10;
    border-right: 1px solid #202024;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# HEADER
# ============================================================

st.markdown("""
<div class="nexus-brand">
    <div class="nexus-name">NEXUS</div>
    <div class="nexus-line"></div>
</div>

<div class="nexus-description">
    Research first. Answer second.
</div>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("### NEXUS")

    st.caption("Research-first intelligence")

    st.divider()

    mode = st.selectbox(
        "Mode",
        [
            "General",
            "Coding",
            "Business",
            "Research",
            "Writing"
        ]
    )

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True
    ):
        st.session_state.messages = []
        st.rerun()


# ============================================================
# WEB SEARCH
# ============================================================

def search_web(query):

    if not TAVILY_API_KEY:
        return [], "TAVILY_API_KEY is missing."

    try:

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "topic": "general",
                "max_results": 5,
                "include_answer": False,
                "include_raw_content": False
            },

            timeout=30
        )

        if response.status_code != 200:
            return [], response.text

        data = response.json()

        results = []

        for item in data.get("results", [])[:5]:

            results.append({
                "title": item.get(
                    "title",
                    "Untitled"
                ),
                "url": item.get(
                    "url",
                    ""
                ),
                "content": item.get(
                    "content",
                    ""
                )[:1400]
            })

        return results, None

    except Exception as e:

        return [], str(e)


# ============================================================
# GROQ
# ============================================================

def ask_groq(question, research, history):

    if not GROQ_API_KEY:

        return (
            "Your Groq API key is missing. "
            "Add `GROQ_API_KEY` to Streamlit Secrets."
        )

    # IMPORTANT:
    # Keep the request small so we don't hit 413.

    source_text = ""

    for i, source in enumerate(
        research[:5],
        start=1
    ):

        source_text += f"""

SOURCE {i}
Title: {source["title"]}
URL: {source["url"]}
Evidence:
{source["content"][:1200]}
"""


    recent_history = ""

    for item in history[-4:]:

        recent_history += (
            f'\n{item["role"]}: '
            f'{item["content"][:700]}'
        )


    prompt = f"""
You are NEXUS.

You are a research-first AI assistant.

USER QUESTION:
{question}

WEB EVIDENCE:
{source_text}

RECENT CONVERSATION:
{recent_history}

Answer using the evidence above.

Rules:

- Do not invent facts.
- Prefer claims supported by multiple sources.
- If sources disagree, say so.
- If evidence is weak, say so.
- Use [1], [2], etc. for source references.
- Be concise but useful.
- Current information should be based on the supplied web evidence.

PERSONALITY:

NEXUS is intelligent, calm, direct and slightly funny.

Humor is occasional and natural.

Never force jokes.

Never use cringe AI/robot language.

A little dry humor is okay when appropriate.

Mode: {mode}
"""


    try:

        response = requests.post(

            "https://api.groq.com/openai/v1/chat/completions",

            headers={
                "Authorization":
                    "Bearer " + GROQ_API_KEY,

                "Content-Type":
                    "application/json"
            },

            json={
                "model":
                    "llama-3.3-70b-versatile",

                "messages": [
                    {
                        "role":
                            "system",

                        "content":
                            "You are NEXUS."
                    },
                    {
                        "role":
                            "user",

                        "content":
                            prompt
                    }
                ],

                "temperature":
                    0.45,

                "max_completion_tokens":
                    1800
            },

            timeout=90
        )


        if response.status_code == 413:

            return (
                "The research request was too large. "
                "I trimmed the sources, but Groq still "
                "rejected it. We can reduce it further."
            )


        if response.status_code != 200:

            return (
                "NEXUS AI error: "
                + response.text
            )


        data = response.json()

        return data[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]


    except Exception as e:

        return f"NEXUS AI error: {e}"


# ============================================================
# RENDER SOURCES
# ============================================================

def render_sources(sources):

    if not sources:
        return

    st.markdown(
        '<div class="sources-title">Sources</div>',
        unsafe_allow_html=True
    )

    for i, source in enumerate(
        sources,
        start=1
    ):

        title = html.escape(
            source["title"]
        )

        url = html.escape(
            source["url"]
        )

        st.markdown(
            f"""
<div class="source">

<div class="source-number">
{str(i).zfill(2)}
</div>

<div class="source-title">
<a href="{url}" target="_blank"
style="color:#dddddf;text-decoration:none;">
{title}
</a>
</div>

<div class="source-url">
{url}
</div>

</div>
""",
            unsafe_allow_html=True
        )


# ============================================================
# RENDER OLD MESSAGES
# ============================================================

for message in st.session_state.messages:

    if message["role"] == "user":

        safe = html.escape(
            message["content"]
        )

        st.markdown(
            f"""
<div class="user-message">

<div class="user-bubble">
{safe}
</div>

</div>
""",
            unsafe_allow_html=True
        )

    else:

        content = message["content"]

        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">NEXUS</div>'
            '<div class="ai-content">',
            unsafe_allow_html=True
        )

        st.markdown(
            content
        )

        st.markdown(
            "</div></div>",
            unsafe_allow_html=True
        )

        render_sources(
            message.get(
                "sources",
                []
            )
        )


# ============================================================
# BOTTOM CHAT
# ============================================================

question = st.chat_input(
    "Ask NEXUS anything..."
)


if question:

    # USER

    st.session_state.messages.append({

        "role":
            "user",

        "content":
            question
    })


    safe_question = html.escape(
        question
    )


    st.markdown(
        f"""
<div class="user-message">

<div class="user-bubble">
{safe_question}
</div>

</div>
""",
        unsafe_allow_html=True
    )


    # SEARCH

    status = st.empty()

    status.markdown(
        '<div class="research-status">'
        'Searching the web…'
        '</div>',
        unsafe_allow_html=True
    )


    sources, search_error = search_web(
        question
    )


    if search_error:

        status.empty()

        answer = (
            "I couldn't complete the web search.\n\n"
            + search_error
        )

        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">NEXUS</div>'
            '<div class="ai-content">',
            unsafe_allow_html=True
        )

        st.markdown(answer)

        st.markdown(
            "</div></div>",
            unsafe_allow_html=True
        )

        st.session_state.messages.append({

            "role":
                "assistant",

            "content":
                answer,

            "sources":
                []
        })

    else:

        status.markdown(
            '<div class="research-status">'
            'Checking sources…'
            '</div>',
            unsafe_allow_html=True
        )


        # ASK AI

        answer = ask_groq(

            question,

            sources,

            st.session_state.messages
        )


        status.empty()


        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">NEXUS</div>'
            '<div class="ai-content">',
            unsafe_allow_html=True
        )

        st.markdown(answer)

        st.markdown(
            "</div></div>",
            unsafe_allow_html=True
        )


        render_sources(
            sources
        )


        # SAVE

        st.session_state.messages.append({

            "role":
                "assistant",

            "content":
                answer,

            "sources":
                sources
        })

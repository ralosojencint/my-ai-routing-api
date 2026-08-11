import os
import html
import requests
import streamlit as st

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered"
)

# ============================================================
# KEYS
# ============================================================

def get_key(name):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, "")

GROQ = get_key("GROQ_API_KEY")
TAVILY = get_key("TAVILY_API_KEY")

# ============================================================
# SESSION
# ============================================================

if "chats" not in st.session_state:
    st.session_state.chats = {
        "chat_1": {
            "title": "New conversation",
            "messages": []
        }
    }

if "chat_id" not in st.session_state:
    st.session_state.chat_id = "chat_1"

chat = st.session_state.chats[st.session_state.chat_id]

# ============================================================
# CSS
# ============================================================

st.markdown("""
<style>
.stApp {
    background: #0b0b0d;
    color: #eeeeee;
}

.block-container {
    max-width: 760px;
    padding-top: 45px;
    padding-bottom: 180px;
}

.nexus {
    text-align: center;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: 8px;
}

.sub {
    text-align: center;
    color: #68686f;
    font-size: 13px;
    margin: 12px 0 45px;
}

.user {
    display: flex;
    justify-content: flex-end;
    margin: 20px 0;
}

.bubble {
    background: #19191d;
    border: 1px solid #29292e;
    padding: 12px 16px;
    border-radius: 18px 18px 5px 18px;
    max-width: 78%;
    line-height: 1.55;
}

.ai {
    margin: 25px 0 35px;
}

.label {
    font-size: 11px;
    letter-spacing: 2px;
    color: #777777;
    margin-bottom: 8px;
}

.answer {
    line-height: 1.7;
    font-size: 15px;
}

.source {
    border-top: 1px solid #222226;
    padding: 10px 0;
}

.source small {
    color: #666666;
}

.status {
    color: #777777;
    font-size: 13px;
    margin: 10px 0;
}

[data-testid="stSidebar"] {
    background: #0e0e10;
}

div[data-testid="stForm"] {
    position: fixed !important;
    bottom: 15px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    width: min(720px, calc(100vw - 24px)) !important;
    z-index: 999999 !important;
    background: #151518 !important;
    border: 1px solid #303035 !important;
    border-radius: 18px !important;
    padding: 10px !important;
    box-shadow: 0 12px 45px rgba(0,0,0,.55) !important;
}

div[data-testid="stForm"] input {
    background: #151518 !important;
    color: #eeeeee !important;
    border: 0 !important;
    box-shadow: none !important;
}

div[data-testid="stForm"] div[data-baseweb="select"] > div {
    background: #19191d !important;
    border: 1px solid #303035 !important;
    border-radius: 10px !important;
}

div[data-testid="stForm"] button {
    border-radius: 10px !important;
}

@media (max-width: 600px) {
    .block-container {
        padding-bottom: 200px;
    }

    .nexus {
        font-size: 29px;
    }

    div[data-testid="stForm"] {
        width: calc(100vw - 20px) !important;
        bottom: 8px !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("## NEXUS")

    if st.button("＋ New chat", use_container_width=True):

        number = len(st.session_state.chats) + 1
        new_id = "chat_" + str(number)

        st.session_state.chats[new_id] = {
            "title": "New conversation",
            "messages": []
        }

        st.session_state.chat_id = new_id
        st.rerun()

    st.divider()
    st.caption("HISTORY")

    items = list(st.session_state.chats.items())
    items.reverse()

    for cid, item in items:

        title = item["title"][:38]

        if st.button(
            title,
            key="history_" + cid,
            use_container_width=True
        ):
            st.session_state.chat_id = cid
            st.rerun()

# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="nexus">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub">Research first. Answer second.</div>',
    unsafe_allow_html=True
)

# ============================================================
# SEARCH WEB
# ============================================================

def search_web(query, deep=False):

    if not TAVILY:
        return []

    try:

        depth = "advanced" if deep else "basic"
        amount = 8 if deep else 4

        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY,
                "query": query,
                "search_depth": depth,
                "topic": "general",
                "max_results": amount,
                "include_answer": False
            },
            timeout=35
        )

        if response.status_code != 200:
            return []

        data = response.json()

        results = []

        for item in data.get("results", []):

            results.append({
                "title": item.get("title", "Source"),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:850]
            })

        return results

    except Exception:
        return []

# ============================================================
# AI
# ============================================================

def ask_ai(question, sources, deep):

    if not GROQ:
        return "GROQ_API_KEY is missing."

    evidence = ""

    for i, source in enumerate(sources[:8], 1):

        evidence += (
            "\nSOURCE " + str(i) +
            "\nTitle: " + source["title"] +
            "\nURL: " + source["url"] +
            "\nEvidence: " + source["content"] +
            "\n"
        )

    history = ""

    for message in chat["messages"][-4:]:

        history += (
            "\n" +
            message["role"] +
            ": " +
            message["content"][:400]
        )

    mode = "DEEP RESEARCH" if deep else "QUICK"

    prompt = f"""
You are NEXUS.

Mode: {mode}

Question:
{question}

Web evidence:
{evidence}

Recent conversation:
{history}

Answer accurately.

Rules:
- Never invent facts.
- Use [1], [2], etc. for important sources.
- Compare sources when useful.
- Say when evidence is insufficient.
- Be direct and useful.
- Have a smart, calm personality.
- Light natural humor is allowed.
- Never force jokes.
"""

    try:

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ,
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are NEXUS."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.4,
                "max_completion_tokens": 1800
            },
            timeout=90
        )

        if response.status_code == 413:
            return "The research data was too large. Try a shorter question."

        if response.status_code != 200:
            return "NEXUS AI error: " + response.text

        data = response.json()

        return data["choices"][0]["message"]["content"]

    except Exception as e:

        return "NEXUS error: " + str(e)

# ============================================================
# SHOW CHAT
# ============================================================

for message in chat["messages"]:

    if message["role"] == "user":

        text = html.escape(message["content"])

        st.markdown(
            '<div class="user">'
            '<div class="bubble">' +
            text +
            '</div></div>',
            unsafe_allow_html=True
        )

    else:

        st.markdown(
            '<div class="ai">'
            '<div class="label">NEXUS</div>'
            '<div class="answer">',
            unsafe_allow_html=True
        )

        st.markdown(message["content"])

        st.markdown(
            '</div></div>',
            unsafe_allow_html=True
        )

        sources = message.get("sources", [])

        if sources:

            st.caption("SOURCES")

            for i, source in enumerate(sources, 1):

                title = html.escape(source["title"])
                url = html.escape(source["url"])

                st.markdown(
                    '<div class="source">'
                    '<b>[' + str(i) + ']</b> '
                    '<a href="' + url + '" target="_blank">'
                    + title +
                    '</a><br>'
                    '<small>' + url + '</small>'
                    '</div>',
                    unsafe_allow_html=True
                )

# ============================================================
# BOTTOM COMPOSER
# ============================================================

with st.form("nexus_composer", clear_on_submit=True):

    question = st.text_input(
        "Question",
        placeholder="Ask NEXUS anything...",
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([3, 1])

    with col1:

        mode = st.selectbox(
            "Research mode",
            ["Quick", "Deep Research"],
            label_visibility="collapsed"
        )

    with col2:

        send = st.form_submit_button(
            "↑ Send",
            use_container_width=True
        )

# ============================================================
# PROCESS
# ============================================================

if send and question.strip():

    question = question.strip()

    deep = mode == "Deep Research"

    if chat["title"] == "New conversation":

        chat["title"] = question[:38]

    chat["messages"].append({
        "role": "user",
        "content": question
    })

    status = st.empty()

    if deep:

        status.markdown(
            '<div class="status">'
            'Researching multiple sources...'
            '</div>',
            unsafe_allow_html=True
        )

        sources = search_web(question, True)

    else:

        status.markdown(
            '<div class="status">'
            'Searching...'
            '</div>',
            unsafe_allow_html=True
        )

        sources = search_web(question, False)

    status.markdown(
        '<div class="status">'
        'Analyzing evidence...'
        '</div>',
        unsafe_allow_html=True
    )

    answer = ask_ai(
        question,
        sources,
        deep
    )

    chat["messages"].append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })

    status.empty()

    st

import os
import requests
import streamlit as st

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered"
)

# =========================
# KEYS
# =========================

def get_key(name):
    try:
        return st.secrets.get(name) or os.getenv(name, "")
    except Exception:
        return os.getenv(name, "")

GROQ = get_key("GROQ_API_KEY")
TAVILY = get_key("TAVILY_API_KEY")

# =========================
# STATE
# =========================

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

# =========================
# CSS
# =========================

st.markdown("""
<style>

.stApp {
    background: #0b0b0d;
    color: #eeeeee;
}

.block-container {
    max-width: 760px;
    padding-top: 35px;
    padding-bottom: 170px;
}

.nexus {
    text-align: center;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: 8px;
    margin-bottom: 8px;
}

.tagline {
    text-align: center;
    color: #707078;
    font-size: 13px;
    margin-bottom: 45px;
}

.user {
    display: flex;
    justify-content: flex-end;
    margin: 18px 0;
}

.userbox {
    background: #19191d;
    border: 1px solid #29292e;
    border-radius: 18px 18px 5px 18px;
    padding: 12px 16px;
    max-width: 80%;
}

.ai {
    margin: 25px 0 35px;
}

.ailabel {
    color: #77777f;
    font-size: 10px;
    letter-spacing: 2px;
    margin-bottom: 8px;
}

.answer {
    line-height: 1.7;
}

.source {
    border-top: 1px solid #252529;
    padding: 9px 0;
    font-size: 12px;
}

.source a {
    color: #dddddf;
    text-decoration: none;
}

.sourceurl {
    color: #55555d;
    font-size: 10px;
}

[data-testid="stSidebar"] {
    background: #0e0e10;
}

.composer {
    background: #151518;
    border: 1px solid #303035;
    border-radius: 18px;
    padding: 10px;
    margin-top: 40px;
}

div[data-testid="stForm"] {
    border: 0;
    padding: 0;
}

div[data-testid="stTextInput"] input {
    background: #151518 !important;
    color: #eeeeee !important;
    border: 1px solid #303035 !important;
    border-radius: 13px !important;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background: #19191d !important;
    border: 1px solid #303035 !important;
    border-radius: 10px !important;
}

</style>
""", unsafe_allow_html=True)

# =========================
# SIDEBAR
# =========================

with st.sidebar:

    st.markdown("## NEXUS")

    if st.button("＋ New chat", use_container_width=True):

        n = len(st.session_state.chats) + 1
        new_id = "chat_" + str(n)

        st.session_state.chats[new_id] = {
            "title": "New conversation",
            "messages": []
        }

        st.session_state.chat_id = new_id
        st.rerun()

    st.divider()
    st.caption("HISTORY")

    for cid, data in reversed(list(st.session_state.chats.items())):

        title = data["title"][:35]

        if st.button(
            title,
            key="history_" + cid,
            use_container_width=True
        ):
            st.session_state.chat_id = cid
            st.rerun()

# =========================
# HEADER
# =========================

st.markdown(
    '<div class="nexus">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="tagline">Research first. Answer second.</div>',
    unsafe_allow_html=True
)

# =========================
# WEB SEARCH
# =========================

def search_web(query, deep):

    if not TAVILY:
        return []

    try:

        r = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": TAVILY,
                "query": query,
                "search_depth": "advanced" if deep else "basic",
                "max_results": 8 if deep else 4
            },
            timeout=35
        )

        if r.status_code != 200:
            return []

        data = r.json()

        results = []

        for item in data.get("results", []):

            results.append({
                "title": item.get("title", "Source"),
                "url": item.get("url", ""),
                "content": item.get("content", "")[:700]
            })

        return results

    except Exception:
        return []

# =========================
# AI
# =========================

def ask_ai(question, sources, deep):

    if not GROQ:
        return "GROQ_API_KEY is missing."

    evidence = ""

    for i, source in enumerate(sources, 1):

       

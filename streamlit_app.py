import os
import html
import requests
import streamlit as st

st.set_page_config(page_title="NEXUS", page_icon="N", layout="centered")

# ---------- KEYS ----------

def key(name):
    try:
        return st.secrets.get(name) or os.getenv(name, "")
    except Exception:
        return os.getenv(name, "")

GROQ = key("GROQ_API_KEY")
TAVILY = key("TAVILY_API_KEY")

# ---------- STATE ----------

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "chat_id" not in st.session_state:
    st.session_state.chat_id = "chat_1"
    st.session_state.chats["chat_1"] = {
        "title": "New conversation",
        "messages": []
    }

# ---------- STYLE ----------

st.markdown("""
<style>
.stApp{background:#0b0b0d;color:#eee}
.block-container{max-width:760px;padding-top:45px;padding-bottom:150px}

.nexus{text-align:center;font-size:34px;font-weight:700;
letter-spacing:8px;color:#f5f5f5}
.sub{text-align:center;color:#68686f;font-size:13px;
margin:12px 0 45px}

.user{display:flex;justify-content:flex-end;margin:20px 0}
.bubble{background:#19191d;border:1px solid #29292e;
padding:12px 16px;border-radius:18px 18px 5px 18px;
max-width:78%;line-height:1.55}

.ai{margin:25px 0 35px}
.label{font-size:11px;letter-spacing:2px;color:#777;margin-bottom:8px}
.answer{line-height:1.7}

.status{color:#777;font-size:13px;margin:12px 0}

.source{border-top:1px solid #222;padding:10px 0}
.source small{color:#666}

[data-testid="stSidebar"]{background:#0e0e10}

div[data-testid="stForm"]{
background:#151518;
border:1px solid #303035;
border-radius:18px;
padding:10px;
}

div[data-testid="stTextInput"] input{
background:#151518!important;
color:#eee!important;
border:0!important;
box-shadow:none!important;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"]>div{
background:#19191d!important;
border:1px solid #303035!important;
border-radius:10px!important;
}

div.stButton>button{
border-radius:12px!important;
}

</style>
""", unsafe_allow_html=True)

# ---------- SIDEBAR ----------

with st.sidebar:
    st.markdown("## NEXUS")

    if st.button("＋ New chat", use_container_width=True):
        n = len(st.session_state.chats) + 1
        cid = f"chat_{n}"
        st.session_state.chats[cid] = {
            "title": "New conversation",
            "messages": []
        }
        st.session_state.chat_id = cid
        st.rerun()

    st.divider()
    st.caption("HISTORY")

    for cid, chat in reversed(list(st.session_state.chats.items())):
        title = chat["title"][:35]

        if st.button(title, key=cid, use_container_width=True):
            st.session_state.chat_id = cid
            st.rerun()

# ---------- HEADER ----------

st.markdown('<div class="nexus">NEXUS</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Research first. Answer second.</div>',
            unsafe_allow_html=True)

chat = st.session_state.chats[st.session_state.chat_id]

# ---------- SEARCH ----------

def search(query, deep):

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
            timeout=30
        )

        if r.status_code != 200:
            return []

        return [
            {
                "title": x.get("title", "Source"),
                "url": x.get("url", ""),
                "content": x.get("content", "")[:800]
            }
            for x in r.json().get("results", [])
        ]

    except Exception:
        return []

# ---------- AI ----------

def ask_ai(question, sources, deep):

    if not GROQ:
        return "GROQ_API_KEY is missing."

    evidence = ""

    for i, s in enumerate(sources[:8], 1):
        evidence += f"""
SOURCE {i}
{s["title"]}
{s["url"]}
{s["content"]}
"""

    history = ""

    for m in chat["messages"][-4:]:
        history += f'\n{m["role"]}: {m["content"][:400]}'

    prompt = f"""
You are NEXUS.

Question:
{question}

Research mode:
{"DEEP RESEARCH" if deep else "QUICK"}

Evidence:
{evidence}

Recent conversation:
{history}

Answer accurately.

Rules:
- Never invent information.
- Use [1], [2], etc. for source references.
- Compare sources when appropriate.
- Mention uncertainty.
- If evidence is insufficient, say so.
- Be concise but useful.
- Smart, calm, direct personality.
- Occasional natural humor is okay.
- Never be cringe.
"""

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "You are NEXUS."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4,
                "max_completion_tokens": 1800
            },
            timeout=90
        )

        if r.status_code == 413:
            return "NEXUS received too much research data. Try a shorter question."

        if r.status_code != 200:
            return "NEXUS AI error: " + r.text

        return r.json()["choices"][0]["message"]["content"]

    except Exception as e:
        return "NEXUS error: " + str(e)

# ---------- HISTORY DISPLAY ----------

for m in chat["messages"]:

    if m["role"] == "user":
        text = html.escape(m["content"])

        st.markdown(
            f'<div class="user"><div class="bubble">{text}</div></div>',
            unsafe_allow_html=True
        )

    else:
        st.markdown(
            '<div class="ai"><div class="label">NEXUS</div>'
            '<div class="answer">',
            unsafe_allow_html=True
        )

        st.markdown(m["content"])
        st.markdown("</div></div>", unsafe_allow_html=True)

        if m.get("sources"):
            st.caption("SOURCES")

            for i, s in enumerate(m["sources"], 1):
                st.markdown(
                    f'<div class="source">'
                    f'<b>[{i}]</b> '
                    f'<a href="{s["url"]}" target="_blank">'
                    f'{html.escape(s["title"])}</a><br>'
                    f'<small>{html.escape(s["url"])}</small>'
                    f'</div>',
                    unsafe_allow_html=True
                )

# ---------- COMPOSER ----------

with st.form("nexus_composer", clear_on_submit=True):

    question = st.text_input(
        "Question",
        placeholder="Ask NEXUS anything...",
        label_visibility="collapsed"
    )

    col1, col2 = st.columns([3, 1])

    with col1:
        mode = st.selectbox(
            "Research",
            ["Quick", "Deep Research"],
            label_visibility="collapsed"
        )

    with col2:
        send = st.form_submit_button(
            "↑ Send",
            use_container_width=True
        )

# ---------- PROCESS ----------

if send and question.strip():

    question = question.strip()
    deep = mode == "Deep Research"

    if chat["title"] == "New conversation":
        chat["title"] = question[:35]

    chat["messages"].append({
        "role": "user",
        "content": question
    })

    status = st.empty()

    if deep:
        status.markdown(
            '<div class="status">Researching multiple sources…</div>',
            unsafe_allow_html=True
        )
        sources = search(question, True)

    else:
        status.markdown(
            '<div class="status">Searching…</div>',
            unsafe_allow_html=True
        )
        sources = search(question, False)

    status.markdown(
        '<div class="status">Analyzing evidence…</div>',
        unsafe_allow_html=True
    )

    answer = ask_ai(question, sources, deep)

    chat["messages"].append({
        "role": "assistant",
        "content": answer,
        "sources": sources
    })

    st.rerun()

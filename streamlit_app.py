import os
import html
import requests
import streamlit as st

# ============================================================
# NEXUS
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered"
)

# ============================================================
# API KEYS
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
    st.session_state.chats = {}

if "chat_id" not in st.session_state:

    st.session_state.chat_id = "chat_1"

    st.session_state.chats["chat_1"] = {
        "title": "New conversation",
        "messages": []
    }


# ============================================================
# STYLE
# ============================================================

st.markdown("""
<style>

/* ============================================================
   APP
   ============================================================ */

.stApp {
    background: #0b0b0d;
    color: #eeeeee;
}

.block-container {
    max-width: 760px;
    padding-top: 45px;
    padding-bottom: 190px;
}


/* ============================================================
   LOGO
   ============================================================ */

.nexus {
    text-align: center;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: 8px;
    color: #f5f5f5;
}

.sub {
    text-align: center;
    color: #68686f;
    font-size: 13px;
    margin: 12px 0 45px;
}


/* ============================================================
   USER MESSAGE
   ============================================================ */

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


/* ============================================================
   AI MESSAGE
   ============================================================ */

.ai {
    margin: 25px 0 35px;
}

.label {
    font-size: 11px;
    letter-spacing: 2px;
    color: #777;
    margin-bottom: 8px;
}

.answer {
    line-height: 1.7;
    font-size: 15px;
}


/* ============================================================
   STATUS
   ============================================================ */

.status {
    color: #777;
    font-size: 13px;
    margin: 12px 0;
}


/* ============================================================
   SOURCES
   ============================================================ */

.source {
    border-top: 1px solid #222;
    padding: 10px 0;
}

.source small {
    color: #666;
}


/* ============================================================
   SIDEBAR
   ============================================================ */

[data-testid="stSidebar"] {
    background: #0e0e10;
}


/* ============================================================
   BOTTOM COMPOSER
   ============================================================ */

div[data-testid="stForm"] {

    position: fixed !important;

    bottom: 18px !important;

    left: 50% !important;

    transform: translateX(-50%) !important;

    width: min(720px, calc(100vw - 32px)) !important;

    z-index: 999999 !important;

    background: #151518 !important;

    border: 1px solid #303035 !important;

    border-radius: 18px !important;

    padding: 10px !important;

    box-shadow:
        0 12px 45px rgba(0,0,0,.55) !important;
}


/* ============================================================
   INPUT
   ============================================================ */

div[data-testid="stForm"]
div[data-testid="stTextInput"] {

    margin-bottom: 5px !important;
}

div[data-testid="stForm"]
div[data-testid="stTextInput"] input {

    background: #151518 !important;

    color: #eeeeee !important;

    border: 0 !important;

    box-shadow: none !important;

    height: 42px !important;

    font-size: 14px !important;
}


/* ============================================================
   MODE SELECTOR
   ============================================================ */

div[data-testid="stForm"]
div[data-baseweb="select"] > div {

    background: #19191d !important;

    color: #eeeeee !important;

    border: 1px solid #303035 !important;

    border-radius: 10px !important;
}


/* ============================================================
   SEND BUTTON
   ============================================================ */

div[data-testid="stForm"] button {

    border-radius: 10px !important;

    min-height: 38px !important;
}


/* ============================================================
   MOBILE
   ============================================================ */

@media (max-width: 600px) {

    .block-container {

        padding-top: 30px;

        padding-bottom: 200px;
    }

    .nexus {

        font-size: 29px;
    }

    div[data-testid="stForm"] {

        bottom: 10px !important;

        width: calc(100vw - 20px) !important;

    }

}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR / HISTORY
# ============================================================

with st.sidebar:

    st.markdown("## NEXUS")

    if st.button(
        "＋ New chat",
        use_container_width=True
    ):

        number = len(
            st.session_state.chats
        ) + 1

        chat_id = "chat_" + str(number)

        st.session_state.chats[chat_id] = {
            "title": "New conversation",
            "messages": []
        }

        st.session_state.chat_id = chat_id

        st.rerun()


    st.divider()

    st.caption("HISTORY")


    chats = list(
        st.session_state.chats.items()
    )

    chats.reverse()


    for chat_id, chat in chats:

        title = chat["title"]

        if not title:
            title = "New conversation"

        title = title[:38]


        if st.button(
            title,
            key="history_" + chat_id,
            use_container_width=True
        ):

            st.session_state.chat_id = chat_id

            st.rerun()


# ============================================================
# CURRENT CHAT
# ============================================================

chat = st.session_state.chats[
    st.session_state.chat_id
]


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="nexus">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub">'
    'Research first. Answer second.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# WEB SEARCH
# ============================================================

def search_web(query, deep=False):

    if not TAVILY:

        return []


    try:

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY,

                "query": query,

                "search_depth":
                    "advanced"
                    if deep
                    else "basic",

                "topic":
                    "general",

                "max_results":
                    8
                    if deep
                    else 4,

                "include_answer":
                    False,

                "include_raw_content":
                    False
            },

            timeout=35
        )


        if response.status_code != 200:

            return []


        data = response.json()


        results = []


        for item in data.get(
            "results",
            []
        ):

            results.append({

                "title":
                    item.get(
                        "title",
                        "Source"
                    ),

                "url":
                    item.get(
                        "url",
                        ""
                    ),

                "content":
                    item.get(
                        "content",
                        ""
                    )[:850]
            })


        return results


    except Exception:

        return []


# ============================================================
# AI
# ============================================================

def ask_ai(
    question,
    sources,
    deep
):

    if not GROQ:

        return (
            "GROQ_API_KEY is missing."
        )


    evidence = ""


    for index, source in enumerate(
        sources[:8],
        1
    ):

        evidence += f"""

SOURCE {index}

Title:
{source["title"]}

URL:
{source["url"]}

Evidence:
{source["content"]}

"""


    history = ""


    for message in chat["messages"][-4:]:

        history += (
            "\n"
            + message["role"]
            + ": "
            + message["content"][:400]
        )


    mode = (
        "DEEP RESEARCH"
        if deep
        else "QUICK"
    )


    prompt = f"""
You are NEXUS.

Research mode:
{mode}

Question:
{question}

Web evidence:
{evidence}

Recent conversation:
{history}

Answer accurately using the evidence.

Rules:

- Never invent facts.
- Cite important claims with [1], [2], etc.
- Compare sources when useful.
- Mention uncertainty.
- If evidence is insufficient, say so.
- Be useful and reasonably concise.

Personality:

Intelligent.
Calm.
Direct.
Slightly humorous.

Use humor naturally.
Do not force jokes.
Do not sound cringe.
Accuracy comes first.
"""


    try:

        response = requests.post(

            "https://api.groq.com/openai/v1/chat/completions",

            headers={

                "Authorization":
                    "Bearer " + GROQ,

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
                    0.4,

                "max_completion_tokens":
                    1800
            },

            timeout=90
        )


        if response.status_code == 413:

            return (
                "NEXUS received too much "
                "research data. Try a shorter "
                "question."
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

        return (
            "NEXUS error: "
            + str(e)
        )


# ============================================================
# DISPLAY CHAT
# ============================================================

for message in chat["messages"]:

    if message["role"] == "user":

        text = html.escape(
            message["content"]
        )


        st.markdown(
            '<div class="user">'
            '<div class="bubble">'
            + text +
            '</div></div>',
            unsafe_allow_html=True
        )


    else:

        st.markdown(
            '<div class="ai">'
            '<div class="label">'
            'NEXUS'
            '</div>'
            '<div class="answer">',
            unsafe_allow_html=True
        )


        st.markdown(
            message["content"]
        )


        st.markdown(
            '</div></div>',
            unsafe_allow_html=True
        )


        sources = message.get(
            "sources",
            []
        )


        if sources:

            st.caption(
                "SOURCES"
            )


            for index, source in enumerate(
                sources,
                1
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

<b>[{index}]</b>

<a href="{url}"
target="_blank">

{title}

</a>

<br>

<small>{url}</small>

</div>
""",
                    unsafe_allow_html=True
                )


# ============================================================
# BOTTOM COMPOSER
# ============================================================

with st.form(
    "nexus_composer",
    clear_on_submit=True
):

    question = st.text_input(

        "Question",

        placeholder:
            "Ask NEXUS anything...",

        label_visibility:
            "collapsed"
    )


    col1, col2 = st.columns(
        [3, 1]
    )


    with col1:

        mode = st.selectbox(

            "Research mode",

            [
                "Quick",
                "Deep Research"
            ],

            label_visibility:
                "collapsed"
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


    deep = (
        mode == "Deep Research"
    )


    # --------------------------------------------------------
    # CHAT TITLE
    # --------------------------------------------------------

    if (
        chat["title"]
        == "New conversation"
    ):

        chat["title"] = (
            question[:38]
        )


    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    chat["messages"].append({

        "role":
            "user",

        "content":
            question
    })


    status = st.empty()


    # --------------------------------------------------------
    # RESEARCH
    # --------------------------------------------------------

    if deep:

        status.markdown(
            '<div class="status">'
            'Researching multiple sources…'
            '</div>',
            unsafe_allow_html=True
        )

        sources = search_web(
            question,
            True
        )

    else:

        status.markdown(
            '<div class="status">'
            'Searching…'
            '</div>',
            unsafe_allow_html=True
        )

        sources = search_web(
            question,
            False
        )


    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    status.markdown(
        '<div class="status">'
        'Analyzing evidence…'
        '</div>',
        unsafe_allow_html=True
    )


    answer = ask_ai(

        question,

        sources,

        deep
    )


    # --------------------------------------------------------
    # SAVE ANSWER
    # --------------------------------------------------------

    chat["messages"].append({

        "role":
            "assistant",

        "content":
            answer,

        "sources":
            sources
    })


    status.empty()


    # --------------------------------------------------------
    # REFRESH
    # --------------------------------------------------------

    st.rerun()

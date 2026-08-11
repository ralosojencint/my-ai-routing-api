import os
import html
import requests
import streamlit as st

# ============================================================
# NEXUS CONFIG
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered",
    initial_sidebar_state="expanded"
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


GROQ_API_KEY = get_key("GROQ_API_KEY")
TAVILY_API_KEY = get_key("TAVILY_API_KEY")


# ============================================================
# SESSION STATE
# ============================================================

if "chats" not in st.session_state:
    st.session_state.chats = {
        "chat_1": {
            "title": "New conversation",
            "messages": []
        }
    }

if "current_chat" not in st.session_state:
    st.session_state.current_chat = "chat_1"


chat = st.session_state.chats[
    st.session_state.current_chat
]


# ============================================================
# NEXUS UI
# ============================================================

st.markdown("""
<style>

/* ================= APP ================= */

.stApp {
    background: #0b0b0d;
    color: #eeeeee;
}

.block-container {
    max-width: 780px;
    padding-top: 40px;
    padding-bottom: 130px;
}


/* ================= NEXUS ================= */

.nexus-logo {
    text-align: center;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 8px;
    color: #f5f5f5;
    margin-top: 10px;
}

.nexus-subtitle {
    text-align: center;
    color: #66666d;
    font-size: 12px;
    margin-top: 8px;
    margin-bottom: 45px;
}


/* ================= USER MESSAGE ================= */

.user-row {
    display: flex;
    justify-content: flex-end;
    margin: 18px 0;
}

.user-bubble {
    max-width: 78%;
    background: #19191d;
    border: 1px solid #29292e;
    padding: 12px 16px;
    border-radius: 18px 18px 5px 18px;
    line-height: 1.55;
}


/* ================= AI MESSAGE ================= */

.ai-message {
    margin: 25px 0 35px;
}

.ai-label {
    color: #77777f;
    font-size: 10px;
    letter-spacing: 2px;
    margin-bottom: 8px;
}

.ai-answer {
    color: #eeeeee;
    font-size: 15px;
    line-height: 1.7;
}


/* ================= SOURCES ================= */

.sources-label {
    color: #66666d;
    font-size: 10px;
    letter-spacing: 1.5px;
    margin-top: 22px;
    margin-bottom: 6px;
}

.source-item {
    border-top: 1px solid #222226;
    padding: 9px 0;
}

.source-item a {
    color: #dddddf;
    text-decoration: none;
    font-size: 13px;
}

.source-url {
    color: #55555d;
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}


/* ================= SIDEBAR ================= */

[data-testid="stSidebar"] {
    background: #0e0e10;
}

[data-testid="stSidebar"] hr {
    border-color: #222226;
}


/* ================= BOTTOM COMPOSER ================= */

/*
   The composer is kept in the normal Streamlit flow.
   This prevents Streamlit from accidentally making
   the whole page a search field.
*/

.composer-box {
    background: #151518;
    border: 1px solid #303035;
    border-radius: 18px;
    padding: 8px;
    margin-top: 35px;
}


/* ================= INPUT ================= */

div[data-testid="stTextInput"] input {
    background: #151518 !important;
    color: #eeeeee !important;
    border: 1px solid #303035 !important;
    border-radius: 13px !important;
    height: 44px !important;
}

div[data-testid="stTextInput"] label {
    display: none !important;
}


/* ================= SELECT ================= */

div[data-testid="stSelectbox"] label {
    display: none !important;
}

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background: #19191d !important;
    color: #eeeeee !important;
    border: 1px solid #303035 !important;
    border-radius: 10px !important;
}


/* ================= BUTTON ================= */

div[data-testid="stFormSubmitButton"] button {
    border-radius: 10px !important;
    min-height: 40px !important;
}


/* ================= MOBILE ================= */

@media (max-width: 600px) {

    .block-container {
        padding-top: 25px;
        padding-bottom: 110px;
    }

    .nexus-logo {
        font-size: 27px;
        letter-spacing: 6px;
    }

    .user-bubble {
        max-width: 88%;
    }

}

</style>
""", unsafe_allow_html=True)


# ============================================================
# SIDEBAR
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

        new_chat_id = "chat_" + str(number)

        st.session_state.chats[
            new_chat_id
        ] = {
            "title": "New conversation",
            "messages": []
        }

        st.session_state.current_chat = new_chat_id

        st.rerun()


    st.divider()

    st.caption("HISTORY")


    history = list(
        st.session_state.chats.items()
    )

    history.reverse()


    for chat_id, chat_data in history:

        title = chat_data["title"]

        if not title:
            title = "New conversation"

        title = title[:38]


        if st.button(
            title,
            key="history_" + chat_id,
            use_container_width=True
        ):

            st.session_state.current_chat = chat_id

            st.rerun()


# ============================================================
# NEXUS HEADER
# ============================================================

st.markdown(
    '<div class="nexus-logo">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-subtitle">'
    'Research first. Answer second.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# WEB SEARCH
# ============================================================

def web_search(query, deep=False):

    if not TAVILY_API_KEY:
        return []


    try:

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": (
                    "advanced"
                    if deep
                    else "basic"
                ),
                "topic": "general",
                "max_results": (
                    8
                    if deep
                    else 4
                )
            },

            timeout=35
        )


        if response.status_code != 200:
            return []


        data = response.json()


        sources = []


        for item in data.get(
            "results",
            []
        ):

            sources.append({

                "title": item.get(
                    "title",
                    "Source"
                ),

                "url": item.get(
                    "url",
                    ""
                ),

                "content": item.get(
                    "content",
                    ""
                )[:900]

            })


        return sources


    except Exception:

        return []


# ============================================================
# AI ANSWER
# ============================================================

def generate_answer(
    question,
    sources,
    deep
):

    if not GROQ_API_KEY:

        return (
            "GROQ_API_KEY is missing."
        )


    evidence = ""


    for i, source in enumerate(
        sources[:8],
        1
    ):

        evidence += (
            "\nSOURCE "
            + str(i)
            + "\nTitle: "
            + source["title"]
            + "\nURL: "
            + source["url"]
            + "\nEvidence: "
            + source["content"]
            + "\n"
        )


    conversation = ""


    for message in chat["messages"][-4:]:

        conversation += (
            "\n"
            + message["role"]
            + ": "
            + message["content"][:400]
        )


    mode = (
        "DEEP RESEARCH"
        if deep
        else "QUICK RESEARCH"
    )


    prompt = f"""
You are NEXUS.

Mode:
{mode}

USER QUESTION:
{question}

WEB RESEARCH:
{evidence}

RECENT CONVERSATION:
{conversation}

Give the best answer possible.

Rules:

1. Do not invent facts.
2. Use the web evidence.
3. Cite important claims using [1], [2], etc.
4. Compare sources when appropriate.
5. If evidence is weak or conflicting, say so.
6. If you do not know, say you do not know.
7. Be direct.
8. Be intelligent.
9. Have a little natural humor.
10. Never force jokes or sound cringe.

Accuracy is more important than confidence.
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
                    0.4,

                "max_completion_tokens":
                    1800
            },

            timeout=90
        )


        if response.status_code == 413:

            return (
                "The research package was "
                "too large. Try a shorter "
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


    except Exception as error:

        return (
            "NEXUS error: "
            + str(error)
        )


# ============================================================
# DISPLAY CONVERSATION
# ============================================================

for message in chat["messages"]:

    if message["role"] == "user":

        text = html.escape(
            message["content"]
        )

        st.markdown(
            '<div class="user-row">'
            '<div class="user-bubble">'
            + text +
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )


    else:

        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">'
            'NEXUS'
            '</div>'
            '<div class="ai-answer">',
            unsafe_allow_html=True
        )

        st.markdown(
            message["content"]
        )

        st.markdown(
            '</div>'
            '</div>',
            unsafe_allow_html=True
        )


        sources = message.get(
            "sources",
            []
        )


        if sources:

            st.markdown(
                '<div class="sources-label">'
                'SOURCES'
                '</div>',
                unsafe_allow_html=True
            )


            for i, source in enumerate(
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
                    '<div class="source-item">'
                    '<b>['
                    + str(i)
                    + ']</b> '
                    '<a href="'
                    + url
                    + '" target="_blank">'
                    + title
                    + '</a>'
                    '<div class="source-url">'
                    + url
                    + '</div>'
                    '</div>',
                    unsafe

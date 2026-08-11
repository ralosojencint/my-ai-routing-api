import os
import html
import requests
import streamlit as st

# ============================================================
# NEXUS AI
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="N",
    layout="centered"
)

# ============================================================
# API KEYS
# ============================================================

def get_secret(name):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass

    return os.getenv(name, "")


GROQ_API_KEY = get_secret("GROQ_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")


# ============================================================
# SESSION STATE
# ============================================================

if "chats" not in st.session_state:
    st.session_state.chats = {}

if "current_chat" not in st.session_state:
    st.session_state.current_chat = None

if "research_mode" not in st.session_state:
    st.session_state.research_mode = "Quick"


# ============================================================
# CREATE NEW CHAT
# ============================================================

def create_new_chat():

    chat_id = str(
        len(st.session_state.chats) + 1
    ) + "_" + str(
        abs(hash(str(st.session_state.chats)))
    )

    st.session_state.chats[chat_id] = {
        "title": "New conversation",
        "messages": []
    }

    st.session_state.current_chat = chat_id


# Create first conversation
if st.session_state.current_chat is None:

    create_new_chat()


# ============================================================
# CURRENT CHAT
# ============================================================

def current_messages():

    return st.session_state.chats[
        st.session_state.current_chat
    ]["messages"]


# ============================================================
# UI
# ============================================================

st.markdown("""
<style>

.stApp {
    background: #0b0b0d;
    color: #eeeeef;
}

.block-container {
    max-width: 800px;
    padding-top: 45px;
    padding-bottom: 150px;
}

/* ============================================================
   LOGO
   ============================================================ */

.nexus-name {
    text-align: center;
    font-size: 34px;
    font-weight: 700;
    letter-spacing: 8px;
    color: #f4f4f5;
}

.nexus-line {
    width: 25px;
    height: 2px;
    background: #eeeeee;
    margin: 12px auto;
}

.nexus-sub {
    text-align: center;
    color: #707078;
    font-size: 13px;
    margin-bottom: 45px;
}

/* ============================================================
   USER
   ============================================================ */

.user-message {
    display: flex;
    justify-content: flex-end;
    margin: 22px 0;
}

.user-bubble {
    max-width: 78%;
    background: #19191d;
    border: 1px solid #29292e;
    border-radius: 18px 18px 5px 18px;
    padding: 12px 16px;
    line-height: 1.55;
}

/* ============================================================
   NEXUS
   ============================================================ */

.ai-message {
    margin: 25px 0 35px;
}

.ai-label {
    color: #77777e;
    font-size: 11px;
    letter-spacing: 1.5px;
    margin-bottom: 8px;
}

.ai-content {
    color: #eeeeef;
    line-height: 1.7;
    font-size: 15px;
}

/* ============================================================
   STATUS
   ============================================================ */

.research-status {
    color: #77777e;
    font-size: 13px;
    margin: 15px 0;
}

/* ============================================================
   SOURCES
   ============================================================ */

.sources-title {
    color: #77777e;
    font-size: 11px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-top: 25px;
}

.source {
    border-top: 1px solid #222226;
    padding: 12px 0;
}

.source-number {
    color: #505057;
    font-size: 11px;
}

.source-title {
    color: #dddddf;
    font-size: 13px;
    margin-top: 3px;
}

.source-url {
    color: #66666d;
    font-size: 11px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

/* ============================================================
   CHAT INPUT
   ============================================================ */

[data-testid="stChatInput"] {
    background: #151518 !important;
}

[data-testid="stChatInput"] textarea {
    background: #151518 !important;
    color: #eeeeef !important;
    border: 1px solid #303035 !important;
    border-radius: 18px !important;
}

/* ============================================================
   SIDEBAR
   ============================================================ */

[data-testid="stSidebar"] {
    background: #0e0e10;
    border-right: 1px solid #202024;
}

.history-label {
    color: #66666d;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 15px;
    margin-bottom: 8px;
}

/* ============================================================
   MOBILE
   ============================================================ */

@media (max-width: 600px) {

    .block-container {
        padding-top: 30px;
        padding-bottom: 130px;
    }

    .nexus-name {
        font-size: 29px;
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
        "＋  New chat",
        use_container_width=True
    ):

        create_new_chat()

        st.rerun()


    st.divider()

    st.markdown(
        '<div class="history-label">History</div>',
        unsafe_allow_html=True
    )


    # Show newest chats first
    chat_items = list(
        st.session_state.chats.items()
    )

    chat_items.reverse()


    for chat_id, chat in chat_items:

        title = chat["title"]

        if not title:
            title = "New conversation"

        # Keep title short in sidebar
        display_title = title[:38]

        if len(title) > 38:
            display_title += "..."


        if st.button(
            display_title,
            key="history_" + chat_id,
            use_container_width=True
        ):

            st.session_state.current_chat = chat_id

            st.rerun()


    st.divider()

    st.caption(
        "Your conversations are kept in this session."
    )


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="nexus-name">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-line"></div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-sub">'
    'Research first. Answer second.'
    '</div>',
    unsafe_allow_html=True
)


# ============================================================
# WEB SEARCH
# ============================================================

def search_web(query, deep=False):

    if not TAVILY_API_KEY:

        return [], "TAVILY_API_KEY is missing."


    try:

        results_count = 8 if deep else 5

        depth = (
            "advanced"
            if deep
            else "basic"
        )


        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": depth,
                "topic": "general",
                "max_results": results_count,
                "include_answer": False,
                "include_raw_content": False
            },

            timeout=35
        )


        if response.status_code != 200:

            return [], response.text


        data = response.json()

        results = []


        for item in data.get(
            "results",
            []
        ):

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
                )[:1000]
            })


        return results, None


    except Exception as e:

        return [], str(e)


# ============================================================
# SEARCH PLANNER
# ============================================================

def create_search_queries(question):

    if not GROQ_API_KEY:

        return [question]


    prompt = f"""
Create 3 different search queries
to research this question:

{question}

Return ONLY the queries.
One query per line.
No numbering.
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
                            "user",

                        "content":
                            prompt
                    }
                ],

                "temperature":
                    0.2,

                "max_completion_tokens":
                    180
            },

            timeout=30
        )


        if response.status_code != 200:

            return [question]


        data = response.json()


        text = data[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]


        queries = []


        for line in text.splitlines():

            line = line.strip()

            if line:

                line = line.lstrip(
                    "0123456789.-) "
                )

                if line:

                    queries.append(line)


        return queries[:3] or [question]


    except Exception:

        return [question]


# ============================================================
# AI ANSWER
# ============================================================

def generate_answer(
    question,
    sources,
    history,
    deep
):

    if not GROQ_API_KEY:

        return (
            "GROQ_API_KEY is missing."
        )


    # Keep request small
    source_limit = 8 if deep else 5


    evidence = ""


    for index, source in enumerate(
        sources[:source_limit],
        start=1
    ):

        evidence += f"""

SOURCE {index}

Title:
{source["title"]}

URL:
{source["url"]}

Evidence:
{source["content"][:800]}

"""


    # Only send a small amount of chat history
    recent = ""


    for message in history[-4:]:

        recent += (
            "\n"
            + message["role"]
            + ": "
            + message["content"][:450]
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

WEB EVIDENCE:
{evidence}

RECENT CONVERSATION:
{recent}

Answer accurately using the evidence.

RULES:

- Never invent facts.
- Cite important claims using [1], [2], etc.
- Prefer multiple sources.
- Identify meaningful disagreements.
- Consider source quality.
- Consider recency.
- If evidence is insufficient, say so.
- Do not claim to have searched something
  that was not searched.

PERSONALITY:

Smart.
Calm.
Direct.
Slightly funny.

Use humor naturally.

Never force jokes.

Never use cringe AI language.

Accuracy comes first.
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
                    2200
            },

            timeout=90
        )


        if response.status_code == 413:

            return (
                "The research package was too large. "
                "Try the question again."
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
            "NEXUS AI error: "
            + str(e)
        )


# ============================================================
# DISPLAY SOURCES
# ============================================================

def display_sources(sources):

    if not sources:
        return


    st.markdown(
        '<div class="sources-title">'
        'Sources'
        '</div>',
        unsafe_allow_html=True
    )


    for index, source in enumerate(
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
{index:02d}
</div>

<div class="source-title">

<a href="{url}"
target="_blank"
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
# DISPLAY CURRENT CHAT
# ============================================================

for message in current_messages():

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


    elif message["role"] == "assistant":

        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">'
            'NEXUS'
            '</div>'
            '<div class="ai-content">',
            unsafe_allow_html=True
        )


        st.markdown(
            message["content"]
        )


        st.markdown(
            '</div></div>',
            unsafe_allow_html=True
        )


        display_sources(
            message.get(
                "sources",
                []
            )
        )


# ============================================================
# RESEARCH MODE INSIDE THE CHAT COMPOSER
# ============================================================

mode_col1, mode_col2 = st.columns(
    [1, 1]
)


with mode_col1:

    quick = st.button(
        "Quick",
        use_container_width=True
    )


with mode_col2:

    deep_button = st.button(
        "Deep Research",
        use_container_width=True
    )


if quick:

    st.session_state.research_mode = "Quick"

    st.rerun()


if deep_button:

    st.session_state.research_mode = "Deep Research"

    st.rerun()


# Show current mode immediately above chat box

mode_text = (
    "Deep Research"
    if st.session_state.research_mode
    == "Deep Research"
    else "Quick"
)


st.caption(
    "Mode: " + mode_text
)


# ============================================================
# CHAT INPUT
# ============================================================

question = st.chat_input(
    "Ask NEXUS anything..."
)


# ============================================================
# PROCESS QUESTION
# ============================================================

if question:

    question = question.strip()


    if not question:
        st.stop()


    deep = (
        st.session_state.research_mode
        == "Deep Research"
    )


    # --------------------------------------------------------
    # UPDATE TITLE
    # --------------------------------------------------------

    current_chat = st.session_state.chats[
        st.session_state.current_chat
    ]


    if (
        current_chat["title"]
        == "New conversation"
    ):

        current_chat["title"] = (
            question[:42]
        )


    # --------------------------------------------------------
    # SAVE USER MESSAGE
    # --------------------------------------------------------

    current_chat["messages"].append({

        "role":
            "user",

        "content":
            question
    })


    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status = st.empty()


    if deep:

        status.markdown(
            '<div class="research-status">'
            'Planning research…'
            '</div>',
            unsafe_allow_html=True
        )


        queries = create_search_queries(
            question
        )


    else:

        queries = [question]


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    status.markdown(
        '<div class="research-status">'
        'Searching the web…'
        '</div>',
        unsafe_allow_html=True
    )


    all_sources = []

    seen_urls = set()


    for query in queries:

        results, error = search_web(
            query,
            deep
        )


        if error:
            continue


        for result in results:

            url = result.get(
                "url",
                ""
            )


            if (
                url
                and url not in seen_urls
            ):

                seen_urls.add(url)

                all_sources.append(
                    result
                )


    # Limit sources
    all_sources = all_sources[
        :(8 if deep else 5)
    ]


    # --------------------------------------------------------
    # ANALYZE
    # --------------------------------------------------------

    status.markdown(
        '<div class="research-status">'
        'Checking and comparing sources…'
        '</div>',
        unsafe_allow_html=True
    )


    answer = generate_answer(

        question,

        all_sources,

        current_chat["messages"],

        deep
    )


    status.empty()


    # --------------------------------------------------------
    # SAVE ANSWER
    # --------------------------------------------------------

    current_chat["messages"].append({

        "role":
            "assistant",

        "content":
            answer,

        "sources":
            all_sources
    })


    # --------------------------------------------------------
    # RELOAD
    # --------------------------------------------------------

    st.rerun()

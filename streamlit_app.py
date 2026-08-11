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

if "messages" not in st.session_state:
    st.session_state.messages = []

if "research_mode" not in st.session_state:
    st.session_state.research_mode = "Quick"


# ============================================================
# CUSTOM UI
# ============================================================

st.markdown("""
<style>

.stApp {
    background: #0b0b0d;
    color: #eeeeef;
}

.block-container {
    max-width: 780px;
    padding-top: 50px;
    padding-bottom: 180px;
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
    width: 26px;
    height: 2px;
    background: #eeeeee;
    margin: 12px auto;
}

.nexus-sub {
    text-align: center;
    color: #707078;
    font-size: 13px;
    margin-bottom: 50px;
}

/* ============================================================
   USER MESSAGE
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
    color: #eeeeef;
    line-height: 1.55;
}

/* ============================================================
   AI MESSAGE
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
    font-size: 15px;
    line-height: 1.7;
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
    margin-bottom: 5px;
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
   INPUT AREA
   ============================================================ */

.composer-title {
    color: #66666d;
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 5px;
}

/* Text input */

div[data-testid="stTextInput"] input {
    background: #151518 !important;
    color: #eeeeef !important;
    border: 1px solid #303035 !important;
    border-radius: 16px !important;
    height: 48px !important;
    padding-left: 16px !important;
}

div[data-testid="stTextInput"] input:focus {
    border-color: #55555c !important;
    box-shadow: none !important;
}

/* Selectbox */

div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background: #151518 !important;
    color: #eeeeef !important;
    border: 1px solid #303035 !important;
    border-radius: 16px !important;
    min-height: 48px !important;
}

/* Send button */

div.stButton > button {
    background: #eeeeef !important;
    color: #0b0b0d !important;
    border: none !important;
    border-radius: 14px !important;
    font-weight: 600 !important;
    min-height: 42px !important;
}

div.stButton > button:hover {
    background: #ffffff !important;
}

/* ============================================================
   SIDEBAR
   ============================================================ */

[data-testid="stSidebar"] {
    background: #0e0e10;
    border-right: 1px solid #202024;
}

/* ============================================================
   MOBILE
   ============================================================ */

@media (max-width: 600px) {

    .block-container {
        padding-top: 35px;
        padding-bottom: 190px;
    }

    .nexus-name {
        font-size: 29px;
    }

}

</style>
""", unsafe_allow_html=True)


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
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("### NEXUS")

    st.caption(
        "Research-first intelligence"
    )

    st.divider()

    st.markdown("**Modes**")

    st.write(
        "Quick — fast answers"
    )

    st.write(
        "Deep — broader research"
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

def search_web(query, deep=False):

    if not TAVILY_API_KEY:

        return [], (
            "TAVILY_API_KEY is missing."
        )

    try:

        max_results = 8 if deep else 5

        search_depth = (
            "advanced"
            if deep
            else "basic"
        )

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth": search_depth,
                "topic": "general",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False
            },

            timeout=35
        )

        if response.status_code != 200:

            return [], (
                "Search error: "
                + response.text
            )

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
                )[:1100]
            })

        return results, None

    except Exception as e:

        return [], str(e)


# ============================================================
# CREATE SEARCH QUERIES
# ============================================================

def create_search_queries(question):

    if not GROQ_API_KEY:

        return [question]

    prompt = f"""
Create 3 different web search queries
for this question:

{question}

The queries should approach the question
from different angles.

Return ONLY the queries.

One query per line.
No numbering.
No explanation.
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
                    200
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
# GENERATE ANSWER
# ============================================================

def generate_answer(
    question,
    sources,
    history,
    deep
):

    if not GROQ_API_KEY:

        return (
            "GROQ_API_KEY is missing. "
            "Add it to Streamlit Secrets."
        )


    # Keep payload deliberately small.
    max_sources = 8 if deep else 5

    evidence_parts = []


    for index, source in enumerate(
        sources[:max_sources],
        start=1
    ):

        evidence_parts.append(
            f"""
SOURCE {index}
Title: {source["title"]}
URL: {source["url"]}
Evidence: {source["content"][:900]}
"""
        )


    evidence = "\n".join(
        evidence_parts
    )


    recent_history = []


    for message in history[-4:]:

        recent_history.append(
            message["role"]
            + ": "
            + message["content"][:500]
        )


    conversation = "\n".join(
        recent_history
    )


    mode = (
        "DEEP RESEARCH"
        if deep
        else "QUICK RESEARCH"
    )


    prompt = f"""
You are NEXUS.

Research mode:
{mode}

USER QUESTION:
{question}

WEB EVIDENCE:
{evidence}

RECENT CONVERSATION:
{conversation}

Your job is to answer accurately
using the evidence.

Rules:

1. Do not invent facts.
2. Cite important claims using [1], [2], etc.
3. Prefer claims supported by multiple sources.
4. Identify important disagreements.
5. Consider source quality and recency.
6. If evidence is insufficient, say so.
7. Do not claim you searched something
   that you did not search.

PERSONALITY:

NEXUS is intelligent, calm,
direct and slightly funny.

Use occasional dry humor
when it fits naturally.

Do not force jokes.

Do not use cringe AI language.

Accuracy comes before humor.
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
                "NEXUS hit a payload-size limit. "
                "The research evidence was too large."
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
style="color:#dddddf;
text-decoration:none;">

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
# DISPLAY CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    if message["role"] == "user":

        safe_text = html.escape(
            message["content"]
        )

        st.markdown(
            f"""
<div class="user-message">

<div class="user-bubble">
{safe_text}
</div>

</div>
""",
            unsafe_allow_html=True
        )

    else:

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
# COMPOSER
# ============================================================

st.markdown(
    '<div class="composer-title">'
    'Ask NEXUS'
    '</div>',
    unsafe_allow_html=True
)

input_col, mode_col = st.columns(
    [5, 2]
)


with input_col:

    question = st.text_input(
        "Question",
        placeholder="Ask NEXUS anything...",
        label_visibility="collapsed"
    )


with mode_col:

    selected_mode = st.selectbox(
        "Research mode",
        [
            "Quick",
            "Deep Research"
        ],
        index=(
            1
            if st.session_state.research_mode
            == "Deep Research"
            else 0
        ),
        label_visibility="collapsed"
    )


st.session_state.research_mode = selected_mode


send = st.button(
    "Send",
    use_container_width=True
)


# ============================================================
# HANDLE QUESTION
# ============================================================

if send and question.strip():

    question = question.strip()


    # Save user message

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


    deep = (
        selected_mode
        == "Deep Research"
    )


    status = st.empty()


    # ========================================================
    # DEEP RESEARCH PLANNING
    # ========================================================

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


    # ========================================================
    # SEARCH
    # ========================================================

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


    # Keep research controlled.

    max_sources = (
        8 if deep else 5
    )

    all_sources = all_sources[
        :max_sources
    ]


    # ========================================================
    # ANALYSIS
    # ========================================================

    status.markdown(
        '<div class="research-status">'
        'Comparing sources…'
        '</div>',
        unsafe_allow_html=True
    )


    answer = generate_answer(

        question,

        all_sources,

        st.session_state.messages,

        deep
    )


    status.empty()


    # ========================================================
    # DISPLAY ANSWER
    # ========================================================

    st.markdown(
        '<div class="ai-message">'
        '<div class="ai-label">'
        'NEXUS'
        '</div>'
        '<div class="ai-content">',
        unsafe_allow_html=True
    )


    st.markdown(
        answer
    )


    st.markdown(
        '</div></div>',
        unsafe_allow_html=True
    )


    display_sources(
        all_sources
    )


    # ========================================================
    # SAVE ANSWER
    # ========================================================

    st.session_state.messages.append({

        "role":
            "assistant",

        "content":
            answer,

        "sources":
            all_sources
    })

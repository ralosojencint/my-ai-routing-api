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
# SETTINGS
# ============================================================

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


# ============================================================
# MEMORY
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "mode" not in st.session_state:
    st.session_state.mode = "Quick"


# ============================================================
# PROFESSIONAL UI
# ============================================================

st.markdown("""
<style>

.stApp {
    background: #0b0b0d;
    color: #eeeeef;
}

.block-container {
    max-width: 780px;
    padding-top: 45px;
    padding-bottom: 120px;
}

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
    margin-bottom: 35px;
}

.mode-title {
    text-align: center;
    color: #77777e;
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 8px;
}

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
}

.research-status {
    color: #77777e;
    font-size: 13px;
    margin: 15px 0;
}

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

[data-testid="stChatInput"] textarea {
    background: #151518 !important;
    border: 1px solid #303035 !important;
    border-radius: 18px !important;
    color: #eeeeef !important;
}

[data-testid="stSidebar"] {
    background: #0e0e10;
    border-right: 1px solid #202024;
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
# MODE
# ============================================================

st.markdown(
    '<div class="mode-title">Research depth</div>',
    unsafe_allow_html=True
)

mode = st.radio(
    "",
    ["Quick", "Deep Research"],
    horizontal=True,
    label_visibility="collapsed"
)

st.session_state.mode = mode


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown("### NEXUS")

    st.caption(
        "Research-first intelligence"
    )

    st.divider()

    st.markdown("**Current mode**")

    st.write(
        st.session_state.mode
    )

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True
    ):

        st.session_state.messages = []

        st.rerun()


# ============================================================
# SEARCH
# ============================================================

def search_web(query, deep=False):

    if not TAVILY_API_KEY:
        return [], "TAVILY_API_KEY is missing."

    try:

        max_results = 5 if not deep else 8

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth":
                    "advanced" if deep else "basic",
                "topic": "general",
                "max_results": max_results,
                "include_answer": False,
                "include_raw_content": False
            },

            timeout=35
        )

        if response.status_code != 200:
            return [], response.text

        data = response.json()

        results = []

        for item in data.get("results", []):

            results.append({

                "title":
                    item.get(
                        "title",
                        "Untitled"
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
                    )[:1100]
            })

        return results, None

    except Exception as e:

        return [], str(e)


# ============================================================
# CREATE EXTRA SEARCHES
# ============================================================

def make_search_queries(question):

    if not GROQ_API_KEY:

        return [question]

    prompt = f"""
Create 3 short web-search queries for this question:

{question}

Return ONLY the 3 queries.
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
                    200
            },

            timeout=30
        )

        if response.status_code != 200:
            return [question]

        text = response.json()[
            "choices"
        ][0][
            "message"
        ][
            "content"
        ]

        queries = [
            q.strip()
            for q in text.splitlines()
            if q.strip()
        ]

        return queries[:3] or [question]

    except Exception:
        return [question]


# ============================================================
# ANSWER
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

    evidence = ""

    # Keep payload deliberately small.

    limit = 5 if not deep else 8

    for i, source in enumerate(
        sources[:limit],
        start=1
    ):

        evidence += f"""

SOURCE {i}
Title: {source["title"]}
URL: {source["url"]}
Evidence: {source["content"][:900]}

"""


    conversation = ""

    for item in history[-3:]:

        conversation += (
            f'\n{item["role"]}: '
            f'{item["content"][:500]}'
        )


    research_level = (
        "DEEP RESEARCH"
        if deep
        else "QUICK RESEARCH"
    )


    prompt = f"""
You are NEXUS.

Research level: {research_level}

User question:
{question}

Web evidence:
{evidence}

Recent conversation:
{conversation}

Answer using the evidence.

Rules:

- Do not invent facts.
- Cite important claims as [1], [2], etc.
- Prefer multiple supporting sources.
- Mention disagreements between sources.
- Consider source quality and recency.
- If evidence is insufficient, say so.
- Never pretend you searched something you did not search.

PERSONALITY:

Smart, calm, direct and slightly funny.

Humor should be natural and occasional.

Never use cringe AI language.

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
                "The research package was too large. "
                "NEXUS needs to trim the evidence "
                "before asking the AI."
            )

        if response.status_code != 200:

            return (
                "NEXUS AI error: "
                + response.text
            )

        return response.json()[
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
# SOURCES
# ============================================================

def show_sources(sources):

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
# OLD MESSAGES
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

        st.markdown(
            '<div class="ai-message">'
            '<div class="ai-label">NEXUS</div>'
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

        show_sources(
            message.get(
                "sources",
                []
            )
        )


# ============================================================
# CHAT INPUT
# ============================================================

question = st.chat_input(
    "Ask NEXUS anything..."
)


if question:

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
        st.session_state.mode
        == "Deep Research"
    )


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

        queries = make_search_queries(
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

            url = result["url"]

            if url and url not in seen_urls:

                seen_urls.add(url)

                all_sources.append(
                    result
                )


    # Deep mode keeps more sources.

    max_sources = (
        8 if deep else 5
    )

    all_sources = all_sources[
        :max_sources
    ]


    # --------------------------------------------------------
    # ANALYSIS
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # ANSWER
    # --------------------------------------------------------

    st.markdown(
        '<div class="ai-message">'
        '<div class="ai-label">NEXUS</div>'
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


    show_sources(
        all_sources
    )


    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    st.session_state.messages.append({

        "role":
            "assistant",

        "content":
            answer,

        "sources":
            all_sources
    })

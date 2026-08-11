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
# SECRETS
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
# SESSION
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "research_mode" not in st.session_state:
    st.session_state.research_mode = "Quick"


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
    max-width: 780px;
    padding-top: 55px;
    padding-bottom: 150px;
}

/* ---------------- LOGO ---------------- */

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
    margin-bottom: 55px;
}

/* ---------------- USER MESSAGE ---------------- */

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

/* ---------------- AI MESSAGE ---------------- */

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

/* ---------------- RESEARCH STATUS ---------------- */

.research-status {
    color: #77777e;
    font-size: 13px;
    margin: 15px 0;
}

/* ---------------- SOURCES ---------------- */

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
   CUSTOM COMPOSER
   ============================================================ */

.composer-wrap {
    position: fixed;
    left: 50%;
    bottom: 18px;
    transform: translateX(-50%);
    width: min(760px, calc(100% - 28px));
    z-index: 999;
}

.composer-box {
    background: #151518;
    border: 1px solid #303035;
    border-radius: 18px;
    padding: 10px 12px 8px;
    box-shadow: 0 12px 40px rgba(0,0,0,.45);
}

.composer-label {
    color: #66666d;
    font-size: 11px;
    padding-left: 4px;
    margin-bottom: 5px;
}

.mode-pill {
    display: inline-block;
    color: #cfcfd3;
    font-size: 12px;
    border: 1px solid #303035;
    border-radius: 10px;
    padding: 5px 9px;
    background: #1b1b1f;
}

/* Hide normal Streamlit chat input */
[data-testid="stChatInput"] {
    display: none;
}

/* Mobile */

@media (max-width: 600px) {

    .block-container {
        padding-top: 35px;
    }

    .nexus-name {
        font-size: 29px;
    }

    .composer-wrap {
        width: calc(100% - 20px);
        bottom: 10px;
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

    st.markdown(
        "**Research modes**"
    )

    st.write(
        "Quick — faster research"
    )

    st.write(
        "Deep — broader investigation"
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
        return [], "TAVILY_API_KEY is missing."

    try:

        response = requests.post(

            "https://api.tavily.com/search",

            json={
                "api_key": TAVILY_API_KEY,
                "query": query,
                "search_depth":
                    "advanced" if deep else "basic",
                "topic": "general",
                "max_results":
                    8 if deep else 5,
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
# GENERATE SEARCH QUERIES
# ============================================================

def make_search_queries(question):

    if not GROQ_API_KEY:

        return [question]

    prompt = f"""
Create three different web search queries
that will help research this question:

{question}

Return ONLY the three queries.
One query per line.
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

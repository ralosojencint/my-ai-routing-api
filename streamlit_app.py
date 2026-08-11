import os
import requests
import streamlit as st

# ============================================================
# NEXUS v2
# Research-first AI
# ============================================================

st.set_page_config(
    page_title="NEXUS",
    page_icon="✦",
    layout="centered"
)

# ============================================================
# PROFESSIONAL UI
# ============================================================

st.markdown("""
<style>

.stApp {
    background: #0b0c0f;
}

.block-container {
    max-width: 900px;
    padding-top: 45px;
    padding-bottom: 110px;
}

.nexus-logo {
    text-align: center;
    font-size: 38px;
    font-weight: 700;
    letter-spacing: 7px;
    color: #f4f4f5;
}

.nexus-tagline {
    text-align: center;
    color: #71717a;
    font-size: 14px;
    margin-top: 8px;
    margin-bottom: 45px;
}

.research-box {
    border: 1px solid #27272a;
    border-radius: 14px;
    padding: 14px 18px;
    background: #111214;
}

.source-card {
    border: 1px solid #27272a;
    border-radius: 12px;
    padding: 14px;
    margin-top: 10px;
    background: #111214;
}

.source-number {
    color: #71717a;
    font-size: 12px;
}

.source-title {
    font-weight: 600;
    margin-top: 3px;
}

.source-url {
    color: #71717a;
    font-size: 12px;
}

.small-text {
    color: #71717a;
    font-size: 13px;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    '<div class="nexus-logo">NEXUS</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="nexus-tagline">'
    'Research first. Answer second.'
    '</div>',
    unsafe_allow_html=True
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

    return os.getenv(name)


GROQ_API_KEY = get_secret("GROQ_API_KEY")
TAVILY_API_KEY = get_secret("TAVILY_API_KEY")


# ============================================================
# MEMORY
# ============================================================

if "messages" not in st.session_state:
    st.session_state.messages = []


# ============================================================
# TAVILY WEB SEARCH
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
                "search_depth": "advanced",
                "topic": "general",
                "max_results": 8,
                "include_answer": False,
                "include_raw_content": False
            },

            timeout=30
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        clean_results = []

        for item in results:

            clean_results.append({

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
                    ),

                "score":
                    item.get(
                        "score",
                        0
                    )
            })

        return clean_results, None

    except Exception as e:

        return [], str(e)


# ============================================================
# GROQ
# ============================================================

def ask_groq(messages):

    if not GROQ_API_KEY:

        return (
            "GROQ_API_KEY is missing.\n\n"
            "Add it in Streamlit → Manage app → "
            "Settings → Secrets."
        )

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

                "messages":
                    messages,

                "temperature":
                    0.35,

                "max_tokens":
                    3500
            },

            timeout=90
        )

        response.raise_for_status()

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
# BUILD RESEARCH CONTEXT
# ============================================================

def build_research_context(results):

    if not results:

        return "No web sources were found."

    context = ""

    for i, result in enumerate(
        results,
        start=1
    ):

        context += f"""

SOURCE {i}
Title: {result["title"]}
URL: {result["url"]}
Relevance score: {result["score"]}

Content:
{result["content"]}

--------------------------------
"""

    return context


# ============================================================
# RESEARCH ANSWER
# ============================================================

def research_answer(question):

    # --------------------------------------------------------
    # First search
    # --------------------------------------------------------

    results, error = search_web(question)

    if error:

        return (
            f"⚠️ I couldn't search the web.\n\n"
            f"{error}"
        ), []


    if not results:

        return (
            "I searched, but didn't find useful "
            "public sources for that question."
        ), []


    # --------------------------------------------------------
    # Research context
    # --------------------------------------------------------

    research = build_research_context(
        results
    )


    # --------------------------------------------------------
    # AI instructions
    # --------------------------------------------------------

    system = {

        "role":
            "system",

        "content":
"""
You are NEXUS.

You are a research-first AI assistant.

Your job is NOT to blindly answer from memory.

The user asked a question and web sources
were collected for you.

Use the sources as evidence.

Rules:

1. Prefer information supported by multiple
   credible sources.

2. Do not invent facts.

3. If sources disagree, say so.

4. Prefer official sources for official facts.

5. Prefer recent information when the question
   depends on current events.

6. Clearly separate facts from your interpretation.

7. If the evidence is weak, say that it is weak.

8. Do not pretend that a source says something
   it does not say.

9. Keep the answer readable.

10. Use numbered source references such as
    [1], [2], [3] in the answer.

PERSONALITY:

You are intelligent, calm, direct and slightly funny.

Humor is allowed when appropriate.

Do NOT force jokes into serious topics.

Do NOT use cringe "AI robot" language.

You can occasionally make a dry observation
like:

"Apparently the internet couldn't agree on this."

But accuracy comes first.

Answer the user's question using the research.
"""
    }


    user = {

        "role":
            "user",

        "content":
f"""
USER QUESTION:

{question}


WEB RESEARCH:

{research}


Now analyze the sources and answer the
user's question.

Cite claims using [1], [2], etc.
"""
    }


    answer = ask_groq([
        system,
        user
    ])


    return answer, results


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.markdown(
        "### NEXUS"
    )

    st.caption(
        "Research-first intelligence"
    )

    st.divider()

    st.markdown(
        "**Research engine**"
    )

    st.write(
        "Web search → source collection → "
        "cross-checking → answer"
    )

    st.divider()

    if st.button(
        "New conversation",
        use_container_width=True
    ):

        st.session_state.messages = []

        st.rerun()


# ============================================================
# CONVERSATION
# ============================================================

for message in st.session_state.messages:

    with st.chat_message(
        message["role"]
    ):

        st.markdown(
            message["content"]
        )

        if (
            message["role"] == "assistant"
            and "sources" in message
        ):

            sources = message["sources"]

            if sources:

                st.markdown(
                    "#### Sources"
                )

                for i, source in enumerate(
                    sources,
                    start=1
                ):

                    st.markdown(
                        f"""
<div class="source-card">

<div class="source-number">
SOURCE {i}
</div>

<div class="source-title">
{source["title"]}
</div>

<div class="source-url">
<a href="{source["url"]}" target="_blank">
{source["url"]}
</a>
</div>

</div>
""",
                        unsafe_allow_html=True
                    )


# ============================================================
# BOTTOM CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask NEXUS anything..."
)


if prompt:

    # --------------------------------------------------------
    # User message
    # --------------------------------------------------------

    st.session_state.messages.append({

        "role":
            "user",

        "content":
            prompt
    })


    with st.chat_message("user"):

        st.markdown(
            prompt
        )


    # --------------------------------------------------------
    # Research
    # --------------------------------------------------------

    with st.chat_message("assistant"):

        status = st.empty()

        status.markdown(
            "🔎 **Researching the web...**"
        )

        answer, sources = research_answer(
            prompt
        )

        status.empty()

        st.markdown(
            answer
        )


        # ----------------------------------------------------
        # Sources
        # ----------------------------------------------------

        if sources:

            st.markdown(
                "#### Sources"
            )

            for i, source in enumerate(
                sources,
                start=1
            ):

                st.markdown(

                    f"""
<div class="source-card">

<div class="source-number">
SOURCE {i}
</div>

<div class="source-title">
{source["title"]}
</div>

<div class="source-url">
<a href="{source["url"]}" target="_blank">
{source["url"]}
</a>
</div>

</div>
""",

                    unsafe_allow_html=True
                )


    # --------------------------------------------------------
    # Save response
    # --------------------------------------------------------

    st.session_state.messages.append({

        "role":
            "assistant",

        "content":
            answer,

        "sources":
            sources
    })

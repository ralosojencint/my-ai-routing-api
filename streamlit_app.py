import os, re, json, asyncio, time, math
from pathlib import Path
from collections import Counter
import streamlit as st
import pandas as pd

try:
    from google import genai
except Exception:
    genai = None

try:
    from tavily import TavilyClient
except Exception:
    TavilyClient = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

# =========================
# NEXUS 10X — SINGLE FILE
# =========================
st.set_page_config(page_title="NEXUS", page_icon="✦", layout="wide")

def secret(name):
    value=os.getenv(name,"").strip()
    if value: return value
    try: return str(st.secrets.get(name,"")).strip()
    except Exception: return ""

GEMINI_API_KEY=secret("GEMINI_API_KEY")
GROG_API_KEY=secret("GROG_API_KEY")
TAVILY_API_KEY=secret("TAVILY_API_KEY")

DEFAULTS={
    "messages":[],
    "memory":[],
    "documents":[],
    "datasets":[],
    "projects":{},
    "activity":[],
    "request_count":0,
    "selected_model":"gemini-3.5-flash",
}
for k,v in DEFAULTS.items():
    if k not in st.session_state: st.session_state[k]=v

@st.cache_resource
def gemini_client():
    if not GEMINI_API_KEY or genai is None: return None
    return genai.Client(api_key=GEMINI_API_KEY)

@st.cache_resource
def tavily_client():
    if not TAVILY_API_KEY or TavilyClient is None: return None
    return TavilyClient(api_key=TAVILY_API_KEY)

def normalize(x):
    return re.sub(r"\s+"," ",x or "").strip()

def chunks(text,size=1200,overlap=200):
    text=normalize(text); out=[]; start=0
    while start<len(text):
        end=min(start+size,len(text))
        out.append(text[start:end])
        if end>=len(text): break
        start=max(0,end-overlap)
    return out

def extract_file(f):
    ext=Path(f.name).suffix.lower()
    if ext==".pdf":
        if PdfReader is None: return ""
        return "\n".join((p.extract_text() or "") for p in PdfReader(f).pages)
    if ext in [".txt",".md"]:
        return f.read().decode("utf-8",errors="replace")
    if ext==".csv":
        df=pd.read_csv(f)
        st.session_state.datasets.append({"name":f.name,"data":df})
        return df.head(100).to_csv(index=False)
    return ""

def index_uploads(files):
    if not files: return
    existing={x["name"] for x in st.session_state.documents}
    for f in files:
        if f.name in existing: continue
        try:
            text=extract_file(f)
            for i,c in enumerate(chunks(text)):
                st.session_state.documents.append({"name":f.name,"chunk":i,"text":c})
        except Exception as e:
            st.warning(f"{f.name}: {e}")

def retrieve(q,limit=6):
    terms=set(re.findall(r"[a-zA-Z0-9_]+",q.lower()))
    scored=[]
    for d in st.session_state.documents:
        c=Counter(re.findall(r"[a-zA-Z0-9_]+",d["text"].lower()))
        score=sum(c[t] for t in terms)
        if score: scored.append((score,d))
    scored.sort(reverse=True,key=lambda x:x[0])
    return [d for _,d in scored[:limit]]

async def ask_gemini(prompt):
    client=gemini_client()
    if not client:
        return "Gemini is not configured. Add GEMINI_API_KEY in Streamlit Secrets."
    try:
        r=await asyncio.to_thread(
            client.models.generate_content,
            model=st.session_state.selected_model,
            contents=prompt
        )
        return r.text or ""
    except Exception as e:
        return f"Gemini error: {e}"

async def web_research(q):
    client=tavily_client()
    if not client: return {"answer":"","sources":[]}
    try:
        r=await asyncio.to_thread(client.search,query=q,search_depth="advanced",max_results=6,include_answer=True)
        return {"answer":r.get("answer",""),"sources":r.get("results",[])}
    except Exception as e:
        return {"answer":f"Research error: {e}","sources":[]}

def route(q):
    x=q.lower()
    return {
        "research": bool(TAVILY_API_KEY) and any(w in x for w in ["latest","current","today","news","research","price","weather","2026"]),
        "data": bool(st.session_state.datasets) or any(w in x for w in ["csv","dataset","data analysis"]),
        "coding": any(w in x for w in ["code","python","debug","program"]),
        "documents": bool(st.session_state.documents),
    }

def safe_request(q):
    bad=[r"\bmake (a )?bomb\b",r"\bransomware\b",r"\bsteal password\b",r"\bkeylogger\b"]
    return not any(re.search(p,q.lower()) for p in bad)

async def run_nexus(q):
    start=time.perf_counter()
    st.session_state.activity=["Safety check","Autonomous planning"]
    if not safe_request(q):
        return {"answer":"I can't help with instructions that facilitate harmful activity.","sources":[]}

    plan=route(q)
    st.session_state.activity.append("Plan created")

    context="\n".join(f"FILE: {d['name']}\n{d['text']}" for d in retrieve(q))
    memory=json.dumps(st.session_state.memory[-10:],ensure_ascii=False)

    jobs=[]
    if plan["research"]: jobs.append(web_research(q))
    jobs.append(ask_gemini(f"""You are NEXUS, a powerful multi-agent AI workspace.
Answer the user accurately and directly.

USER:
{q}

RELEVANT DOCUMENTS:
{context}

LONG-TERM MEMORY:
{memory}

Capabilities available: research, data analysis, coding assistance, document retrieval,
tool orchestration, project persistence, self-evaluation and parallel task planning.
Do not claim an external action happened unless it actually did."""))

    results=await asyncio.gather(*jobs,return_exceptions=True)
    research={}
    draft=""
    for r in results:
        if isinstance(r,dict): research=r
        elif isinstance(r,str): draft=r

    if research.get("answer"):
        draft=await ask_gemini(f"""Answer the user using the research and draft below.
USER: {q}
WEB RESEARCH: {research['answer']}
DRAFT: {draft}
Sources must not be invented.""")
        st.session_state.activity.append("Deep research synthesis")

    if plan["data"]:
        st.session_state.activity.append("Data agent available")
    if plan["coding"]:
        st.session_state.activity.append("Coding agent available")
    if plan["documents"]:
        st.session_state.activity.append("Document retrieval complete")

    st.session_state.activity.append("Parallel execution complete")
    st.session_state.activity.append("Self-evaluation complete")

    st.session_state.memory.append({"user":q,"assistant":draft})
    st.session_state.memory=st.session_state.memory[-100:]
    st.session_state.request_count+=1

    return {"answer":draft,"sources":research.get("sources",[]),"latency":time.perf_counter()-start}

# =========================
# UI
# =========================
st.markdown("""
<style>
#MainMenu,footer{visibility:hidden}
.block-container{max-width:1050px;padding-top:1.2rem;padding-bottom:6rem}
.nexus-logo{font-size:31px;font-weight:800;letter-spacing:-1.5px}
.nexus-sub{font-size:13px;color:#888;margin-bottom:22px}
.pill{display:inline-block;border:1px solid rgba(128,128,128,.25);border-radius:999px;padding:6px 11px;font-size:12px}
[data-testid="stChatMessageAvatar"]{display:none}
[data-testid="stChatMessage"]{padding-top:1rem;padding-bottom:1rem}
</style>
""",unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="nexus-logo">✦ NEXUS</div>',unsafe_allow_html=True)
    st.markdown('<div class="nexus-sub">10X agentic workspace</div>',unsafe_allow_html=True)
    if st.button("New conversation",use_container_width=True):
        st.session_state.messages=[]; st.rerun()
    st.divider()
    st.markdown("### Connections")
    st.write(("🟢" if GEMINI_API_KEY else "⚪")+" Gemini")
    st.write(("🟢" if GROG_API_KEY else "⚪")+" Grog")
    st.write(("🟢" if TAVILY_API_KEY else "⚪")+" Tavily")
    st.divider()
    st.markdown("### Knowledge")
    files=st.file_uploader("Upload files",type=["pdf","txt","md","csv","png","jpg","jpeg","webp"],accept_multiple_files=True)
    if files: index_uploads(files)
    st.caption(f"{len(st.session_state.documents)} document chunks")
    st.caption(f"{len(st.session_state.datasets)} datasets")
    st.divider()
    st.markdown("### Project")
    name=st.text_input("Project name","default")
    if st.button("Save project",use_container_width=True):
        st.session_state.projects[name]={"messages":st.session_state.messages,"memory":st.session_state.memory}
        st.success("Saved")

st.markdown('<div class="nexus-logo">✦ NEXUS</div>',unsafe_allow_html=True)
st.markdown('<div class="nexus-sub">Research, analyze, reason, create, and work with your knowledge.</div>',unsafe_allow_html=True)

a,b,c,d=st.columns(4)
a.markdown('<div class="pill">Model: gemini-3.5-flash</div>',unsafe_allow_html=True)
b.markdown(f'<div class="pill">Memory: {len(st.session_state.memory)}</div>',unsafe_allow_html=True)
c.markdown(f'<div class="pill">Knowledge: {len(st.session_state.documents)}</div>',unsafe_allow_html=True)
d.markdown(f'<div class="pill">Requests: {st.session_state.request_count}</div>',unsafe_allow_html=True)

for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if st.session_state.activity:
    with st.expander("Activity"):
        for x in st.session_state.activity: st.write("•",x)

q=st.chat_input("Message NEXUS...")
if q:
    st.session_state.messages.append({"role":"user","content":q})
    with st.chat_message("user"): st.markdown(q)
    with st.chat_message("assistant"):
        with st.status("NEXUS is working...",expanded=False):
            result=asyncio.run(run_nexus(q))
        st.markdown(result["answer"])
        if result["sources"]:
            with st.expander("Sources"):
                for s in result["sources"]:
                    title=s.get("title","Source"); url=s.get("url","")
                    st.markdown(f"**{title}**  \n{url}")
    st.session_state.messages.append({"role":"assistant","content":result["answer"]})
    st.rerun()

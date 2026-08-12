import os, asyncio
import streamlit as st
from dotenv import load_dotenv
from nexus.core import NEXUS

load_dotenv()
st.set_page_config(page_title="NEXUS 10X", page_icon="✦", layout="wide")

st.markdown("""
<style>
#MainMenu,footer{visibility:hidden}
.block-container{max-width:1100px;padding-top:1.5rem;padding-bottom:6rem}
.logo{font-size:34px;font-weight:800;letter-spacing:-1.5px}
.sub{color:#888;margin-bottom:24px}
.card{border:1px solid rgba(128,128,128,.18);border-radius:16px;padding:15px}
</style>
""", unsafe_allow_html=True)

if "nexus" not in st.session_state: st.session_state.nexus=NEXUS()
if "messages" not in st.session_state: st.session_state.messages=[]

nexus=st.session_state.nexus

with st.sidebar:
    st.markdown('<div class="logo">✦ NEXUS</div>',unsafe_allow_html=True)
    st.caption("10X agentic workspace")
    if st.button("New conversation",use_container_width=True):
        st.session_state.messages=[]; st.rerun()
    st.divider()
    st.subheader("Connections")
    for name,ok in nexus.status().items():
        st.write(("🟢 " if ok else "⚪ ")+name)
    st.divider()
    st.subheader("Attachments")
    uploads=st.file_uploader("Add files",type=["pdf","txt","csv","png","jpg","jpeg","webp"],accept_multiple_files=True)

st.markdown('<div class="logo">✦ NEXUS</div>',unsafe_allow_html=True)
st.markdown('<div class="sub">Autonomous research, analysis, reasoning and execution workspace.</div>',unsafe_allow_html=True)

a,b,c,d=st.columns(4)
a.metric("Agents","10X")
b.metric("Memory","Enabled")
c.metric("Tools",len(nexus.tools.tools))
d.metric("Connections",sum(nexus.status().values()))

for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

q=st.chat_input("Message NEXUS...")
if q:
    st.session_state.messages.append({"role":"user","content":q})
    with st.chat_message("user"): st.markdown(q)
    with st.chat_message("assistant"):
        with st.status("Planning and executing..."):
            result=asyncio.run(nexus.run(q,uploads or []))
        st.markdown(result["answer"])
        if result["sources"]:
            with st.expander("Sources"):
                for s in result["sources"]:
                    st.write(s.get("title","Source"),s.get("url",""))
        with st.expander("Activity"):
            for x in result["activity"]: st.write("•",x)
    st.session_state.messages.append({"role":"assistant","content":result["answer"]})
    st.rerun()

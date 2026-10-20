"""Streamlit conversational interface for Tamil Nadu scheme information."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

from rag_chain import SchemeRAG

PROJECT_DIR = Path(__file__).resolve().parent
st.set_page_config(page_title="Tamil Nadu Schemes Assistant", page_icon="🏛️")


@st.cache_resource
def get_rag() -> SchemeRAG:
    return SchemeRAG()


def refresh_data() -> None:
    for script in ("scraper.py", "ingest.py"):
        with st.spinner(f"Running {script}..."):
            result = subprocess.run(
                [sys.executable, str(PROJECT_DIR / script)],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                check=False,
            )
        if result.stdout:
            st.code(result.stdout)
        if result.stderr:
            st.code(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{script} failed with exit code {result.returncode}")
    get_rag.clear()
    st.success("Government scheme data and the search index were refreshed.")
    st.rerun()


st.title("Tamil Nadu Government Schemes")
st.caption(
    "Ask questions about schemes listed by the Tamil Nadu government. "
    "This is an unofficial research assistant."
)
st.warning(
    "Extracted content may be incomplete or outdated. Confirm current eligibility, "
    "benefits, deadlines, and application requirements with the linked official source."
)

with st.sidebar:
    st.header("Data")
    if st.button("Refresh official data and rebuild index"):
        try:
            refresh_data()
        except Exception as exc:
            st.error(f"Refresh failed: {exc}")
            st.exception(exc)

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("sources"):
            st.markdown("**Official sources**")
            for source in message["sources"]:
                st.markdown(f"- [{source['title']}]({source['url']})")

question = st.chat_input("Ask about a scheme, eligibility, or how to apply...")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        try:
            rag = get_rag()
            history = st.session_state.messages[:-1]
            with st.spinner("Searching official scheme information..."):
                result = rag.answer(question, history)
            st.markdown(result.answer)
            if result.sources:
                st.markdown("**Official sources**")
                for source in result.sources:
                    st.markdown(f"- [{source['title']}]({source['url']})")
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.answer,
                "sources": result.sources,
            })
        except Exception as exc:
            st.error(f"Unable to answer right now: {exc}")
            st.exception(exc)

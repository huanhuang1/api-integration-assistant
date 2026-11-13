"""Run with: streamlit run app.py"""

import streamlit as st

from api_assistant.assistant import IntegrationAssistant, render_markdown
from api_assistant.config import Settings
from api_assistant.store import KnowledgeStore

# Initialize the page and session.
st.set_page_config(page_title="API Integration Assistant", page_icon="🔗", layout="wide")
settings = Settings.from_env()

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("Prototype workspace")
    st.caption("Local models · LangChain · Chroma")
    st.write("**Chat model**", settings.chat_model)
    st.write("**Embedding model**", settings.embedding_model)
    try:
        # Check the records produced by ingestion before enabling chat and example buttons.
        _, manifest = KnowledgeStore(settings).load()
        st.success(f"{manifest['workflow_count']} workflows · {manifest['operation_count']} APIs")
        ready = True
    except Exception as exc:
        st.warning(str(exc))
        st.code("api-assistant ingest", language="bash")
        ready = False
    st.divider()
    st.markdown("**How a question becomes a guide**")
    st.markdown(
        "1. Embed the question\n2. Search workflow descriptions\n3. Select or ask for clarification\n4. Load full API specs and rules\n5. Validate examples and explain"
    )
    st.caption("The workflow registry supplies API order. Retrieval scores do not.")
    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("API Integration Assistant")
st.write(
    "Describe the account-opening scenario. Get the API sequence, relevant fields, and sample requests."
)
st.caption("Fictional demo data. Guidance only — this application never executes banking APIs.")

examples = {
    "Personal account": "Open a USD account for a new individual customer. Which APIs and fields do I need?",
    "Business account": "Open a EUR account for a new company. Show the API sequence and sample requests.",
    "Needs clarification": "I want to open an account.",
    "Failed verification": "Open a USD account for a new individual customer, but identity verification failed.",
}
selected_example = None
columns = st.columns(len(examples))
for column, (label, prompt) in zip(columns, examples.items(), strict=True):
    if column.button(label, disabled=not ready, use_container_width=True):
        selected_example = prompt

if selected_example:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("trace"):
            with st.expander("Inspect retrieval and backend lookups"):
                st.json(message["trace"])

typed_prompt = st.chat_input(
    "For example: Open a USD account for a new individual", disabled=not ready
)
prompt = selected_example or typed_prompt
if prompt:
    # Each example starts fresh, so a previous failed-verification scenario cannot leak into it.
    if selected_example:
        st.session_state.messages = []
        history = []
    else:
        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Searching workflows and checking the integration guide…"):
            answer = IntegrationAssistant(settings).invoke(prompt, history)
        content = render_markdown(answer)
        st.markdown(content)
        with st.expander("Inspect retrieval and backend lookups"):
            st.json(answer.trace)
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": content,
            "trace": answer.trace,
        }
    )

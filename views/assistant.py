"""Claude-powered health assistant."""

import datetime as dt

import streamlit as st

import ai_assistant as ai
import auth
import data_service as ds


def render():
    auth.require()
    st.title("AI Health Assistant")
    st.caption("Powered by Claude. Interprets your recent Garmin trends.")

    key = ai.resolve_key(st.session_state.get("anthropic_key"))
    if not key:
        st.warning("Add your Claude API key to enable the assistant.")
        with st.form("claude_key"):
            entered = st.text_input(
                "Anthropic API key", type="password",
                help="Get one at https://platform.claude.com. Stored only in this session.",
            )
            if st.form_submit_button("Save key", type="primary") and entered:
                st.session_state.anthropic_key = entered
                st.rerun()
        st.stop()

    top = st.columns([1, 2])
    context_days = top[0].slider("Days of context", 7, 30, 14)
    df = ds.summaries_range(context_days, dt.date.today().isoformat())
    acts = ds.recent_activities(10)
    health_context = ai.build_health_context(df, acts)

    with st.expander("Data shared with Claude"):
        st.text(health_context)

    if "chat" not in st.session_state:
        st.session_state.chat = []

    for msg in st.session_state.chat:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if not st.session_state.chat:
        st.markdown("**Try asking:**")
        cols = st.columns(3)
        suggestions = [
            "Summarize my week. What's going well?",
            "How is my sleep affecting my energy?",
            "Give me 3 concrete goals for next week.",
        ]
        for col, s in zip(cols, suggestions):
            if col.button(s, use_container_width=True):
                st.session_state.pending = s
                st.rerun()

    prompt = st.chat_input("Ask about your health data...")
    if not prompt and "pending" in st.session_state:
        prompt = st.session_state.pop("pending")

    if prompt:
        st.session_state.chat.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                reply = st.write_stream(
                    ai.stream_reply(st.session_state.chat, health_context, api_key=key)
                )
            except Exception as e:
                st.error(f"Claude API error: {e}")
                st.session_state.chat.pop()
            else:
                st.session_state.chat.append({"role": "assistant", "content": reply})

    if st.session_state.chat and top[1].button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()

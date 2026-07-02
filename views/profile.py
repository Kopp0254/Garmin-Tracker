"""Profile & settings."""

import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()
    prof = auth.profile()

    # ---- Profile header ---------------------------------------------------
    head = st.columns([1, 3], vertical_alignment="center")
    with head[0]:
        st.markdown(auth.avatar_html(prof, 120), unsafe_allow_html=True)
    with head[1]:
        st.title(prof.get("name") or "Athlete")
        bits = []
        if prof.get("location"):
            bits.append(prof["location"])
        if prof.get("username"):
            bits.append(prof["username"])
        st.markdown("  |  ".join(bits) if bits else "&nbsp;")
        st.caption(f"Connected via {prof.get('source', 'Garmin')}")

    st.divider()

    # ---- Fun stats --------------------------------------------------------
    stats = st.columns(3)
    vo2 = prof.get("vo2max")
    stats[0].metric("VO₂ max (run)", f"{vo2:.0f}" if vo2 else "-")
    level = prof.get("level")
    stats[1].metric("Garmin level", level if level is not None else "-")
    stats[2].metric("Gender", (prof.get("gender") or "-").title())

    st.divider()

    # ---- Settings ---------------------------------------------------------
    st.subheader("Settings")
    cur = ds.units()
    choice = st.radio(
        "Preferred units", ["imperial", "metric"],
        index=0 if cur == "imperial" else 1,
        format_func=lambda u: "Imperial (miles)" if u == "imperial" else "Metric (km)",
        horizontal=True,
    )
    if choice != cur:
        st.session_state.units = choice
        st.rerun()

    with st.expander("Claude API key (for the AI Assistant)"):
        existing = bool(st.session_state.get("anthropic_key"))
        st.caption("Stored only in this browser session." +
                   (" A key is currently set." if existing else ""))
        entered = st.text_input("Anthropic API key", type="password",
                                value="", placeholder="sk-ant-...")
        cols = st.columns(2)
        if cols[0].button("Save key", type="primary") and entered:
            st.session_state.anthropic_key = entered
            st.success("Saved.")
        if cols[1].button("Clear key") and existing:
            st.session_state.pop("anthropic_key", None)
            st.rerun()

    st.divider()
    if st.button("Log out", type="secondary"):
        auth.logout()
        st.rerun()

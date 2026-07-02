"""In-app authentication + profile state.

Credentials are entered in the sidebar and held only in ``st.session_state``
for the browser session - nothing is written to disk except the Garmin login
token cache (per account, git-ignored). No password is stored.
"""

from __future__ import annotations

import html
import os

import streamlit as st

import garmin_client as gc


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def is_authed() -> bool:
    return st.session_state.get("provider") is not None


def provider():
    return st.session_state.get("provider")


def account_key() -> str:
    return st.session_state.get("account", "anon")


def profile() -> dict:
    return st.session_state.get("profile", {})


def _activate(prov, account: str):
    st.session_state.provider = prov
    st.session_state.account = account
    try:
        st.session_state.profile = prov.profile()
    except Exception:
        st.session_state.profile = {}
    try:
        st.session_state.units = prov.unit_system()
    except Exception:
        st.session_state.setdefault("units", "imperial")
    st.cache_data.clear()


def login_garmin(email: str, password: str):
    """Raises on failure so the caller can show the error."""
    prov = gc.GarminConnectProvider(email, password)
    _activate(prov, email.lower())


def start_demo():
    _activate(gc.DemoProvider(), "demo")


def logout():
    for key in ("provider", "account", "profile", "units", "anthropic_key"):
        st.session_state.pop(key, None)
    st.cache_data.clear()


def try_env_autologin():
    """One-shot convenience login from .env (headless/kiosk). No-op unless
    GARMIN_EMAIL/PASSWORD are set; failures fall through to the sidebar login."""
    if is_authed() or st.session_state.get("_env_login_tried"):
        return
    st.session_state["_env_login_tried"] = True
    email, pw = os.getenv("GARMIN_EMAIL"), os.getenv("GARMIN_PASSWORD")
    if email and pw:
        try:
            login_garmin(email, pw)
        except Exception:
            pass


def require():
    """Guard for pages: stop with a friendly prompt if not signed in."""
    if not is_authed():
        st.title("Welcome to PaceMaker")
        st.info(
            "Sign in with your Garmin account using the panel in the sidebar, "
            "or click **Try demo** to explore with realistic sample data."
        )
        st.stop()


# ---------------------------------------------------------------------------
# UI: avatar + sidebar profile panel
# ---------------------------------------------------------------------------

def _initials(name: str | None) -> str:
    if not name:
        return "?"
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def avatar_html(prof: dict, size: int = 64) -> str:
    """Circular avatar: Garmin photo if available, else an initials monogram."""
    url = prof.get("avatar")
    if url:
        return (
            f'<img src="{html.escape(url)}" alt="avatar" '
            f'style="width:{size}px;height:{size}px;border-radius:50%;'
            f'object-fit:cover;border:2px solid #22d3ee;" />'
        )
    initials = html.escape(_initials(prof.get("name")))
    fs = int(size * 0.4)
    return (
        f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
        f'background:linear-gradient(135deg,#22d3ee,#6366f1);color:#0e1117;'
        f'display:flex;align-items:center;justify-content:center;'
        f'font-weight:700;font-size:{fs}px;border:2px solid #22d3ee;">{initials}</div>'
    )


def sidebar_panel(profile_page=None):
    """Render the login form (logged-out) or profile card (logged-in) at the
    top of the sidebar, above the navigation menu."""
    with st.sidebar:
        if is_authed():
            prof = profile()
            name = prof.get("name") or "Athlete"
            sub = prof.get("location") or prof.get("source", "")
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:12px;'
                f'padding:6px 2px 10px;">{avatar_html(prof, 56)}'
                f'<div style="line-height:1.25;">'
                f'<div style="font-weight:700;font-size:1.02rem;">{html.escape(name)}</div>'
                f'<div style="color:#94a3b8;font-size:0.8rem;">{html.escape(sub)}</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            cols = st.columns(2)
            if profile_page is not None:
                cols[0].page_link(profile_page, label="Profile")
            if cols[1].button("Log out", use_container_width=True):
                logout()
                st.rerun()
            if st.button("Refresh data", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
            st.divider()
        else:
            st.markdown("### Sign in")
            with st.form("garmin_login", clear_on_submit=False):
                email = st.text_input("Garmin email", key="login_email")
                password = st.text_input("Password", type="password",
                                         key="login_password")
                submitted = st.form_submit_button("Log in", use_container_width=True,
                                                  type="primary")
            if submitted:
                if not (email and password):
                    st.error("Enter your Garmin email and password.")
                else:
                    with st.spinner("Signing in to Garmin..."):
                        try:
                            login_garmin(email, password)
                        except Exception as e:
                            st.error(f"Login failed: {e}")
                        else:
                            st.rerun()
            if st.button("Try demo", use_container_width=True):
                start_demo()
                st.rerun()
            st.caption(
                "Credentials stay in your browser session only. If your "
                "account uses MFA, complete the prompt once."
            )
            st.divider()

"""Garmin Health & Fitness Dashboard - entry point.

Uses st.navigation so we can render a profile/login panel above the sidebar
navigation. Log in with your Garmin account from the sidebar (or Try demo).
"""

import streamlit as st

st.set_page_config(
    page_title="Garmin Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

import auth  # noqa: E402
import data_service as ds  # noqa: E402
from views import (  # noqa: E402
    activity, assistant, heart, home, profile, running, sleep,
)

# Pages - each render() shares the function name, so give explicit url_paths.
home_pg = st.Page(home.render, title="Home", url_path="home", default=True)
activity_pg = st.Page(activity.render, title="Activity", url_path="activity")
running_pg = st.Page(running.render, title="Running", url_path="running")
sleep_pg = st.Page(sleep.render, title="Sleep", url_path="sleep")
heart_pg = st.Page(heart.render, title="Heart Rate & Stress", url_path="heart")
assistant_pg = st.Page(assistant.render, title="AI Assistant", url_path="assistant")
profile_pg = st.Page(profile.render, title="Profile", url_path="profile")

# Reorder the sidebar so our profile/login panel sits ABOVE the nav menu
# (Streamlit otherwise pins the nav to the top). All three are flex siblings
# of stSidebarContent.
st.markdown(
    """
    <style>
      section[data-testid="stSidebar"] div[data-testid="stSidebarContent"]{
          display:flex; flex-direction:column;
      }
      div[data-testid="stSidebarHeader"]{ order:0; }
      div[data-testid="stSidebarUserContent"]{ order:1; }
      div[data-testid="stSidebarNav"]{ order:2; }
      div[data-testid="stSidebarUserContent"]{ padding-top:0.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Optional headless convenience: log in from .env if present (no-op otherwise).
auth.try_env_autologin()

# Profile / login panel at the very top of the sidebar.
auth.sidebar_panel(profile_page=profile_pg)

pg = st.navigation({
    "Dashboard": [home_pg, activity_pg, running_pg, sleep_pg, heart_pg],
    "Coach": [assistant_pg],
    "Account": [profile_pg],
})

pg.run()

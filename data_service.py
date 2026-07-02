"""Cached data access + shared UI helpers for all pages.

The active provider now comes from the logged-in session (see auth.py), so
cached functions are keyed by an ``account`` argument to keep users' data
separate. Public wrappers inject the current account so call sites stay clean.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth

KM_TO_MI = 0.621371

CHART_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=10, r=10, t=30, b=10),
    font=dict(color="#e6e9ef"),
)
ACCENT = "#22d3ee"


def units() -> str:
    return st.session_state.get("units", "imperial").lower()


def _provider():
    """Active provider, or a demo provider as a safe fallback."""
    prov = auth.provider()
    if prov is None:
        import garmin_client as gc
        prov = gc.DemoProvider()
    return prov


# ---------------------------------------------------------------------------
# Cached fetchers (keyed by account so data never leaks between logins)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900, show_spinner=False)
def _daily_summary(account: str, date_iso: str) -> dict:
    return asdict(_provider().daily_summary(dt.date.fromisoformat(date_iso)))


@st.cache_data(ttl=900, show_spinner="Loading history...")
def _summaries_range(account: str, days: int, end_iso: str) -> pd.DataFrame:
    end = dt.date.fromisoformat(end_iso)
    rows = [_daily_summary(account, (end - dt.timedelta(days=i)).isoformat())
            for i in range(days - 1, -1, -1)]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=900, show_spinner=False)
def _intraday(account: str, kind: str, date_iso: str) -> pd.DataFrame:
    prov = _provider()
    date = dt.date.fromisoformat(date_iso)
    series = {
        "hr": prov.heart_rate_series,
        "stress": prov.stress_series,
        "body_battery": prov.body_battery_series,
    }[kind](date)
    return pd.DataFrame(series, columns=["time", "value"])


@st.cache_data(ttl=900, show_spinner=False)
def _recent_activities(account: str, limit: int) -> pd.DataFrame:
    return pd.DataFrame([asdict(a) for a in _provider().activities(limit)])


@st.cache_data(ttl=3600, show_spinner="Loading run details...")
def _run_details(account: str, activity_id: str) -> pd.DataFrame:
    df = pd.DataFrame([asdict(p) for p in _provider().run_details(activity_id)])
    if df.empty:
        return df
    return df.dropna(subset=["distance_m"]).sort_values("distance_m").reset_index(drop=True)


# -- public wrappers (inject current account) -------------------------------

def daily_summary(date_iso: str) -> dict:
    return _daily_summary(auth.account_key(), date_iso)


def summaries_range(days: int, end_iso: str) -> pd.DataFrame:
    return _summaries_range(auth.account_key(), days, end_iso)


def intraday(kind: str, date_iso: str) -> pd.DataFrame:
    return _intraday(auth.account_key(), kind, date_iso)


def recent_activities(limit: int = 20) -> pd.DataFrame:
    return _recent_activities(auth.account_key(), limit)


def run_details(activity_id: str) -> pd.DataFrame:
    return _run_details(auth.account_key(), activity_id)


# ---------------------------------------------------------------------------
# Split computation
# ---------------------------------------------------------------------------

def compute_splits(df: pd.DataFrame, split_m: float) -> pd.DataFrame:
    """Aggregate a detail stream into distance splits (one row per split)."""
    if df.empty or split_m <= 0:
        return pd.DataFrame()
    d = df.dropna(subset=["time_s"]).copy()
    d["split"] = (d["distance_m"] / split_m).astype(int)

    rows = []
    for split_idx, g in d.groupby("split"):
        dist = min(max(g["distance_m"].max() - split_idx * split_m, 1.0), split_m)
        t0 = d.loc[d["split"] < split_idx, "time_s"].max()
        t0 = 0.0 if pd.isna(t0) else float(t0)
        duration = float(g["time_s"].max()) - t0
        if duration <= 0:
            continue
        elev = g["elevation_m"].dropna()
        gain = float(elev.diff().clip(lower=0).sum()) if len(elev) > 1 else 0.0
        rows.append({
            "split": split_idx + 1,
            "distance_m": dist,
            "duration_s": duration,
            "pace_s": duration / dist * split_m,  # normalized to full split
            "avg_hr": g["hr"].mean(),
            "elev_gain_m": gain,
            "partial": dist < split_m * 0.98,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Formatting / chart helpers
# ---------------------------------------------------------------------------

def fmt_distance(km: float) -> str:
    if units() == "metric":
        return f"{km:.2f} km"
    return f"{km * KM_TO_MI:.2f} mi"


def fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return "-"
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m"


def fmt_pace(seconds: float | None) -> str:
    """Seconds-per-unit -> 'M:SS'."""
    if seconds is None or seconds != seconds or seconds <= 0:
        return "-"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"


def sparkline(series: pd.Series, dates: pd.Series, color: str = ACCENT) -> go.Figure:
    fig = go.Figure(
        go.Scatter(x=dates, y=series, mode="lines", fill="tozeroy",
                   line=dict(color=color, width=2))
    )
    fig.update_layout(**CHART_LAYOUT, height=90, showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def refresh_button():
    if st.sidebar.button("Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

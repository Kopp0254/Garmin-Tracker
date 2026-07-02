"""Sleep analysis."""

import datetime as dt

import plotly.graph_objects as go
import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()
    st.title("Sleep")

    c1, c2, _ = st.columns([1, 1, 2])
    days = c1.slider("History (days)", 7, 90, 30)
    picked = c2.date_input("Night of", dt.date.today(), max_value=dt.date.today())

    df = ds.summaries_range(days, dt.date.today().isoformat())
    night = ds.daily_summary(picked.isoformat())

    # ---- Last night -------------------------------------------------------
    st.subheader(f"Night of {picked.strftime('%b %d')}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Duration", ds.fmt_duration(night["sleep_seconds"]))
    c2.metric("Sleep score", night["sleep_score"] or "-")
    avg_score = df["sleep_score"].mean()
    c3.metric(f"{days}-day avg score",
              f"{avg_score:.0f}" if avg_score == avg_score else "-")

    stages = night["sleep_stages"] or {}
    if any(stages.values()):
        labels = {"deep": "Deep", "light": "Light", "rem": "REM", "awake": "Awake"}
        colors = {"deep": "#1d4ed8", "light": "#38bdf8", "rem": "#a78bfa", "awake": "#f43f5e"}
        fig = go.Figure(go.Bar(
            x=[v / 3600 for v in stages.values()],
            y=[labels.get(k, k) for k in stages.keys()],
            orientation="h",
            marker_color=[colors.get(k, "#888") for k in stages.keys()],
            text=[ds.fmt_duration(v) for v in stages.values()],
            textposition="auto",
        ))
        fig.update_layout(**ds.CHART_LAYOUT, height=240,
                          xaxis_title="Hours", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    # ---- Trends -----------------------------------------------------------
    st.subheader("Sleep duration & score trend")
    hours = df["sleep_seconds"].fillna(0) / 3600
    fig2 = go.Figure()
    fig2.add_bar(x=df["date"], y=hours, name="Hours", marker_color="#a78bfa")
    fig2.add_scatter(x=df["date"], y=df["sleep_score"], name="Score",
                     mode="lines+markers", line=dict(color="#4ade80"), yaxis="y2")
    fig2.add_hline(y=8, line_dash="dot", line_color="#facc15",
                   annotation_text="8h target")
    fig2.update_layout(
        **ds.CHART_LAYOUT, height=360, legend=dict(orientation="h"),
        yaxis=dict(title="Hours"),
        yaxis2=dict(title="Score", overlaying="y", side="right",
                    range=[0, 100], showgrid=False),
    )
    st.plotly_chart(fig2, use_container_width=True)

    consistent = hours[hours > 0]
    if len(consistent) > 1:
        st.caption(
            f"Avg: **{consistent.mean():.1f}h** · "
            f"Best: **{consistent.max():.1f}h** · "
            f"Worst: **{consistent.min():.1f}h** · "
            f"Nights ≥ 7h: **{int((consistent >= 7).sum())}/{len(consistent)}**"
        )

"""Home dashboard."""

import datetime as dt

import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()

    st.title("Health & Fitness Dashboard")
    dcol, _ = st.columns([1, 3])
    picked = dcol.date_input("Day", dt.date.today(), max_value=dt.date.today())
    st.caption(f"Snapshot for **{picked.strftime('%A, %B %d, %Y')}**")

    today = ds.daily_summary(picked.isoformat())
    yesterday = ds.daily_summary((picked - dt.timedelta(days=1)).isoformat())

    def delta(cur, prev):
        if cur is None or prev is None:
            return None
        return cur - prev

    # ---- Snapshot cards ---------------------------------------------------
    row1 = st.columns(4)
    goal_pct = 100 * today["steps"] / max(today["step_goal"], 1)
    row1[0].metric("Steps", f"{today['steps']:,}",
                   f"{goal_pct:.0f}% of {today['step_goal']:,} goal",
                   delta_color="off")
    row1[1].metric("Active Calories", f"{today['active_calories']:,}",
                   delta(today["active_calories"], yesterday["active_calories"]))
    row1[2].metric("Resting HR", f"{today['resting_hr'] or '-'} bpm",
                   delta(today["resting_hr"], yesterday["resting_hr"]),
                   delta_color="inverse")
    row1[3].metric("Sleep", ds.fmt_duration(today["sleep_seconds"]),
                   f"Score: {today['sleep_score'] or '-'}", delta_color="off")

    row2 = st.columns(4)
    bb = today["body_battery_high"]
    row2[0].metric("Body Battery (peak)", bb if bb is not None else "-",
                   f"low: {today['body_battery_low'] or '-'}", delta_color="off")
    row2[1].metric("Avg Stress", today["stress_avg"] or "-",
                   delta(today["stress_avg"], yesterday["stress_avg"]),
                   delta_color="inverse")
    row2[2].metric("Floors Climbed", today["floors_climbed"],
                   delta(today["floors_climbed"], yesterday["floors_climbed"]))
    row2[3].metric("Distance", ds.fmt_distance(today["distance_km"]),
                   delta_color="off")

    st.divider()

    # ---- Weekly trend sparklines -----------------------------------------
    st.subheader("Last 7 days")
    week = ds.summaries_range(7, picked.isoformat())

    spark_defs = [
        ("Steps", week["steps"], "#22d3ee"),
        ("Active calories", week["active_calories"], "#f97316"),
        ("Sleep (hours)", week["sleep_seconds"].fillna(0) / 3600, "#a78bfa"),
        ("Resting HR", week["resting_hr"], "#f43f5e"),
        ("Avg stress", week["stress_avg"], "#facc15"),
        ("Body battery peak", week["body_battery_high"], "#4ade80"),
    ]

    cols = st.columns(3)
    for i, (label, series, color) in enumerate(spark_defs):
        with cols[i % 3]:
            avg = series.mean()
            st.markdown(f"**{label}** · 7-day avg: `{avg:,.1f}`")
            fig = ds.sparkline(series, week["date"], color)
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False}, key=f"spark-{i}")

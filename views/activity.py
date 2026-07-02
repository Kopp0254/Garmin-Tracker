"""Activity & workouts."""

import datetime as dt

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()
    st.title("Activity")

    scol, _ = st.columns([1, 3])
    days = scol.slider("History (days)", 7, 90, 30)
    df = ds.summaries_range(days, dt.date.today().isoformat())

    # ---- Steps vs goal ----------------------------------------------------
    st.subheader("Daily steps vs. goal")
    fig = go.Figure()
    fig.add_bar(x=df["date"], y=df["steps"], name="Steps", marker_color=ds.ACCENT)
    fig.add_scatter(x=df["date"], y=df["step_goal"], name="Goal",
                    mode="lines", line=dict(color="#f97316", dash="dash"))
    fig.update_layout(**ds.CHART_LAYOUT, height=340, legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    hit = int((df["steps"] >= df["step_goal"]).sum())
    c1.metric("Goal days hit", f"{hit}/{len(df)}")
    c2.metric("Avg daily steps", f"{df['steps'].mean():,.0f}")
    c3.metric("Total distance", ds.fmt_distance(df["distance_km"].sum()))

    # ---- Calories & intensity --------------------------------------------
    st.subheader("Active calories & intensity minutes")
    fig2 = go.Figure()
    fig2.add_bar(x=df["date"], y=df["active_calories"], name="Active kcal",
                 marker_color="#f97316")
    fig2.add_scatter(x=df["date"], y=df["intensity_minutes"], name="Intensity min",
                     mode="lines+markers", line=dict(color="#4ade80"), yaxis="y2")
    fig2.update_layout(
        **ds.CHART_LAYOUT, height=340, legend=dict(orientation="h"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False),
    )
    st.plotly_chart(fig2, use_container_width=True)

    # ---- Recent workouts --------------------------------------------------
    st.subheader("Recent workouts")
    acts = ds.recent_activities(25)
    if acts.empty:
        st.info("No recent activities found.")
        return

    pie = px.pie(acts, names="activity_type", values="duration_min", hole=0.45)
    pie.update_traces(textposition="inside", textinfo="percent",
                      insidetextorientation="horizontal")
    pie.update_layout(
        **ds.CHART_LAYOUT, height=360,
        legend=dict(orientation="h", yanchor="top", y=-0.05,
                    xanchor="center", x=0.5),
    )
    pie.update_layout(margin=dict(l=10, r=10, t=10, b=70))
    left, right = st.columns([1, 1.6], gap="large")
    with left:
        st.markdown("**Time by activity type**")
        st.plotly_chart(pie, use_container_width=True,
                        config={"displayModeBar": False})
    right.dataframe(
        acts[["start_time", "name", "activity_type", "duration_min",
              "distance_km", "calories", "avg_hr"]],
        use_container_width=True, hide_index=True,
        column_config={
            "start_time": "Start",
            "name": "Activity",
            "activity_type": "Type",
            "duration_min": st.column_config.NumberColumn("Duration (min)", format="%.0f"),
            "distance_km": st.column_config.NumberColumn("Distance (km)", format="%.2f"),
            "calories": "kcal",
            "avg_hr": "Avg HR",
        },
    )

"""Heart rate, stress, and body battery."""

import datetime as dt

import plotly.graph_objects as go
import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()
    st.title("Heart Rate & Stress")

    c1, c2, _ = st.columns([1, 1, 2])
    picked = c1.date_input("Day", dt.date.today(), max_value=dt.date.today())
    days = c2.slider("Trend history (days)", 7, 90, 30)
    iso = picked.isoformat()

    hr = ds.intraday("hr", iso)
    stress = ds.intraday("stress", iso)
    bb = ds.intraday("body_battery", iso)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Heart rate")
        if hr.empty:
            st.info("No intraday heart rate data for this day.")
        else:
            fig = go.Figure(go.Scatter(x=hr["time"], y=hr["value"], mode="lines",
                                       line=dict(color="#f43f5e", width=1.5)))
            fig.update_layout(**ds.CHART_LAYOUT, height=300, yaxis_title="bpm")
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Min **{hr['value'].min()}** · Avg **{hr['value'].mean():.0f}** · "
                       f"Max **{hr['value'].max()}** bpm")

    with col2:
        st.subheader("Stress")
        if stress.empty:
            st.info("No stress data for this day.")
        else:
            fig = go.Figure(go.Scatter(x=stress["time"], y=stress["value"],
                                       mode="lines", fill="tozeroy",
                                       line=dict(color="#facc15", width=1.5)))
            fig.update_layout(**ds.CHART_LAYOUT, height=300,
                              yaxis=dict(title="Stress (0-100)", range=[0, 100]))
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Avg stress **{stress['value'].mean():.0f}**")

    st.subheader("Body battery")
    if bb.empty:
        st.info("No body battery data for this day.")
    else:
        fig = go.Figure(go.Scatter(x=bb["time"], y=bb["value"], mode="lines",
                                   fill="tozeroy", line=dict(color="#4ade80", width=2)))
        fig.update_layout(**ds.CHART_LAYOUT, height=280,
                          yaxis=dict(title="Energy (0-100)", range=[0, 100]))
        st.plotly_chart(fig, use_container_width=True)

    st.divider()

    st.subheader(f"Resting heart rate - last {days} days")
    df = ds.summaries_range(days, dt.date.today().isoformat())
    fig = go.Figure(go.Scatter(x=df["date"], y=df["resting_hr"],
                               mode="lines+markers",
                               line=dict(color="#f43f5e", width=2)))
    mean_rhr = df["resting_hr"].mean()
    if mean_rhr == mean_rhr:
        fig.add_hline(y=mean_rhr, line_dash="dot", line_color="#94a3b8",
                      annotation_text=f"avg {mean_rhr:.0f}")
    fig.update_layout(**ds.CHART_LAYOUT, height=300, yaxis_title="bpm")
    st.plotly_chart(fig, use_container_width=True)

"""Running - per-run deep dive: map, elevation, HR, pace, and splits."""

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import auth
import data_service as ds


def render():
    auth.require()
    st.title("Running")

    ucol, _ = st.columns([1, 2])
    unit_label = ucol.radio(
        "Pace / distance units", ["Miles", "Kilometers"],
        index=0 if ds.units() == "imperial" else 1, horizontal=True,
    )
    MI = unit_label == "Miles"
    UNIT_M = 1609.344 if MI else 1000.0
    U = "mi" if MI else "km"

    acts = ds.recent_activities(50)
    runs = acts[acts["activity_type"].str.contains("run", case=False, na=False)] \
        if not acts.empty else acts
    if runs.empty:
        st.info("No running activities found in your recent history.")
        return

    labels = {
        row["activity_id"]: (
            f"{row['start_time'][:16]} - {row['name']} "
            f"({row['distance_km'] * 1000 / UNIT_M:.2f} {U})"
        )
        for _, row in runs.iterrows()
    }
    run_id = st.selectbox("Choose a run", list(labels.keys()),
                          format_func=labels.get)

    df = ds.run_details(run_id)
    if df.empty:
        st.warning("No detail stream available for this run.")
        return

    run = runs[runs["activity_id"] == run_id].iloc[0]
    dist_u = df["distance_m"] / UNIT_M
    total_dist = float(dist_u.max())
    total_time = float(df["time_s"].max() or run["duration_min"] * 60)
    avg_pace = total_time / total_dist if total_dist > 0 else None
    elev = df["elevation_m"].dropna()
    gain = float(elev.diff().clip(lower=0).sum()) if len(elev) > 1 else 0.0
    gain_disp = f"{gain * 3.28084:.0f} ft" if MI else f"{gain:.0f} m"

    # ---- Summary cards ----------------------------------------------------
    hr_series = df["hr"].dropna()
    r1 = st.columns(3)
    r1[0].metric("Distance", f"{total_dist:.2f} {U}")
    r1[1].metric("Duration", ds.fmt_duration(int(total_time)))
    r1[2].metric("Avg pace", f"{ds.fmt_pace(avg_pace)} /{U}")
    r2 = st.columns(3)
    r2[0].metric("Avg HR", f"{hr_series.mean():.0f} bpm" if not hr_series.empty else "-")
    r2[1].metric("Max HR", f"{hr_series.max():.0f} bpm" if not hr_series.empty else "-")
    r2[2].metric("Elev. gain", gain_disp)

    st.divider()

    # ---- Route map + elevation -------------------------------------------
    map_col, elev_col = st.columns([1.1, 1])
    gps = df.dropna(subset=["lat", "lon"])
    with map_col:
        st.subheader("Route")
        if gps.empty:
            st.info("No GPS data for this run (treadmill?).")
        else:
            lat_c, lon_c = gps["lat"].mean(), gps["lon"].mean()
            span_km = max(
                (gps["lat"].max() - gps["lat"].min()) * 111,
                (gps["lon"].max() - gps["lon"].min()) * 111 * math.cos(math.radians(lat_c)),
                0.3,
            )
            zoom = max(10.0, min(15.0, 13.6 - math.log2(span_km)))
            fig = go.Figure(go.Scattermapbox(
                lat=gps["lat"], lon=gps["lon"], mode="lines",
                line=dict(color=ds.ACCENT, width=3),
                hovertext=[f"{d:.2f} {U}" for d in gps["distance_m"] / UNIT_M],
                hoverinfo="text", name="",
            ))
            fig.add_trace(go.Scattermapbox(
                lat=[gps["lat"].iloc[0], gps["lat"].iloc[-1]],
                lon=[gps["lon"].iloc[0], gps["lon"].iloc[-1]],
                mode="markers+text",
                marker=dict(size=12, color=["#4ade80", "#f43f5e"]),
                text=["Start", "Finish"], textposition="top center",
                textfont=dict(color="#e6e9ef"), hoverinfo="none", name="",
            ))
            fig.update_layout(
                mapbox=dict(style="carto-darkmatter",
                            center=dict(lat=lat_c, lon=lon_c), zoom=zoom),
                margin=dict(l=0, r=0, t=0, b=0), height=380,
                showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

    with elev_col:
        st.subheader("Elevation")
        if elev.empty:
            st.info("No elevation data.")
        else:
            e = df.dropna(subset=["elevation_m"])
            y = e["elevation_m"] * (3.28084 if MI else 1.0)
            fig = go.Figure(go.Scatter(
                x=e["distance_m"] / UNIT_M, y=y, mode="lines", fill="tozeroy",
                line=dict(color="#a78bfa", width=2), name="",
            ))
            fig.update_layout(
                **ds.CHART_LAYOUT, height=380, showlegend=False,
                xaxis_title=f"Distance ({U})",
                yaxis=dict(title="Elevation (ft)" if MI else "Elevation (m)",
                           range=[float(y.min()) - 10, float(y.max()) + 10]),
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

    # ---- HR + pace over the run ------------------------------------------
    hr_col, pace_col = st.columns(2)
    with hr_col:
        st.subheader("Heart rate")
        h = df.dropna(subset=["hr"])
        if h.empty:
            st.info("No heart rate data.")
        else:
            fig = go.Figure(go.Scatter(
                x=h["distance_m"] / UNIT_M, y=h["hr"], mode="lines",
                line=dict(color="#f43f5e", width=2), name="",
            ))
            fig.add_hline(y=float(h["hr"].mean()), line_dash="dot",
                          line_color="#94a3b8",
                          annotation_text=f"avg {h['hr'].mean():.0f}")
            fig.update_layout(**ds.CHART_LAYOUT, height=300, showlegend=False,
                              xaxis_title=f"Distance ({U})", yaxis_title="bpm")
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

    with pace_col:
        st.subheader(f"Pace (min/{U})")
        p = df.dropna(subset=["speed_mps"]).copy()
        p = p[p["speed_mps"] > 0.5]
        if p.empty:
            st.info("No pace data.")
        else:
            pace_s = (UNIT_M / p["speed_mps"]).rolling(9, min_periods=1,
                                                       center=True).mean()
            fig = go.Figure(go.Scatter(
                x=p["distance_m"] / UNIT_M, y=pace_s / 60, mode="lines",
                line=dict(color=ds.ACCENT, width=2), name="",
                hovertext=[f"{ds.fmt_pace(s)} /{U}" for s in pace_s],
                hoverinfo="text+x",
            ))
            if avg_pace:
                fig.add_hline(y=avg_pace / 60, line_dash="dot",
                              line_color="#94a3b8",
                              annotation_text=f"avg {ds.fmt_pace(avg_pace)}")
            fig.update_layout(
                **ds.CHART_LAYOUT, height=300, showlegend=False,
                xaxis_title=f"Distance ({U})",
                yaxis=dict(title=f"min/{U}", autorange="reversed"),
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"displayModeBar": False})

    st.divider()

    # ---- Splits -----------------------------------------------------------
    st.subheader("Splits")
    frac = st.radio(
        "Split length", [0.25, 0.5, 1.0],
        format_func=lambda f: f"{f:g} {U}", index=2, horizontal=True,
    )
    splits = ds.compute_splits(df, split_m=frac * UNIT_M)
    if splits.empty:
        st.info("Not enough data to compute splits.")
        return

    colors = ["rgba(34,211,238,0.45)" if part else ds.ACCENT
              for part in splits["partial"]]
    fig = go.Figure()
    fig.add_bar(
        x=splits["split"], y=splits["pace_s"] / 60, name="Pace",
        marker_color=colors,
        text=[ds.fmt_pace(s) + ("*" if part else "")
              for s, part in zip(splits["pace_s"], splits["partial"])],
        textposition="outside",
    )
    fig.add_scatter(
        x=splits["split"], y=splits["avg_hr"], name="Avg HR",
        mode="lines+markers", line=dict(color="#f43f5e"), yaxis="y2",
    )
    if avg_pace:
        fig.add_hline(y=avg_pace / 60, line_dash="dot", line_color="#94a3b8")
    pace_min = splits["pace_s"] / 60
    fig.update_layout(
        **ds.CHART_LAYOUT, height=360, legend=dict(orientation="h"),
        xaxis=dict(title=f"Split # ({frac:g} {U} each)", dtick=1),
        yaxis=dict(title=f"Pace (min/{U})",
                   range=[float(pace_min.min()) * 0.85,
                          float(pace_min.max()) * 1.12]),
        yaxis2=dict(title="Avg HR (bpm)", overlaying="y", side="right",
                    showgrid=False),
    )
    st.plotly_chart(fig, use_container_width=True,
                    config={"displayModeBar": False})
    if splits["partial"].any():
        st.caption("\\* partial split - pace normalized to full split distance")

    table = pd.DataFrame({
        "Split": splits["split"],
        f"Distance ({U})": (splits["distance_m"] / UNIT_M).round(2),
        "Time": splits["duration_s"].apply(lambda s: ds.fmt_duration(int(s))
                                           if s >= 3600 else ds.fmt_pace(s)),
        f"Pace (/{U})": splits["pace_s"].apply(ds.fmt_pace),
        "Avg HR": splits["avg_hr"].round(0),
        "Elev. gain": (splits["elev_gain_m"] * (3.28084 if MI else 1)).round(0),
    })
    with st.expander("Split table"):
        st.dataframe(table, use_container_width=True, hide_index=True)

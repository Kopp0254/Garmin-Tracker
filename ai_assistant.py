"""Claude-powered health assistant.

Builds a compact context block from the user's recent Garmin data and chats
about it via the Anthropic Messages API (streaming).
"""

from __future__ import annotations

import datetime as dt
import os

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are a friendly, evidence-minded health and fitness \
assistant embedded in a personal Garmin dashboard. You are given the user's \
recent health metrics (steps, sleep, heart rate, stress, body battery, \
activities) as structured context.

Guidelines:
- Interpret trends plainly and concretely; reference the actual numbers.
- Highlight what's going well before what needs work.
- Offer practical, modest suggestions (sleep timing, activity, recovery).
- You are not a doctor: for anything that looks medically concerning \
(e.g., unusual resting heart rate changes), suggest consulting a physician \
rather than diagnosing.
- Keep answers concise and skimmable."""


def resolve_key(session_key: str | None = None) -> str | None:
    """Prefer an in-app key; fall back to the environment."""
    return session_key or os.getenv("ANTHROPIC_API_KEY") or None


def build_health_context(df: pd.DataFrame, activities: pd.DataFrame) -> str:
    """Summarize the last N days of data into a text block for the model."""
    lines = [f"Health data as of {dt.date.today().isoformat()} "
             f"(last {len(df)} days, oldest first):", ""]
    for _, r in df.iterrows():
        sleep_h = (r["sleep_seconds"] or 0) / 3600
        lines.append(
            f"- {r['date'].date()}: steps={r['steps']} (goal {r['step_goal']}), "
            f"active_kcal={r['active_calories']}, resting_hr={r['resting_hr']}, "
            f"sleep={sleep_h:.1f}h (score {r['sleep_score']}), "
            f"stress_avg={r['stress_avg']}, "
            f"body_battery={r['body_battery_low']}-{r['body_battery_high']}, "
            f"distance_km={r['distance_km']:.1f}, floors={r['floors_climbed']}, "
            f"intensity_min={r['intensity_minutes']}"
        )
    if not activities.empty:
        lines += ["", "Recent workouts:"]
        for _, a in activities.head(8).iterrows():
            lines.append(
                f"- {a['start_time']}: {a['name']} ({a['activity_type']}), "
                f"{a['duration_min']} min, {a['distance_km']} km, "
                f"{a['calories']} kcal, avg HR {a['avg_hr']}"
            )
    return "\n".join(lines)


def stream_reply(history: list[dict], health_context: str, api_key: str | None = None):
    """Yield text chunks for st.write_stream.

    `history` is a list of {"role": "user"|"assistant", "content": str}.
    The health context is cached with prompt caching so repeated turns are cheap.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": f"<health_data>\n{health_context}\n</health_data>",
            "cache_control": {"type": "ephemeral"},
        },
    ]

    with client.messages.stream(
        model=MODEL,
        max_tokens=4096,
        thinking={"type": "adaptive"},
        system=system,
        messages=history,
    ) as stream:
        for event in stream:
            if (event.type == "content_block_delta"
                    and event.delta.type == "text_delta"):
                yield event.delta.text

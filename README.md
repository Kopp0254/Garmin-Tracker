# PaceMaker

[Visit the website here](https://pacemaker.streamlit.app)

A multi-page **Streamlit** dashboard that connects to your real Garmin account,
pulls your health and fitness metrics, and includes a **Claude-powered AI
assistant** that interprets your trends.

## Pages

| Page | What it shows |
|---|---|
| **Home** | Today's snapshot cards (steps/goal %, active calories, resting HR, sleep duration & score, body battery, stress, floors, distance) + 7-day sparklines |
| **Activity** | Steps vs. goal, active calories & intensity minutes, recent workouts table + time-by-type breakdown |
| **Running** | Per-run deep dive: route map, elevation, heart rate, pace (mi/km), and configurable split chart |
| **Sleep** | Nightly duration, sleep score, stage breakdown (deep/light/REM/awake), duration & score trends |
| **Heart Rate & Stress** | Intraday HR, stress, and body battery curves; resting-HR trend |
| **AI Assistant** | Chat with Claude about your recent data: summaries, trend interpretation, goal suggestions |
| **Profile** | Your Garmin avatar, name, VO2 max, level; unit toggle and Claude API-key entry |

## Quick start

```bash
# 1. Install dependencies
python -m venv .venv
.venv\Scripts\activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt

# 2. Run
streamlit run main.py
```

Then **log in with your Garmin account** using the panel at the top of the
sidebar; your profile photo and name appear there once you're in. Or click
**Try demo** to explore every page with realistic synthetic data, no account
needed.

## Signing in

The dashboard uses **in-app login**; there's no need to edit any files.

### Garmin (works immediately, recommended for personal use)

Enter your normal Garmin Connect email + password in the sidebar. This uses the
unofficial `garminconnect` library (session auth). Login tokens are cached
per-account in `.garmin_tokens/` (git-ignored), so subsequent logins are fast.
Credentials are held only in your browser session and are never written to
disk. If your account uses MFA, complete the prompt once.

> Credentials can still be pre-filled via a `.env` file (`GARMIN_EMAIL` /
> `GARMIN_PASSWORD`) for a headless/kiosk setup, but the sidebar login is the
> primary path.

### Official Garmin Health API (OAuth 1.0a)

1. Go to https://developer.garmin.com/health-api/overview/
2. Click **Request Access** and fill out the developer application
   (select *Personal / Research* as the use case).
3. Garmin reviews and emails your credentials in ~1-5 business days:
   `CONSUMER_KEY` and `CONSUMER_SECRET`.
4. Add them to `.env` as `GARMIN_CONSUMER_KEY` / `GARMIN_CONSUMER_SECRET`.
5. Complete the one-time **user authorization** (OAuth 1.0a three-legged flow)
   against `https://connectapi.garmin.com/oauth-service/oauth/...` to obtain a
   user token/secret, and store them as `GARMIN_USER_TOKEN` /
   `GARMIN_USER_SECRET`.

> Note: the Health API is primarily **push-based** (Garmin POSTs to webhook
> endpoints you register). This app uses the pull/backfill endpoints, which are
> sufficient for a personal dashboard. Provider selection order is:
> garminconnect, then Health API, then demo mode.

## Claude AI assistant

Paste your Claude API key on the **Profile** page (or when the AI Assistant
page prompts); get one at https://platform.claude.com. The key is stored only
in your browser session. (You can also set `ANTHROPIC_API_KEY` in `.env` as a
default.) The assistant:

- receives a compact summary of your last 7-30 days (viewable under
  *"Data shared with Claude"*)
- uses **prompt caching** on the health context so multi-turn chats are cheap
- streams responses via the Messages API (`claude-opus-4-8`, adaptive thinking)

## Project structure

```
main.py                    # Entry: st.navigation + sidebar profile/login panel
auth.py                    # In-app login, session state, profile card + avatar
views/                     # home, activity, running, sleep, heart, assistant, profile
garmin_client.py           # Data layer: garminconnect / Health API / demo providers
data_service.py            # Per-account caching + chart/format helpers
ai_assistant.py            # Claude integration (streaming, prompt caching)
.streamlit/config.toml     # Dark theme
.env.example               # Optional credential defaults
```

## Notes & limits

- The unofficial `garminconnect` library scrapes the same endpoints as the
  Garmin Connect app; heavy polling can trigger rate limits, so data here is
  cached for 15 minutes (use the sidebar **Refresh data** button to force).
- Health data is fetched read-only; nothing is written to your Garmin account.
- The AI assistant is not medical advice.

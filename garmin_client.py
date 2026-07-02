"""Garmin data layer.

Supports three providers, tried in this order:

1. ``garminconnect`` (unofficial, session auth with email/password) works
   immediately for personal dashboards. Tokens are cached in .garmin_tokens/
   so the password is only needed on first login.
2. Official Garmin Health API (OAuth 1.0a, CONSUMER_KEY/SECRET) is scaffolded
   in ``GarminHealthAPIProvider``; activates once Garmin approves your
   developer application. Note: the Health API is push-based (ping/pull
   webhooks), so a full integration needs a registered endpoint; the backfill
   endpoints used here work for personal pulls.
3. Demo mode gives deterministic synthetic data so the dashboard runs with no
   credentials at all.

Every provider returns the same normalized dict shapes, so the UI pages never
touch raw Garmin payloads.
"""

from __future__ import annotations

import datetime as dt
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

TOKEN_DIR = Path(__file__).parent / ".garmin_tokens"


# ---------------------------------------------------------------------------
# Normalized record shapes
# ---------------------------------------------------------------------------

@dataclass
class DailySummary:
    date: dt.date
    steps: int = 0
    step_goal: int = 10000
    active_calories: int = 0
    total_calories: int = 0
    resting_hr: int | None = None
    distance_km: float = 0.0
    floors_climbed: int = 0
    stress_avg: int | None = None
    body_battery_high: int | None = None
    body_battery_low: int | None = None
    sleep_seconds: int | None = None
    sleep_score: int | None = None
    sleep_stages: dict = field(default_factory=dict)  # deep/light/rem/awake seconds
    intensity_minutes: int = 0


@dataclass
class RunPoint:
    """One sample of an activity's detail stream."""
    time_s: float | None = None       # seconds since start
    lat: float | None = None
    lon: float | None = None
    elevation_m: float | None = None
    hr: int | None = None
    distance_m: float | None = None   # cumulative
    speed_mps: float | None = None


@dataclass
class Activity:
    activity_id: str
    name: str
    activity_type: str
    start_time: str
    duration_min: float
    distance_km: float
    calories: int
    avg_hr: int | None


# ---------------------------------------------------------------------------
# Provider: garminconnect (unofficial, session auth)
# ---------------------------------------------------------------------------

class GarminConnectProvider:
    """Pulls data with the unofficial garminconnect library."""

    name = "Garmin Connect (session auth)"

    def __init__(self, email: str, password: str):
        import hashlib

        from garminconnect import Garmin

        self.email = email
        self.client = Garmin(email, password)
        # Per-account token cache so multiple users don't clobber each other.
        digest = hashlib.sha256(email.lower().encode()).hexdigest()[:16]
        self._token_path = TOKEN_DIR / digest
        # login(tokenstore) resumes a cached session if present, else does a
        # full login and persists tokens to that path.
        try:
            self._token_path.mkdir(parents=True, exist_ok=True)
            self.client.login(str(self._token_path))
        except Exception:
            self.client.login()

    def profile(self) -> dict:
        """Display info for the profile card: name, avatar URL, location, etc."""
        info = {
            "name": None, "location": None, "avatar": None, "username": self.email,
            "vo2max": None, "level": None, "gender": None, "source": self.name,
        }
        try:
            info["name"] = self.client.get_full_name()
        except Exception:
            pass
        try:
            sp = self.client.connectapi("/userprofile-service/socialProfile") or {}
            info["name"] = sp.get("fullName") or info["name"]
            info["location"] = sp.get("location")
            info["username"] = sp.get("userName") or self.email
            info["avatar"] = (sp.get("profileImageUrlMedium")
                              or sp.get("profileImageUrlLarge")
                              or sp.get("profileImageUrlSmall"))
            info["level"] = sp.get("userLevel")
        except Exception:
            pass
        try:
            ud = (self.client.get_user_profile() or {}).get("userData") or {}
            info["vo2max"] = ud.get("vo2MaxRunning")
            info["gender"] = ud.get("gender")
        except Exception:
            pass
        return info

    def unit_system(self) -> str:
        """'imperial' or 'metric' based on the Garmin account setting."""
        try:
            us = (self.client.get_unit_system() or "").lower()
            return "imperial" if "statute" in us or "us" in us else "metric"
        except Exception:
            return "imperial"

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _get(d: dict | None, *keys, default=None):
        cur = d
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur if cur is not None else default

    # -- public API --------------------------------------------------------

    def daily_summary(self, date: dt.date) -> DailySummary:
        iso = date.isoformat()
        summary = DailySummary(date=date)

        try:
            stats = self.client.get_stats(iso) or {}
            summary.steps = int(stats.get("totalSteps") or 0)
            summary.step_goal = int(stats.get("dailyStepGoal") or 10000)
            summary.active_calories = int(stats.get("activeKilocalories") or 0)
            summary.total_calories = int(stats.get("totalKilocalories") or 0)
            summary.resting_hr = stats.get("restingHeartRate")
            summary.distance_km = float(stats.get("totalDistanceMeters") or 0) / 1000
            summary.floors_climbed = int(stats.get("floorsAscended") or 0)
            summary.stress_avg = stats.get("averageStressLevel")
            summary.body_battery_high = stats.get("bodyBatteryHighestValue")
            summary.body_battery_low = stats.get("bodyBatteryLowestValue")
            summary.intensity_minutes = int(
                (stats.get("moderateIntensityMinutes") or 0)
                + 2 * (stats.get("vigorousIntensityMinutes") or 0)
            )
        except Exception:
            pass

        try:
            sleep = self.client.get_sleep_data(iso) or {}
            dto = sleep.get("dailySleepDTO") or {}
            summary.sleep_seconds = dto.get("sleepTimeSeconds")
            summary.sleep_score = self._get(dto, "sleepScores", "overall", "value")
            summary.sleep_stages = {
                "deep": dto.get("deepSleepSeconds") or 0,
                "light": dto.get("lightSleepSeconds") or 0,
                "rem": dto.get("remSleepSeconds") or 0,
                "awake": dto.get("awakeSleepSeconds") or 0,
            }
        except Exception:
            pass

        return summary

    def heart_rate_series(self, date: dt.date) -> list[tuple[dt.datetime, int]]:
        """Intraday heart rate samples for one day."""
        try:
            data = self.client.get_heart_rates(date.isoformat()) or {}
            out = []
            for point in data.get("heartRateValues") or []:
                if point and point[1] is not None:
                    ts = dt.datetime.fromtimestamp(point[0] / 1000)
                    out.append((ts, int(point[1])))
            return out
        except Exception:
            return []

    def stress_series(self, date: dt.date) -> list[tuple[dt.datetime, int]]:
        try:
            data = self.client.get_stress_data(date.isoformat()) or {}
            out = []
            for point in data.get("stressValuesArray") or []:
                if point and point[1] is not None and point[1] >= 0:
                    ts = dt.datetime.fromtimestamp(point[0] / 1000)
                    out.append((ts, int(point[1])))
            return out
        except Exception:
            return []

    def body_battery_series(self, date: dt.date) -> list[tuple[dt.datetime, int]]:
        try:
            iso = date.isoformat()
            days = self.client.get_body_battery(iso, iso) or []
            out = []
            for day in days:
                for point in day.get("bodyBatteryValuesArray") or []:
                    if point and point[1] is not None:
                        ts = dt.datetime.fromtimestamp(point[0] / 1000)
                        out.append((ts, int(point[1])))
            return out
        except Exception:
            return []

    def activities(self, limit: int = 20) -> list[Activity]:
        try:
            raw = self.client.get_activities(0, limit) or []
        except Exception:
            return []
        out = []
        for a in raw:
            out.append(
                Activity(
                    activity_id=str(a.get("activityId", "")),
                    name=a.get("activityName") or "Activity",
                    activity_type=self._get(a, "activityType", "typeKey", default="other"),
                    start_time=a.get("startTimeLocal") or "",
                    duration_min=round(float(a.get("duration") or 0) / 60, 1),
                    distance_km=round(float(a.get("distance") or 0) / 1000, 2),
                    calories=int(a.get("calories") or 0),
                    avg_hr=a.get("averageHR"),
                )
            )
        return out

    def run_details(self, activity_id: str) -> list[RunPoint]:
        """Per-second detail stream (GPS, HR, elevation, pace) for one activity."""
        try:
            det = self.client.get_activity_details(
                activity_id, maxchart=2000, maxpoly=4000
            ) or {}
        except Exception:
            return []

        descriptors = det.get("metricDescriptors") or []
        idx = {d.get("key"): d.get("metricsIndex") for d in descriptors}

        def val(metrics: list, key: str):
            i = idx.get(key)
            if i is None or i >= len(metrics):
                return None
            return metrics[i]

        points = []
        for m in det.get("activityDetailMetrics") or []:
            metrics = m.get("metrics") or []
            points.append(RunPoint(
                time_s=val(metrics, "sumDuration"),
                lat=val(metrics, "directLatitude"),
                lon=val(metrics, "directLongitude"),
                elevation_m=val(metrics, "directElevation"),
                hr=val(metrics, "directHeartRate"),
                distance_m=val(metrics, "sumDistance"),
                speed_mps=val(metrics, "directSpeed"),
            ))
        return points


# ---------------------------------------------------------------------------
# Provider: Official Garmin Health API (OAuth 1.0a) - scaffold
# ---------------------------------------------------------------------------

class GarminHealthAPIProvider:
    """Official Health API client using OAuth 1.0a consumer credentials.

    The Health API is primarily push-based: Garmin POSTs data to webhook
    endpoints you register in the developer portal. For a personal dashboard,
    the backfill/pull endpoints below can be used after completing the
    one-time user authorization (OAuth 1.0a three-legged flow) to obtain a
    user access token + secret.

    This scaffold raises until you complete user authorization and store
    GARMIN_USER_TOKEN / GARMIN_USER_SECRET in .env.
    """

    name = "Garmin Health API (OAuth 1.0a)"
    BASE = "https://apis.garmin.com/wellness-api/rest"

    def __init__(self, consumer_key: str, consumer_secret: str):
        user_token = os.getenv("GARMIN_USER_TOKEN")
        user_secret = os.getenv("GARMIN_USER_SECRET")
        if not (user_token and user_secret):
            raise RuntimeError(
                "Health API consumer credentials found, but the one-time user "
                "authorization has not been completed. Run the OAuth 1.0a flow "
                "described in README.md and set GARMIN_USER_TOKEN / "
                "GARMIN_USER_SECRET in .env."
            )
        from requests_oauthlib import OAuth1Session

        self.session = OAuth1Session(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=user_token,
            resource_owner_secret=user_secret,
        )

    def _pull(self, endpoint: str, date: dt.date) -> list[dict]:
        start = int(dt.datetime.combine(date, dt.time.min).timestamp())
        end = int(dt.datetime.combine(date, dt.time.max).timestamp())
        resp = self.session.get(
            f"{self.BASE}/{endpoint}",
            params={
                "uploadStartTimeInSeconds": start,
                "uploadEndTimeInSeconds": end,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def daily_summary(self, date: dt.date) -> DailySummary:
        summary = DailySummary(date=date)
        dailies = self._pull("dailies", date)
        if dailies:
            d = dailies[-1]
            summary.steps = int(d.get("steps") or 0)
            summary.step_goal = int(d.get("stepsGoal") or 10000)
            summary.active_calories = int(d.get("activeKilocalories") or 0)
            summary.resting_hr = d.get("restingHeartRateInBeatsPerMinute")
            summary.distance_km = float(d.get("distanceInMeters") or 0) / 1000
            summary.floors_climbed = int(d.get("floorsClimbed") or 0)
            summary.stress_avg = d.get("averageStressLevel")
        sleeps = self._pull("sleeps", date)
        if sleeps:
            s = sleeps[-1]
            summary.sleep_seconds = s.get("durationInSeconds")
            summary.sleep_score = (s.get("overallSleepScore") or {}).get("value")
            summary.sleep_stages = {
                "deep": s.get("deepSleepDurationInSeconds") or 0,
                "light": s.get("lightSleepDurationInSeconds") or 0,
                "rem": s.get("remSleepInSeconds") or 0,
                "awake": s.get("awakeDurationInSeconds") or 0,
            }
        return summary

    # Intraday series and activities via the Health API require additional
    # endpoint registrations; return empty rather than failing the UI.
    def heart_rate_series(self, date):  # noqa: D102
        return []

    def stress_series(self, date):  # noqa: D102
        return []

    def body_battery_series(self, date):  # noqa: D102
        return []

    def activities(self, limit: int = 20):  # noqa: D102
        return []

    def run_details(self, activity_id: str):  # noqa: D102
        return []

    def profile(self) -> dict:
        return {"name": os.getenv("GARMIN_HEALTH_NAME", "Garmin user"),
                "location": None, "avatar": None,
                "username": None, "vo2max": None, "level": None,
                "gender": None, "source": self.name}

    def unit_system(self) -> str:
        return os.getenv("UNITS", "imperial").lower()


# ---------------------------------------------------------------------------
# Provider: demo data (no credentials required)
# ---------------------------------------------------------------------------

class DemoProvider:
    """Deterministic synthetic data so the app runs without any account."""

    name = "Demo mode (synthetic data)"

    def _rng(self, date: dt.date, salt: str = "") -> random.Random:
        return random.Random(f"{date.isoformat()}-{salt}")

    def profile(self) -> dict:
        return {
            "name": "Demo Athlete", "location": "Synthetic City",
            "avatar": None, "username": "demo",
            "vo2max": 52, "level": 3, "gender": "-", "source": self.name,
        }

    def unit_system(self) -> str:
        return os.getenv("UNITS", "imperial").lower()

    def daily_summary(self, date: dt.date) -> DailySummary:
        r = self._rng(date)
        weekend = date.weekday() >= 5
        steps = int(r.gauss(11500 if weekend else 8800, 2200))
        steps = max(2500, steps)
        sleep_sec = int(r.gauss(7.2, 0.8) * 3600)
        deep = int(sleep_sec * r.uniform(0.15, 0.22))
        rem = int(sleep_sec * r.uniform(0.18, 0.25))
        awake = int(sleep_sec * r.uniform(0.03, 0.08))
        light = sleep_sec - deep - rem - awake
        return DailySummary(
            date=date,
            steps=steps,
            step_goal=10000,
            active_calories=int(steps * 0.045 + r.gauss(120, 40)),
            total_calories=int(1900 + steps * 0.04),
            resting_hr=int(r.gauss(56, 3)),
            distance_km=round(steps * 0.00078, 2),
            floors_climbed=max(0, int(r.gauss(12, 5))),
            stress_avg=max(10, min(80, int(r.gauss(32, 10)))),
            body_battery_high=max(40, min(100, int(r.gauss(88, 8)))),
            body_battery_low=max(5, int(r.gauss(22, 8))),
            sleep_seconds=sleep_sec,
            sleep_score=max(40, min(98, int(r.gauss(78, 9)))),
            sleep_stages={"deep": deep, "light": light, "rem": rem, "awake": awake},
            intensity_minutes=max(0, int(r.gauss(45 if weekend else 25, 15))),
        )

    def _intraday(self, date: dt.date, salt: str, base: float, amp: float,
                  lo: int, hi: int, step_min: int = 15):
        r = self._rng(date, salt)
        out = []
        start = dt.datetime.combine(date, dt.time(0, 0))
        for i in range(0, 24 * 60, step_min):
            ts = start + dt.timedelta(minutes=i)
            hour = i / 60
            # circadian-ish curve
            v = base + amp * math.sin((hour - 8) / 24 * 2 * math.pi) + r.gauss(0, amp * 0.25)
            out.append((ts, int(max(lo, min(hi, v)))))
        return out

    def heart_rate_series(self, date: dt.date):
        return self._intraday(date, "hr", base=72, amp=18, lo=48, hi=165, step_min=10)

    def stress_series(self, date: dt.date):
        return self._intraday(date, "stress", base=35, amp=20, lo=5, hi=95)

    def body_battery_series(self, date: dt.date):
        r = self._rng(date, "bb")
        out = []
        start = dt.datetime.combine(date, dt.time(0, 0))
        level = r.uniform(55, 85)
        for i in range(0, 24 * 60, 15):
            ts = start + dt.timedelta(minutes=i)
            hour = i / 60
            level += (1.2 if hour < 7 else -0.45) + r.gauss(0, 0.4)
            level = max(5, min(100, level))
            out.append((ts, int(level)))
        return out

    def activities(self, limit: int = 20) -> list[Activity]:
        types = [("Morning Run", "running"), ("Evening Walk", "walking"),
                 ("Cycling", "cycling"), ("Strength Training", "strength_training"),
                 ("Yoga", "yoga")]
        out = []
        day = dt.date.today()
        r = random.Random("activities")
        i = 0
        while len(out) < limit and i < limit * 3:
            i += 1
            day -= dt.timedelta(days=r.randint(0, 2))
            name, typ = r.choice(types)
            dur = r.uniform(25, 75)
            # realistic pace per type: min/km for run/walk, km/h-ish for cycling
            if typ == "running":
                dist = dur / r.uniform(5.0, 6.5)
            elif typ == "walking":
                dist = dur / r.uniform(10.0, 13.0)
            elif typ == "cycling":
                dist = dur * r.uniform(0.3, 0.5)
            else:
                dist = 0.0
            out.append(
                Activity(
                    activity_id=f"demo-{i}",
                    name=name,
                    activity_type=typ,
                    start_time=f"{day.isoformat()} {r.randint(6, 19):02d}:{r.randint(0, 59):02d}:00",
                    duration_min=round(dur, 1),
                    distance_km=round(dist, 2),
                    calories=int(dur * r.uniform(5, 11)),
                    avg_hr=int(r.gauss(128, 15)),
                )
            )
        return out

    def run_details(self, activity_id: str) -> list[RunPoint]:
        """Synthesize a plausible GPS/HR/elevation stream for a demo activity."""
        act = next((a for a in self.activities(25) if a.activity_id == activity_id), None)
        if act is None:
            return []
        r = random.Random(activity_id)
        duration_s = act.duration_min * 60
        distance_m = max(act.distance_km, 1.0) * 1000
        base_speed = distance_m / duration_s  # m/s

        # Start near a park-ish location; wander with a slowly-turning heading
        lat, lon = 44.9778 + r.uniform(-0.05, 0.05), -93.2650 + r.uniform(-0.05, 0.05)
        heading = r.uniform(0, 2 * math.pi)
        elevation = r.uniform(240, 320)
        hr = r.uniform(105, 120)

        points, dist, t = [], 0.0, 0.0
        dt_s = 5.0
        while t <= duration_s:
            # Smooth speed variation (surges/recoveries) + gentle noise
            surge = 1 + 0.12 * math.sin(t / 180) + 0.06 * math.sin(t / 47)
            speed = max(1.5, base_speed * surge + r.gauss(0, 0.08))
            step = speed * dt_s
            dist += step

            heading += r.gauss(0, 0.18)  # slowly curving route
            lat += step * math.cos(heading) / 111_320
            lon += step * math.sin(heading) / (111_320 * math.cos(math.radians(lat)))

            elevation += r.gauss(0, 0.25) + 0.2 * math.sin(t / 300)
            # HR: warmup ramp, tracks effort, small noise
            target_hr = 120 + 45 * min(1, t / 420) * surge
            hr += (target_hr - hr) * 0.08 + r.gauss(0, 0.8)

            points.append(RunPoint(
                time_s=round(t, 1),
                lat=round(lat, 6),
                lon=round(lon, 6),
                elevation_m=round(elevation, 1),
                hr=int(hr),
                distance_m=round(dist, 1),
                speed_mps=round(speed, 3),
            ))
            t += dt_s
        return points


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def build_provider():
    """Return (provider, status_message). Never raises."""
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    consumer_key = os.getenv("GARMIN_CONSUMER_KEY")
    consumer_secret = os.getenv("GARMIN_CONSUMER_SECRET")

    if email and password:
        try:
            return GarminConnectProvider(email, password), None
        except Exception as e:
            err = f"Garmin Connect login failed ({e}). Falling back."
    else:
        err = None

    if consumer_key and consumer_secret:
        try:
            return GarminHealthAPIProvider(consumer_key, consumer_secret), err
        except Exception as e:
            err = f"{err + ' ' if err else ''}Health API unavailable ({e})."

    note = err or "No Garmin credentials in .env - running in demo mode."
    return DemoProvider(), note

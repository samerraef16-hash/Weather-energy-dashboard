"""Extract: fetch hourly weather from the Open-Meteo APIs.

Two endpoints are used:
  * archive  - reanalysis history, used for the initial backfill and to fill
               gaps if the pipeline has not run for a while.
  * forecast - the last `past_days` of recent weather plus the next
               `forecast_days` of forecast, used on every run.

All timestamps are requested in UTC so the hourly series has no daylight
saving gaps or duplicates; local time is derived later.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from .config import Config

log = logging.getLogger(__name__)


def _get_json(url: str, params: dict, cfg: Config) -> dict:
    """GET with simple exponential-backoff retries."""
    for attempt in range(1, cfg.max_retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=cfg.timeout_seconds)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == cfg.max_retries:
                raise
            wait = 2**attempt
            log.warning("Request failed (%s), retrying in %ss", exc, wait)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def parse_hourly(payload: dict, variables: tuple[str, ...]) -> pd.DataFrame:
    """Turn an Open-Meteo JSON payload into a tidy hourly DataFrame."""
    hourly = payload["hourly"]
    df = pd.DataFrame({"timestamp_utc": pd.to_datetime(hourly["time"], utc=True)})
    for var in variables:
        df[var] = pd.to_numeric(pd.Series(hourly.get(var)), errors="coerce")
    return df


def _base_params(cfg: Config) -> dict:
    return {
        "latitude": cfg.latitude,
        "longitude": cfg.longitude,
        "hourly": ",".join(cfg.hourly_variables),
        "timezone": "GMT",
        "wind_speed_unit": "kmh",
    }


def fetch_archive(cfg: Config, start: date, end: date) -> pd.DataFrame:
    log.info("Fetching archive weather %s -> %s", start, end)
    params = _base_params(cfg) | {"start_date": start.isoformat(), "end_date": end.isoformat()}
    df = parse_hourly(_get_json(cfg.archive_url, params, cfg), cfg.hourly_variables)
    # The newest archive days can be empty while reanalysis catches up.
    return df.dropna(subset=["temperature_2m"])


def fetch_recent_and_forecast(cfg: Config) -> pd.DataFrame:
    log.info("Fetching recent (%sd) + forecast (%sd) weather", cfg.past_days, cfg.forecast_days)
    params = _base_params(cfg) | {"past_days": cfg.past_days, "forecast_days": cfg.forecast_days}
    return parse_hourly(_get_json(cfg.forecast_url, params, cfg), cfg.hourly_variables)


def extract_weather(cfg: Config, last_actual: pd.Timestamp | None, now: datetime | None = None) -> pd.DataFrame:
    """Fetch everything needed to bring the database up to date.

    Returns one row per UTC hour with an `is_forecast` flag: hours before the
    current hour are actuals, the current hour onward is forecast.
    """
    now = now or datetime.now(timezone.utc)
    now_hour = pd.Timestamp(now).floor("h")
    today = now_hour.date()

    frames = []
    recent_window_start = (now_hour - pd.Timedelta(days=cfg.past_days)).date()
    archive_start = cfg.backfill_start if last_actual is None else last_actual.date()
    if archive_start < recent_window_start:
        archive_end = min(recent_window_start, today - timedelta(days=cfg.archive_lag_days))
        if archive_start <= archive_end:
            frames.append(fetch_archive(cfg, archive_start, archive_end).assign(source="archive"))

    frames.append(fetch_recent_and_forecast(cfg).assign(source="forecast_api"))

    # Later frames (fresher data) win on overlapping hours.
    weather = (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates("timestamp_utc", keep="last")
        .sort_values("timestamp_utc")
        .reset_index(drop=True)
    )
    weather["is_forecast"] = weather["timestamp_utc"] >= now_hour
    return weather

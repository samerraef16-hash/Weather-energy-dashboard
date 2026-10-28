"""Export: write a Power BI-ready star schema as CSV files.

    dim_date ──┬── fact_energy_hourly ─────── dim_building
               ├── fact_energy_daily_model ── dim_building
               ├── fact_energy_forecast ───── dim_building
               ├── fact_anomalies ─────────── dim_building
               └── fact_weather_hourly

plus three operational tables: model_metrics, pipeline_runs, data_quality_checks.

Timestamps are converted to local El Gouna time and split into a `date`
column (for the relationship to dim_date) and an `hour` column, because
those are much easier to work with in Power BI than raw UTC timestamps.
"""

from __future__ import annotations

import logging
import sqlite3

import pandas as pd

from . import store
from .config import Config
from .simulate import EGYPT_WORKDAYS

log = logging.getLogger(__name__)

WEATHER_COLUMNS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "cloud_cover", "wind_speed_10m", "shortwave_radiation", "precipitation",
]
SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring", 5: "Spring",
           6: "Summer", 7: "Summer", 8: "Summer", 9: "Autumn", 10: "Autumn", 11: "Autumn"}


def _add_local_time(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    local = df["timestamp_utc"].dt.tz_convert(tz)
    out = df.copy()
    out.insert(0, "datetime_local", local.dt.strftime("%Y-%m-%d %H:%M:%S"))
    out.insert(1, "date", local.dt.strftime("%Y-%m-%d"))
    out.insert(2, "hour", local.dt.hour)
    out["timestamp_utc"] = df["timestamp_utc"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return out


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    dates = pd.date_range(start.normalize(), end.normalize(), freq="D")
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "year": dates.year,
        "quarter": "Q" + dates.quarter.astype(str),
        "month_number": dates.month,
        "month_name": dates.strftime("%B"),
        "month_short": dates.strftime("%b"),
        "year_month": dates.strftime("%Y-%m"),
        "day_of_week_number": (dates.dayofweek + 1) % 7 + 1,  # Sunday = 1 (Egyptian week)
        "day_name": dates.strftime("%A"),
        "is_workday": dates.dayofweek.isin(EGYPT_WORKDAYS),
        "season": dates.month.map(SEASONS),
    })


def export_powerbi(conn: sqlite3.Connection, cfg: Config) -> dict[str, int]:
    out_dir = cfg.export_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    tz = cfg.timezone

    weather = store.read_table(conn, "weather_hourly").sort_values("timestamp_utc")
    energy = store.read_table(conn, "energy_hourly")
    anomalies = store.read_table(conn, "energy_anomalies")
    forecast = store.read_table(conn, "energy_forecast")
    daily = pd.read_sql_query("SELECT * FROM energy_model_daily ORDER BY building_id, date", conn)
    temps = weather[["timestamp_utc", "temperature_2m"]]
    keys = ["timestamp_utc", "building_id"]

    # The hourly fact is append-only (past hours never change), which keeps
    # the daily git commits small. Model outputs live in their own small tables.
    fact_energy = (energy.drop(columns="is_injected_anomaly")
                   .merge(temps, on="timestamp_utc", how="left")
                   .merge(anomalies[keys].assign(is_detected_anomaly=1), on=keys, how="left")
                   .sort_values(["building_id", "timestamp_utc"]))
    fact_energy["is_detected_anomaly"] = fact_energy["is_detected_anomaly"].fillna(0).astype(int)
    fact_energy["cost"] = (fact_energy["energy_kwh"] * cfg.price_per_kwh).round(2)
    fact_energy["co2_kg"] = (fact_energy["energy_kwh"] * cfg.grid_kg_co2_per_kwh).round(2)
    fact_energy = _add_local_time(fact_energy, tz)

    daily["variance_kwh"] = (daily["actual_kwh"] - daily["predicted_kwh"]).round(1)
    fact_forecast = _add_local_time(
        forecast.merge(temps, on="timestamp_utc", how="left").sort_values(keys[::-1]), tz,
    )
    fact_anomalies = _add_local_time(
        anomalies.merge(temps, on="timestamp_utc", how="left").sort_values(keys), tz,
    )
    fact_weather = _add_local_time(weather[["timestamp_utc", *WEATHER_COLUMNS, "is_forecast", "source"]], tz)

    dim_building = pd.DataFrame([
        {"building_id": b.building_id, "building_name": b.name, "building_type": b.building_type,
         "floor_area_m2": b.floor_area_m2}
        for b in cfg.buildings
    ])
    local_ts = weather["timestamp_utc"].dt.tz_convert(tz).dt.tz_localize(None)
    dim_date = build_dim_date(local_ts.min(), local_ts.max())

    runs = pd.read_sql_query("SELECT * FROM pipeline_runs ORDER BY started_at_utc", conn)
    checks = pd.read_sql_query(
        """SELECT c.*, r.started_at_utc AS run_started_at_utc FROM data_quality_checks c
           JOIN pipeline_runs r USING (run_id)
           WHERE c.run_id IN (SELECT run_id FROM pipeline_runs ORDER BY started_at_utc DESC LIMIT 30)""",
        conn,
    )
    metrics = pd.read_sql_query(
        """SELECT m.* FROM model_metrics m
           JOIN pipeline_runs r USING (run_id) ORDER BY r.started_at_utc""",
        conn,
    )

    tables = {
        "dim_date": dim_date,
        "dim_building": dim_building,
        "fact_energy_hourly": fact_energy,
        "fact_energy_daily_model": daily,
        "fact_energy_forecast": fact_forecast,
        "fact_anomalies": fact_anomalies,
        "fact_weather_hourly": fact_weather,
        "model_metrics": metrics,
        "pipeline_runs": runs,
        "data_quality_checks": checks,
    }
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")
        log.info("Exported %s (%d rows)", name, len(df))
    return {name: len(df) for name, df in tables.items()}

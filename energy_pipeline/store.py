"""Store: a small SQLite warehouse.

SQLite is a single file, needs no server, and is built into Python, which
makes it a good fit for a pipeline that runs on a free GitHub Actions runner.
Loads are upserts keyed on the primary key, so re-running a day is safe
(idempotent) and fresher data replaces older data, e.g. an actual
observation replacing the forecast made for that same hour.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS weather_hourly (
    timestamp_utc         TEXT PRIMARY KEY,
    temperature_2m        REAL,
    relative_humidity_2m  REAL,
    apparent_temperature  REAL,
    cloud_cover           REAL,
    wind_speed_10m        REAL,
    shortwave_radiation   REAL,
    precipitation         REAL,
    is_forecast           INTEGER NOT NULL,
    source                TEXT NOT NULL,
    ingested_at_utc       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS energy_hourly (
    timestamp_utc         TEXT NOT NULL,
    building_id           TEXT NOT NULL,
    energy_kwh            REAL NOT NULL,
    hvac_kwh              REAL NOT NULL,
    base_kwh              REAL NOT NULL,
    occupancy_factor      REAL NOT NULL,
    is_injected_anomaly   INTEGER NOT NULL,
    PRIMARY KEY (timestamp_utc, building_id)
);

-- Model outputs are rebuilt on every run, so they are kept small:
-- daily totals, the 7-day forecast and the list of anomalous hours.
CREATE TABLE IF NOT EXISTS energy_model_daily (
    date                  TEXT NOT NULL,
    building_id           TEXT NOT NULL,
    actual_kwh            REAL NOT NULL,
    predicted_kwh         REAL NOT NULL,
    PRIMARY KEY (date, building_id)
);

CREATE TABLE IF NOT EXISTS energy_forecast (
    timestamp_utc         TEXT NOT NULL,
    building_id           TEXT NOT NULL,
    predicted_kwh         REAL NOT NULL,
    PRIMARY KEY (timestamp_utc, building_id)
);

CREATE TABLE IF NOT EXISTS energy_anomalies (
    timestamp_utc         TEXT NOT NULL,
    building_id           TEXT NOT NULL,
    actual_kwh            REAL NOT NULL,
    predicted_kwh         REAL NOT NULL,
    excess_kwh            REAL NOT NULL,
    PRIMARY KEY (timestamp_utc, building_id)
);

CREATE TABLE IF NOT EXISTS model_metrics (
    run_id                TEXT NOT NULL,
    building_id           TEXT NOT NULL,
    trained_at_utc        TEXT NOT NULL,
    train_rows            INTEGER,
    test_rows             INTEGER,
    mae_kwh               REAL,
    mape_pct              REAL,
    r2                    REAL,
    kwh_per_cooling_degree REAL,
    kwh_per_heating_degree REAL,
    anomalies_detected    INTEGER,
    anomaly_recall_pct    REAL,
    PRIMARY KEY (run_id, building_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id                TEXT PRIMARY KEY,
    started_at_utc        TEXT NOT NULL,
    finished_at_utc       TEXT,
    status                TEXT NOT NULL,
    weather_rows_fetched  INTEGER,
    weather_rows_loaded   INTEGER,
    energy_rows_loaded    INTEGER,
    checks_passed         INTEGER,
    checks_warned         INTEGER,
    duration_seconds      REAL,
    message               TEXT
);

CREATE TABLE IF NOT EXISTS data_quality_checks (
    run_id                TEXT NOT NULL,
    dataset               TEXT NOT NULL,
    check_name            TEXT NOT NULL,
    status                TEXT NOT NULL,
    rows_affected         INTEGER,
    detail                TEXT,
    PRIMARY KEY (run_id, dataset, check_name)
);
"""

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def _to_db(df: pd.DataFrame) -> pd.DataFrame:
    """Convert pandas types to SQLite-friendly ones (UTC text timestamps, 0/1 bools)."""
    out = df.copy()
    for col in out.columns:
        if isinstance(out[col].dtype, pd.DatetimeTZDtype):
            out[col] = out[col].dt.tz_convert("UTC").dt.strftime(TS_FORMAT)
        elif out[col].dtype == bool:
            out[col] = out[col].astype(int)
    return out.astype(object).where(out.notna(), None)


def upsert(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    rows = _to_db(df)
    cols = ", ".join(rows.columns)
    placeholders = ", ".join("?" * len(rows.columns))
    with conn:
        conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})",
            rows.itertuples(index=False, name=None),
        )
    return len(rows)


def replace_all(conn: sqlite3.Connection, table: str, df: pd.DataFrame) -> int:
    with conn:
        conn.execute(f"DELETE FROM {table}")
    return upsert(conn, table, df)


def read_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    if "timestamp_utc" in df.columns:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True)
    return df


def compact(conn: sqlite3.Connection) -> None:
    """Reclaim free pages so the committed database file stays small."""
    conn.execute("VACUUM")


def last_actual_weather_hour(conn: sqlite3.Connection) -> pd.Timestamp | None:
    value = conn.execute("SELECT MAX(timestamp_utc) FROM weather_hourly WHERE is_forecast = 0").fetchone()[0]
    return pd.Timestamp(value, tz="UTC") if value else None

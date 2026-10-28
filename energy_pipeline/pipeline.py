"""Orchestrate one pipeline run: extract -> validate -> store -> simulate -> analyze -> export."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from . import store
from .analyze import analyze
from .config import Config
from .export import export_powerbi
from .extract import extract_weather
from .simulate import simulate_consumption
from .validate import PASS, WARN, validate_energy, validate_weather

log = logging.getLogger(__name__)


def run(cfg: Config, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    now_hour = pd.Timestamp(now).floor("h")
    now_text = now.strftime(store.TS_FORMAT)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    started = time.perf_counter()
    building_ids = [b.building_id for b in cfg.buildings]

    conn = store.connect(cfg.database)
    store.upsert(conn, "pipeline_runs", pd.DataFrame([{
        "run_id": run_id, "started_at_utc": now_text, "status": "running",
    }]))
    summary = {"run_id": run_id, "status": "failed"}

    try:
        # 1. Extract
        last_actual = store.last_actual_weather_hour(conn)
        log.info("Latest stored actual hour: %s", last_actual or "none (first run, backfilling)")
        raw_weather = extract_weather(cfg, last_actual, now)

        # 2. Validate + load weather
        weather, checks = validate_weather(raw_weather, now_hour)
        weather["ingested_at_utc"] = now_text
        summary["weather_rows_fetched"] = len(raw_weather)
        summary["weather_rows_loaded"] = store.upsert(conn, "weather_hourly", weather)

        # 3. Simulate consumption for new (and recently revised) actual hours
        all_weather = store.read_table(conn, "weather_hourly")
        actual = all_weather[all_weather["is_forecast"] == 0]
        if last_actual is not None:
            actual = actual[actual["timestamp_utc"] > last_actual - pd.Timedelta(days=cfg.past_days)]
        energy, energy_checks = validate_energy(
            simulate_consumption(actual, cfg.buildings, cfg.timezone), building_ids
        )
        checks += energy_checks
        summary["energy_rows_loaded"] = store.upsert(conn, "energy_hourly", energy)

        # 4. Analyze
        result = analyze(
            store.read_table(conn, "energy_hourly"), all_weather, building_ids,
            cfg.timezone, cfg.test_days, run_id, now_text,
        )
        store.replace_all(conn, "energy_model_daily", result.daily)
        store.replace_all(conn, "energy_forecast", result.forecast)
        store.replace_all(conn, "energy_anomalies", result.anomalies)
        store.upsert(conn, "model_metrics", result.metrics)

        store.upsert(conn, "data_quality_checks", pd.DataFrame(
            [{"run_id": run_id, **vars(c)} for c in checks]
        ))
        summary["checks_passed"] = sum(c.status == PASS for c in checks)
        summary["checks_warned"] = sum(c.status == WARN for c in checks)
        summary["status"] = "success"
        summary["message"] = "ok"
    except Exception as exc:
        summary["message"] = f"{type(exc).__name__}: {exc}"
        log.exception("Pipeline run failed")
        raise
    finally:
        summary["finished_at_utc"] = datetime.now(timezone.utc).strftime(store.TS_FORMAT)
        summary["duration_seconds"] = round(time.perf_counter() - started, 2)
        store.upsert(conn, "pipeline_runs", pd.DataFrame([{"started_at_utc": now_text, **summary}]))
        # Export even after a failure, so the dashboard's run log shows it.
        export_powerbi(conn, cfg)
        store.compact(conn)
        conn.close()

    log.info("Run %s finished: %s", run_id, summary)
    return summary

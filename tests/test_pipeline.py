"""End-to-end test: two pipeline runs with the API replaced by synthetic data."""

from datetime import datetime, timezone

import pandas as pd

from energy_pipeline import extract, pipeline, store


def test_two_runs_end_to_end(cfg, weather_factory, monkeypatch):
    def fake_archive(c, start, end):
        hours = int((pd.Timestamp(end) - pd.Timestamp(start)).days + 1) * 24
        return weather_factory(str(start), hours).drop(columns="is_forecast")

    def fake_recent(c):
        return weather_factory(str(fake_recent.window_start), 24 * 14).drop(columns="is_forecast")

    monkeypatch.setattr(extract, "fetch_archive", fake_archive)
    monkeypatch.setattr(extract, "fetch_recent_and_forecast", fake_recent)

    fake_recent.window_start = "2025-05-24"
    first = pipeline.run(cfg, now=datetime(2025, 5, 31, 3, tzinfo=timezone.utc))
    fake_recent.window_start = "2025-05-25"
    second = pipeline.run(cfg, now=datetime(2025, 6, 1, 3, tzinfo=timezone.utc))

    assert first["status"] == second["status"] == "success"
    assert second["energy_rows_loaded"] < first["energy_rows_loaded"]  # incremental load

    conn = store.connect(cfg.database)
    runs = pd.read_sql_query("SELECT * FROM pipeline_runs", conn)
    assert len(runs) == 2 and (runs["status"] == "success").all()

    for name in ["dim_date", "dim_building", "fact_energy_hourly", "fact_energy_daily_model",
                 "fact_energy_forecast", "fact_anomalies", "fact_weather_hourly",
                 "model_metrics", "pipeline_runs", "data_quality_checks"]:
        assert (cfg.export_dir / f"{name}.csv").exists(), name

    energy = pd.read_csv(cfg.export_dir / "fact_energy_hourly.csv")
    dates = pd.read_csv(cfg.export_dir / "dim_date.csv")["date"]
    assert energy.duplicated(["timestamp_utc", "building_id"]).sum() == 0
    assert energy["date"].isin(dates).all()
    assert energy["is_detected_anomaly"].sum() > 0
    assert len(pd.read_csv(cfg.export_dir / "fact_energy_forecast.csv")) > 0
    assert pd.read_csv(cfg.export_dir / "fact_energy_daily_model.csv")["date"].isin(dates).all()

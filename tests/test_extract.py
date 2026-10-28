from datetime import datetime, timezone

import pandas as pd

from energy_pipeline import extract


def test_parse_hourly_builds_utc_table(cfg):
    payload = {"hourly": {
        "time": ["2026-10-27T00:00", "2026-10-27T01:00"],
        "temperature_2m": [24.1, None],
        "relative_humidity_2m": [50, 55],
    }}
    df = extract.parse_hourly(payload, ("temperature_2m", "relative_humidity_2m", "cloud_cover"))

    assert str(df["timestamp_utc"].dt.tz) == "UTC"
    assert df["temperature_2m"].isna().tolist() == [False, True]
    assert df["cloud_cover"].isna().all()  # missing variable -> empty column, not a crash


def _fake_frame(start, end):
    ts = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({"timestamp_utc": ts, "temperature_2m": 25.0})


def test_first_run_backfills_from_archive(cfg, monkeypatch):
    now = datetime(2026, 10, 28, 4, 30, tzinfo=timezone.utc)
    calls = []
    monkeypatch.setattr(extract, "fetch_archive",
                        lambda c, s, e: calls.append((s, e)) or _fake_frame(str(s), f"{e} 23:00"))
    monkeypatch.setattr(extract, "fetch_recent_and_forecast",
                        lambda c: _fake_frame("2026-10-21", "2026-11-04 23:00"))

    df = extract.extract_weather(cfg, last_actual=None, now=now)

    assert calls and calls[0][0] == cfg.backfill_start
    assert df["timestamp_utc"].is_unique
    assert not df.loc[df["timestamp_utc"] < "2026-10-28 04:00Z", "is_forecast"].any()
    assert df.loc[df["timestamp_utc"] >= "2026-10-28 04:00Z", "is_forecast"].all()
    # Overlapping hours come from the fresher forecast endpoint.
    assert (df.loc[df["timestamp_utc"] >= "2026-10-21", "source"] == "forecast_api").all()


def test_daily_run_skips_archive(cfg, monkeypatch):
    now = datetime(2026, 10, 28, 4, tzinfo=timezone.utc)
    monkeypatch.setattr(extract, "fetch_archive", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    monkeypatch.setattr(extract, "fetch_recent_and_forecast",
                        lambda c: _fake_frame("2026-10-21", "2026-11-04 23:00"))

    df = extract.extract_weather(cfg, last_actual=pd.Timestamp("2026-10-27 03:00", tz="UTC"), now=now)
    assert len(df) > 0

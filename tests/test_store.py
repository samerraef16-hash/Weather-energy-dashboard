import pandas as pd

from energy_pipeline import store


def _weather_row(ts, temp, is_forecast):
    return pd.DataFrame([{
        "timestamp_utc": pd.Timestamp(ts, tz="UTC"), "temperature_2m": temp,
        "is_forecast": is_forecast, "source": "test", "ingested_at_utc": "2025-01-01 00:00:00",
    }])


def test_upsert_is_idempotent(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    row = _weather_row("2025-01-01 00:00", 20.0, False)
    store.upsert(conn, "weather_hourly", row)
    store.upsert(conn, "weather_hourly", row)
    assert conn.execute("SELECT COUNT(*) FROM weather_hourly").fetchone()[0] == 1


def test_actual_replaces_forecast_for_same_hour(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert(conn, "weather_hourly", _weather_row("2025-01-01 12:00", 30.0, True))
    assert store.last_actual_weather_hour(conn) is None

    store.upsert(conn, "weather_hourly", _weather_row("2025-01-01 12:00", 28.5, False))
    df = store.read_table(conn, "weather_hourly")
    assert df["temperature_2m"].tolist() == [28.5]
    assert store.last_actual_weather_hour(conn) == pd.Timestamp("2025-01-01 12:00", tz="UTC")

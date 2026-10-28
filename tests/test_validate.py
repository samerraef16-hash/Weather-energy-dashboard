import pandas as pd
import pytest

from energy_pipeline.validate import DataQualityError, validate_energy, validate_weather

NOW = pd.Timestamp("2025-01-03 00:00", tz="UTC")


def _by_name(results):
    return {r.check_name: r for r in results}


def test_clean_weather_passes(weather_factory):
    clean, results = validate_weather(weather_factory("2025-01-01", 72, now=NOW), NOW)
    assert len(clean) == 72
    assert all(r.status == "pass" for r in results), [r for r in results if r.status != "pass"]


def test_impossible_values_are_quarantined(weather_factory):
    df = weather_factory("2025-01-01", 72, now=NOW)
    df.loc[5, "temperature_2m"] = 80
    df.loc[6, "relative_humidity_2m"] = 140
    clean, results = validate_weather(df, NOW)
    checks = _by_name(results)

    assert len(clean) == 70
    assert checks["range_temperature_2m"].status == "warn"
    assert checks["quarantined_rows"].rows_affected == 2
    assert checks["hourly_continuity"].rows_affected == 2


def test_duplicate_hours_stop_the_run(weather_factory):
    df = weather_factory("2025-01-01", 24, now=NOW)
    with pytest.raises(DataQualityError):
        validate_weather(pd.concat([df, df.iloc[[0]]]), NOW)


def test_missing_column_stops_the_run(weather_factory):
    df = weather_factory("2025-01-01", 24, now=NOW).drop(columns="cloud_cover")
    with pytest.raises(DataQualityError):
        validate_weather(df, NOW)


def test_stale_data_is_flagged(weather_factory):
    df = weather_factory("2025-01-01", 24)  # all actuals, ends 2 days before "now"
    _, results = validate_weather(df, pd.Timestamp("2025-01-05", tz="UTC"))
    assert _by_name(results)["freshness"].status == "warn"


def test_negative_energy_is_quarantined():
    df = pd.DataFrame({
        "timestamp_utc": pd.date_range("2025-01-01", periods=3, freq="h", tz="UTC"),
        "building_id": "A", "energy_kwh": [10, -1, 12], "hvac_kwh": [1, 1, 1], "base_kwh": [9, 1, 11],
    })
    clean, results = validate_energy(df, ["A", "B"])
    checks = _by_name(results)
    assert len(clean) == 2
    assert checks["non_negative_kwh"].status == "warn"
    assert checks["all_buildings_present"].status == "warn"

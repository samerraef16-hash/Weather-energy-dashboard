"""Validate: data-quality checks run before anything is stored.

Two severities:
  * structural problems (missing columns, duplicate keys) raise
    DataQualityError and stop the run, so bad data never reaches storage;
  * row-level problems (an impossible temperature) quarantine the offending
    rows and record a warning, so one bad reading doesn't block the update.

Every check is recorded, and the results are exported to Power BI as a
data-quality report.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PASS, WARN, FAIL = "pass", "warn", "fail"

# Physically plausible ranges for El Gouna-style climates (min, max).
WEATHER_RANGES = {
    "temperature_2m": (-10, 55),
    "apparent_temperature": (-20, 65),
    "relative_humidity_2m": (0, 100),
    "cloud_cover": (0, 100),
    "wind_speed_10m": (0, 200),
    "shortwave_radiation": (0, 1400),
    "precipitation": (0, 300),
}


class DataQualityError(Exception):
    pass


@dataclass
class CheckResult:
    dataset: str
    check_name: str
    status: str
    rows_affected: int
    detail: str


def _check_columns(df: pd.DataFrame, required: list[str], dataset: str) -> CheckResult:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataQualityError(f"{dataset}: missing columns {missing}")
    return CheckResult(dataset, "required_columns", PASS, 0, f"{len(required)} columns present")


def _check_unique(df: pd.DataFrame, keys: list[str], dataset: str) -> CheckResult:
    if df[keys].isna().any().any():
        raise DataQualityError(f"{dataset}: null values in key columns {keys}")
    dupes = int(df.duplicated(keys).sum())
    if dupes:
        raise DataQualityError(f"{dataset}: {dupes} duplicate rows on {keys}")
    return CheckResult(dataset, "unique_key", PASS, 0, f"one row per {' + '.join(keys)}")


def validate_weather(df: pd.DataFrame, now_hour: pd.Timestamp) -> tuple[pd.DataFrame, list[CheckResult]]:
    ds = "weather"
    results = [
        _check_columns(df, ["timestamp_utc", "is_forecast", *WEATHER_RANGES], ds),
        _check_unique(df, ["timestamp_utc"], ds),
    ]

    bad = pd.Series(False, index=df.index)
    for col, (lo, hi) in WEATHER_RANGES.items():
        out_of_range = df[col].notna() & ~df[col].between(lo, hi)
        bad |= out_of_range
        results.append(CheckResult(
            ds, f"range_{col}", WARN if out_of_range.any() else PASS,
            int(out_of_range.sum()), f"expected {lo} to {hi}",
        ))

    missing_temp = df["temperature_2m"].isna()
    bad |= missing_temp
    results.append(CheckResult(
        ds, "temperature_not_null", WARN if missing_temp.any() else PASS,
        int(missing_temp.sum()), "rows without temperature are quarantined",
    ))

    clean = df[~bad].copy()

    expected = pd.date_range(clean["timestamp_utc"].min(), clean["timestamp_utc"].max(), freq="h")
    gaps = len(expected) - len(clean)
    results.append(CheckResult(
        ds, "hourly_continuity", WARN if gaps else PASS, gaps, f"{gaps} missing hours in fetched window",
    ))

    actual = clean.loc[~clean["is_forecast"], "timestamp_utc"]
    lag_hours = (now_hour - actual.max()) / pd.Timedelta(hours=1) if len(actual) else float("inf")
    results.append(CheckResult(
        ds, "freshness", PASS if lag_hours <= 48 else WARN, 0, f"latest actual hour is {lag_hours:.0f}h old",
    ))

    forecast_hours = int(clean["is_forecast"].sum())
    results.append(CheckResult(
        ds, "forecast_available", PASS if forecast_hours >= 24 else WARN, forecast_hours,
        f"{forecast_hours} forecast hours",
    ))

    if bad.any():
        results.append(CheckResult(ds, "quarantined_rows", WARN, int(bad.sum()), "rows excluded from load"))
    return clean, results


def validate_energy(df: pd.DataFrame, building_ids: list[str]) -> tuple[pd.DataFrame, list[CheckResult]]:
    ds = "energy"
    results = [
        _check_columns(df, ["timestamp_utc", "building_id", "energy_kwh", "hvac_kwh", "base_kwh"], ds),
        _check_unique(df, ["timestamp_utc", "building_id"], ds),
    ]

    negative = (df[["energy_kwh", "hvac_kwh", "base_kwh"]] < 0).any(axis=1)
    results.append(CheckResult(
        ds, "non_negative_kwh", WARN if negative.any() else PASS, int(negative.sum()), "kWh must be >= 0",
    ))

    missing = sorted(set(building_ids) - set(df["building_id"]))
    results.append(CheckResult(
        ds, "all_buildings_present", WARN if missing else PASS, len(missing),
        f"missing: {missing}" if missing else f"{len(building_ids)} buildings",
    ))
    return df[~negative].copy(), results

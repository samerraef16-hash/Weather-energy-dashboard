from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from energy_pipeline.config import load_config


@pytest.fixture
def cfg(tmp_path):
    """Real config, but writing to a temporary folder."""
    return replace(
        load_config(),
        database=tmp_path / "warehouse.db",
        export_dir=tmp_path / "powerbi",
        backfill_start=pd.Timestamp("2025-01-01").date(),
    )


def make_weather(start: str, hours: int, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Synthetic but realistic El Gouna weather: seasonal + daily temperature cycle."""
    ts = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    day_of_year = ts.dayofyear.to_numpy()
    hour_local = (ts.hour.to_numpy() + 2) % 24
    seasonal = 24 - 7 * np.cos(2 * np.pi * (day_of_year - 15) / 365)
    diurnal = 5 * np.sin(2 * np.pi * (hour_local - 9) / 24)
    temp = seasonal + diurnal
    sun = np.clip(np.sin(np.pi * (hour_local - 6) / 12), 0, None) * 850
    df = pd.DataFrame({
        "timestamp_utc": ts,
        "temperature_2m": temp.round(1),
        "relative_humidity_2m": 45.0,
        "apparent_temperature": (temp + 1).round(1),
        "cloud_cover": 10.0,
        "wind_speed_10m": 18.0,
        "shortwave_radiation": sun.round(0),
        "precipitation": 0.0,
    })
    df["is_forecast"] = False if now is None else df["timestamp_utc"] >= now
    return df


@pytest.fixture
def weather_factory():
    return make_weather

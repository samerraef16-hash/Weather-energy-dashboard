"""Load config.toml into typed objects."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Building:
    building_id: str
    name: str
    building_type: str
    floor_area_m2: float
    base_load_kw: float
    peak_occupied_kw: float
    cooling_kw_per_degree: float
    cooling_balance_c: float
    heating_kw_per_degree: float
    heating_balance_c: float
    solar_kw_per_kw_m2: float


@dataclass(frozen=True)
class Config:
    location_name: str
    latitude: float
    longitude: float
    timezone: str
    backfill_start: date
    past_days: int
    forecast_days: int
    archive_lag_days: int
    test_days: int
    currency: str
    price_per_kwh: float
    grid_kg_co2_per_kwh: float
    database: Path
    export_dir: Path
    forecast_url: str
    archive_url: str
    timeout_seconds: int
    max_retries: int
    hourly_variables: tuple[str, ...]
    buildings: tuple[Building, ...]


def load_config(path: Path | None = None) -> Config:
    path = path or PROJECT_ROOT / "config.toml"
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    loc, pipe, econ = raw["location"], raw["pipeline"], raw["economics"]
    paths, api = raw["paths"], raw["api"]
    return Config(
        location_name=loc["name"],
        latitude=loc["latitude"],
        longitude=loc["longitude"],
        timezone=loc["timezone"],
        backfill_start=date.fromisoformat(pipe["backfill_start"]),
        past_days=pipe["past_days"],
        forecast_days=pipe["forecast_days"],
        archive_lag_days=pipe["archive_lag_days"],
        test_days=pipe["test_days"],
        currency=econ["currency"],
        price_per_kwh=econ["price_per_kwh"],
        grid_kg_co2_per_kwh=econ["grid_kg_co2_per_kwh"],
        database=PROJECT_ROOT / paths["database"],
        export_dir=PROJECT_ROOT / paths["export_dir"],
        forecast_url=api["forecast_url"],
        archive_url=api["archive_url"],
        timeout_seconds=api["timeout_seconds"],
        max_retries=api["max_retries"],
        hourly_variables=tuple(api["hourly_variables"]),
        buildings=tuple(Building(**b) for b in raw["buildings"]),
    )

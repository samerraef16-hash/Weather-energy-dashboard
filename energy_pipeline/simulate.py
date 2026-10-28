"""Simulate hourly electricity consumption for each building.

Real smart-meter data is not freely available, so consumption is generated
from the weather with a simple physical model:

    load = base load
         + occupancy-driven load (lights, equipment, people)
         + cooling load  (degrees above a balance point, scaled by occupancy)
         + heating load  (degrees below a balance point)
         + solar gain    (sunshine heating the building envelope)
         +/- random noise, plus rare injected faults

The randomness is *deterministic*: each (building, hour) pair always gets the
same noise, so re-running the pipeline never rewrites history.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Building

NOISE_STD = 0.04
ANOMALY_PROBABILITY = 0.0015

# Resort occupancy by month: winter sun season and summer holidays are busy.
HOTEL_MONTHLY_OCCUPANCY = {
    1: 0.85, 2: 0.85, 3: 0.80, 4: 0.75, 5: 0.60, 6: 0.55,
    7: 0.70, 8: 0.75, 9: 0.60, 10: 0.75, 11: 0.85, 12: 0.90,
}
HOTEL_HOURLY_ACTIVITY = np.array([
    0.55, 0.50, 0.50, 0.50, 0.50, 0.55, 0.70, 0.90, 0.90, 0.80, 0.75, 0.75,
    0.80, 0.80, 0.75, 0.75, 0.80, 0.90, 1.00, 1.00, 1.00, 0.95, 0.80, 0.65,
])
EGYPT_WORKDAYS = {6, 0, 1, 2, 3}  # Sunday-Thursday (pandas: Monday=0)


def _uniform(keys: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic pseudo-random numbers in (0, 1), one per key."""
    hashed = pd.util.hash_array(keys.astype(np.uint64) * np.uint64(31) + np.uint64(salt))
    return np.clip((hashed >> np.uint64(11)).astype(np.float64) / 2.0**53, 1e-12, 1 - 1e-12)


def _normal(keys: np.ndarray, salt: int) -> np.ndarray:
    """Deterministic standard-normal noise via the Box-Muller transform."""
    u1, u2 = _uniform(keys, salt), _uniform(keys, salt + 1)
    return np.sqrt(-2 * np.log(u1)) * np.cos(2 * np.pi * u2)


def occupancy(building_type: str, local: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Return (occupancy 0-1, share of cooling/heating load active) per hour."""
    hour = local.dt.hour.to_numpy()
    dow = local.dt.dayofweek.to_numpy()
    month = local.dt.month.to_numpy()

    if building_type == "Hotel":
        occ = np.vectorize(HOTEL_MONTHLY_OCCUPANCY.get)(month) * HOTEL_HOURLY_ACTIVITY[hour]
        hvac_share = 0.6 + 0.4 * occ
    elif building_type == "Office":
        workday = np.isin(dow, list(EGYPT_WORKDAYS))
        occ = np.where(workday & (hour >= 8) & (hour < 17), 1.0, 0.05)
        occ = np.where(workday & np.isin(hour, [7, 17]), 0.5, occ)
        hvac_share = 0.3 + 0.7 * occ
    elif building_type == "Retail":
        open_hours = (hour >= 10) & (hour < 23)
        busy_evening = np.isin(dow, [3, 4]) & (hour >= 17)  # Thursday & Friday nights
        occ = np.where(open_hours, np.where(busy_evening, 1.0, 0.8), 0.08)
        hvac_share = 0.35 + 0.65 * occ
    else:
        raise ValueError(f"Unknown building type: {building_type}")
    return occ, hvac_share


def simulate_building(weather: pd.DataFrame, building: Building, building_index: int, tz: str) -> pd.DataFrame:
    local = weather["timestamp_utc"].dt.tz_convert(tz)
    temp = weather["temperature_2m"].to_numpy()
    radiation_kw_m2 = weather["shortwave_radiation"].fillna(0).to_numpy() / 1000

    occ, hvac_share = occupancy(building.building_type, local)
    cooling = building.cooling_kw_per_degree * np.maximum(0, temp - building.cooling_balance_c)
    heating = building.heating_kw_per_degree * np.maximum(0, building.heating_balance_c - temp)
    hvac = hvac_share * (cooling + heating) + building.solar_kw_per_kw_m2 * radiation_kw_m2
    base = building.base_load_kw + building.peak_occupied_kw * occ

    epoch_hours = (weather["timestamp_utc"] - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(hours=1)
    keys = epoch_hours.to_numpy(dtype=np.int64) * 16 + building_index
    noise = 1 + NOISE_STD * _normal(keys, salt=1)
    is_anomaly = _uniform(keys, salt=7) < ANOMALY_PROBABILITY
    fault = np.where(is_anomaly, 1.5 + 0.5 * _uniform(keys, salt=9), 1.0)

    total = (base + hvac) * noise * fault
    hvac_kwh = hvac * noise
    return pd.DataFrame({
        "timestamp_utc": weather["timestamp_utc"].reset_index(drop=True),
        "building_id": building.building_id,
        "energy_kwh": total.round(2),
        "hvac_kwh": hvac_kwh.round(2),
        "base_kwh": (total - hvac_kwh).round(2),
        "occupancy_factor": occ.round(3),
        "is_injected_anomaly": is_anomaly,
    })


def simulate_consumption(weather: pd.DataFrame, buildings: tuple[Building, ...], tz: str) -> pd.DataFrame:
    """Simulate consumption for every building over the given (actual) weather hours."""
    frames = [simulate_building(weather, b, i, tz) for i, b in enumerate(buildings)]
    return pd.concat(frames, ignore_index=True)

import pandas as pd

from energy_pipeline.simulate import simulate_consumption


def test_simulation_is_deterministic(cfg, weather_factory):
    weather = weather_factory("2025-07-01", 24 * 14)
    first = simulate_consumption(weather, cfg.buildings, cfg.timezone)
    # Simulating a sub-window must reproduce exactly the same values.
    second = simulate_consumption(weather.iloc[100:200], cfg.buildings, cfg.timezone)

    merged = second.merge(first, on=["timestamp_utc", "building_id"], suffixes=("", "_full"))
    assert len(merged) == len(second)
    assert (merged["energy_kwh"] == merged["energy_kwh_full"]).all()


def test_loads_are_positive_and_components_add_up(cfg, weather_factory):
    energy = simulate_consumption(weather_factory("2025-01-01", 24 * 60), cfg.buildings, cfg.timezone)
    assert (energy["energy_kwh"] > 0).all()
    assert ((energy["hvac_kwh"] + energy["base_kwh"] - energy["energy_kwh"]).abs() < 0.02).all()


def test_hot_weather_raises_consumption(cfg, weather_factory):
    weather = weather_factory("2025-07-01", 24 * 7)
    hot = weather.assign(temperature_2m=weather["temperature_2m"] + 5)
    normal = simulate_consumption(weather, cfg.buildings, cfg.timezone)["energy_kwh"].sum()
    hotter = simulate_consumption(hot, cfg.buildings, cfg.timezone)["energy_kwh"].sum()
    assert hotter > normal * 1.05


def test_office_uses_less_on_egyptian_weekend(cfg, weather_factory):
    energy = simulate_consumption(weather_factory("2025-03-02", 24 * 28), cfg.buildings, cfg.timezone)
    office = energy[energy["building_id"] == "GOU-OFF"].copy()
    local = office["timestamp_utc"].dt.tz_convert(cfg.timezone)
    office["weekend"] = local.dt.dayofweek.isin([4, 5])  # Friday, Saturday
    daily = office.groupby([local.dt.date, "weekend"])["energy_kwh"].sum().reset_index()
    means = daily.groupby("weekend")["energy_kwh"].mean()
    assert means[True] < means[False] * 0.7

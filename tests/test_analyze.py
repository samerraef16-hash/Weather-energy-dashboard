import numpy as np

from energy_pipeline.analyze import analyze, detect_anomalies
from energy_pipeline.simulate import simulate_consumption


def test_model_is_accurate_on_simulated_data(cfg, weather_factory):
    weather = weather_factory("2025-01-01", 24 * 200)
    energy = simulate_consumption(weather, cfg.buildings, cfg.timezone)
    ids = [b.building_id for b in cfg.buildings]

    result = analyze(energy, weather, ids, cfg.timezone, test_days=30, run_id="t", trained_at="t")
    metrics = result.metrics

    assert set(metrics["building_id"]) == set(ids)
    assert (metrics["r2"] > 0.85).all(), metrics[["building_id", "r2"]]
    # Office and mall nights have small loads, so percentage errors run higher there.
    assert (metrics["mape_pct"] < 15).all()
    # Hotter weather costs energy: every building has a positive cooling sensitivity.
    assert (metrics["kwh_per_cooling_degree"] > 0).all()
    # Daily totals cover every complete building-day and roughly balance out.
    assert result.daily.groupby("building_id").size().min() >= 198
    totals = result.daily[["actual_kwh", "predicted_kwh"]].sum()
    assert abs(totals["actual_kwh"] / totals["predicted_kwh"] - 1) < 0.02


def test_injected_faults_are_detected(cfg, weather_factory):
    weather = weather_factory("2025-01-01", 24 * 365)
    energy = simulate_consumption(weather, cfg.buildings, cfg.timezone)
    result = analyze(energy, weather, ["GOU-HTL"], cfg.timezone, 30, "t", "t")

    m = result.metrics.iloc[0]
    assert m["anomaly_recall_pct"] >= 80
    # Few false alarms: roughly as many flags as injected faults.
    assert m["anomalies_detected"] <= 2 * energy.query("building_id == 'GOU-HTL'")["is_injected_anomaly"].sum()
    assert (result.anomalies["excess_kwh"] > 0).all()


def test_forecast_hours_get_predictions(cfg, weather_factory):
    weather = weather_factory("2025-01-01", 24 * 120)
    weather.loc[weather.index[-24 * 7:], "is_forecast"] = True
    actual = weather[~weather["is_forecast"]]
    energy = simulate_consumption(actual, cfg.buildings, cfg.timezone)

    forecast = analyze(energy, weather, ["GOU-HTL"], cfg.timezone, 30, "t", "t").forecast
    assert len(forecast) == 24 * 7
    assert (forecast["predicted_kwh"] > 0).all()


def test_detect_anomalies_flags_spikes_only():
    rng = np.random.default_rng(0)
    predicted = np.full(1000, 100.0)
    actual = predicted + rng.normal(0, 3, 1000)
    actual[[10, 500]] *= 1.8
    actual[700] *= 0.3  # a drop is not flagged as a consumption spike
    flagged = detect_anomalies(actual, predicted)
    assert set(np.flatnonzero(flagged)) == {10, 500}

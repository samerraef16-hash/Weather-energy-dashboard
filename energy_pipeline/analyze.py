"""Analyze: a weather-normalised consumption model and anomaly detection.

For each building we fit a time-of-week-and-temperature regression (the
approach behind LBNL's TOWT model and ASHRAE Guideline 14 baselines):

    kWh = baseline[hour of week] + month effect
        + cooling_sensitivity[hour of week] * cooling degrees
        + b1 * heating degrees + b2 * solar radiation

Each of the 168 hours of the week gets its own baseline and its own cooling
response, so the model learns that an office only cools during working
hours and that the mall is busiest on Thursday and Friday nights.

Cooling/heating degrees are measured from balance-point temperatures that
are *learned* by trying a grid of candidates and keeping the best fit.

The model is evaluated on the most recent `test_days` (never seen during
training), then refit on all history to:
  * predict consumption for the forecast hours (next 7 days);
  * flag hours whose actual use is far above the prediction (anomalies).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

COOLING_CANDIDATES = range(20, 28)
HEATING_CANDIDATES = (14, 16, 18)
ANOMALY_Z = 3.5
HOURS_PER_WEEK = 168
N_MONTH_DUMMIES = 11


@dataclass
class FittedModel:
    coef: np.ndarray
    cooling_balance: int
    heating_balance: int


def hour_of_week(df: pd.DataFrame, tz: str) -> np.ndarray:
    local = df["timestamp_utc"].dt.tz_convert(tz)
    return (local.dt.dayofweek * 24 + local.dt.hour).to_numpy()


@dataclass
class _Inputs:
    """Feature parts that don't depend on the balance points (computed once)."""
    week_dummies: np.ndarray
    month_dummies: np.ndarray
    temp: np.ndarray
    radiation: np.ndarray


def _inputs(df: pd.DataFrame, tz: str) -> _Inputs:
    slot = hour_of_week(df, tz)
    month = df["timestamp_utc"].dt.tz_convert(tz).dt.month.to_numpy()
    week_dummies = np.zeros((len(df), HOURS_PER_WEEK))
    week_dummies[np.arange(len(df)), slot] = 1
    return _Inputs(
        week_dummies=week_dummies,
        month_dummies=(month[:, None] == np.arange(2, 13)[None, :]).astype(float),
        temp=df["temperature_2m"].to_numpy(),
        radiation=df["shortwave_radiation"].fillna(0).to_numpy() / 1000,
    )


def _features(inp: _Inputs, cooling_balance: int, heating_balance: int) -> np.ndarray:
    """Columns: 168 baselines | 11 months | 168 cooling slopes | heating | radiation."""
    cooling = np.maximum(0, inp.temp - cooling_balance)
    heating = np.maximum(0, heating_balance - inp.temp)
    return np.column_stack([inp.week_dummies, inp.month_dummies,
                            inp.week_dummies * cooling[:, None], heating, inp.radiation])


def _fit(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Least squares via the normal equations. The tiny ridge term keeps the
    system solvable when a column is all zeros (e.g. no cooling at 3 a.m.)."""
    xtx = X.T @ X
    xtx[np.diag_indices_from(xtx)] += 1e-6
    return np.linalg.solve(xtx, X.T @ y)


def fit_model(df: pd.DataFrame, tz: str) -> FittedModel:
    """Fit the regression, choosing the balance points that minimise squared error."""
    inp, y = _inputs(df, tz), df["energy_kwh"].to_numpy()
    best = None
    for cb in COOLING_CANDIDATES:
        for hb in HEATING_CANDIDATES:
            X = _features(inp, cb, hb)
            coef = _fit(X, y)
            sse = float(np.sum((y - X @ coef) ** 2))
            if best is None or sse < best[0]:
                best = (sse, FittedModel(coef, cb, hb))
    return best[1]


def predict(model: FittedModel, df: pd.DataFrame, tz: str) -> np.ndarray:
    X = _features(_inputs(df, tz), model.cooling_balance, model.heating_balance)
    return np.maximum(0, X @ model.coef)


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    err = actual - predicted
    ss_tot = np.sum((actual - actual.mean()) ** 2)
    return {
        "mae_kwh": float(np.mean(np.abs(err))),
        "mape_pct": float(np.mean(np.abs(err) / np.maximum(actual, 1e-9)) * 100),
        "r2": float(1 - np.sum(err**2) / ss_tot) if ss_tot else float("nan"),
    }


def detect_anomalies(actual: np.ndarray, predicted: np.ndarray) -> np.ndarray:
    """Flag hours far above the prediction using a robust (median/MAD) z-score.

    Residuals are relative (actual / predicted - 1): a 20 kWh miss matters
    at 3 a.m. in an empty office but not at noon in a full one.
    """
    resid = actual / np.maximum(predicted, 1e-9) - 1
    mad = np.median(np.abs(resid - np.median(resid))) or 1e-9
    robust_z = 0.6745 * (resid - np.median(resid)) / mad
    return robust_z > ANOMALY_Z


@dataclass
class AnalysisResult:
    daily: pd.DataFrame      # actual vs predicted kWh per local day
    forecast: pd.DataFrame   # predicted kWh for each forecast hour
    anomalies: pd.DataFrame  # hours flagged as abnormally high
    metrics: pd.DataFrame    # one row of model scores per building


def analyze(energy: pd.DataFrame, weather: pd.DataFrame, building_ids: list[str],
            tz: str, test_days: int, run_id: str, trained_at: str) -> AnalysisResult:
    actual_weather = weather[~weather["is_forecast"].astype(bool)]
    forecast_weather = weather[weather["is_forecast"].astype(bool)].reset_index(drop=True)
    daily, forecasts, anomalies, metrics = [], [], [], []

    for building_id in building_ids:
        hist = (energy[energy["building_id"] == building_id]
                .merge(actual_weather, on="timestamp_utc")
                .sort_values("timestamp_utc")
                .reset_index(drop=True))
        if len(hist) < 24 * 60:  # need ~2 months to learn seasonality sensibly
            continue

        split = hist["timestamp_utc"].max() - pd.Timedelta(days=test_days)
        train, test = hist[hist["timestamp_utc"] <= split], hist[hist["timestamp_utc"] > split]
        holdout = fit_model(train, tz)
        scores = regression_metrics(test["energy_kwh"].to_numpy(), predict(holdout, test, tz))

        model = fit_model(hist, tz)
        fitted = predict(model, hist, tz)
        flagged = detect_anomalies(hist["energy_kwh"].to_numpy(), fitted)
        injected = hist["is_injected_anomaly"].astype(bool).to_numpy()

        # Marginal kWh per extra degree, averaged over the hours when cooling is active.
        n = HOURS_PER_WEEK + N_MONTH_DUMMIES
        cooling_slopes = model.coef[n:n + HOURS_PER_WEEK]
        b_heat = model.coef[n + HOURS_PER_WEEK]
        cooling_active = (hist["temperature_2m"] > model.cooling_balance).to_numpy()
        slots = hour_of_week(hist, tz)[cooling_active]
        kwh_per_cooling_degree = float(cooling_slopes[slots].mean()) if len(slots) else 0.0

        metrics.append({
            "run_id": run_id,
            "building_id": building_id,
            "trained_at_utc": trained_at,
            "train_rows": len(train),
            "test_rows": len(test),
            **{k: round(v, 4) for k, v in scores.items()},
            "kwh_per_cooling_degree": round(kwh_per_cooling_degree, 3),
            "kwh_per_heating_degree": round(float(b_heat), 3),
            "anomalies_detected": int(flagged.sum()),
            "anomaly_recall_pct": round(float(flagged[injected].mean() * 100), 1) if injected.any() else None,
        })

        hist["predicted_kwh"] = fitted
        hist["date"] = hist["timestamp_utc"].dt.tz_convert(tz).dt.strftime("%Y-%m-%d")
        daily.append(
            hist.groupby("date", as_index=False)
            .agg(actual_kwh=("energy_kwh", "sum"), predicted_kwh=("predicted_kwh", "sum"))
            .round(1)
            .assign(building_id=building_id)
        )
        anomalies.append(pd.DataFrame({
            "timestamp_utc": hist.loc[flagged, "timestamp_utc"],
            "building_id": building_id,
            "actual_kwh": hist.loc[flagged, "energy_kwh"],
            "predicted_kwh": fitted[flagged].round(2),
            "excess_kwh": (hist.loc[flagged, "energy_kwh"] - fitted[flagged]).round(2),
        }))
        if len(forecast_weather):
            forecasts.append(pd.DataFrame({
                "timestamp_utc": forecast_weather["timestamp_utc"],
                "building_id": building_id,
                "predicted_kwh": predict(model, forecast_weather, tz).round(2),
            }))

    def concat(frames):
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    return AnalysisResult(concat(daily), concat(forecasts), concat(anomalies), pd.DataFrame(metrics))

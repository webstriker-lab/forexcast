"""Calibration test: proves summarize()'s output is structurally sound on
real EUR/USD history loaded from a committed fixture file. Runs with no
network access and no SUPABASE env vars.

Does NOT assert ES beats naive — that would violate ADR-0001 (the app
uses whichever model wins the backtest per pair/horizon). Only asserts
structural properties: enough samples, bands straddle zero, coverage ≥ 70%,
MAEs are positive floats, model_selected is a recognised string.
"""
import json
import pathlib

import pytest

from app.prediction.backtest import run_backtest, summarize

HORIZONS = [7, 30, 90, 365]


@pytest.fixture(scope="module")
def eurusd_rates() -> list[float]:
    path = pathlib.Path(__file__).parent / "fixtures" / "eurusd_rates.json"
    rows = json.loads(path.read_text())
    return [float(r["rate"]) for r in rows]


@pytest.fixture(scope="module")
def summaries(eurusd_rates) -> dict[int, dict]:
    results = run_backtest(eurusd_rates, horizons=HORIZONS)
    return {h: summarize(results[h]) for h in HORIZONS}


@pytest.mark.parametrize("horizon", HORIZONS)
def test_sample_count_is_sufficient(summaries, horizon):
    assert summaries[horizon]["sample_count"] >= 10, (
        f"horizon={horizon}d has only {summaries[horizon]['sample_count']} backtest origins — "
        "fixture may be too short"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_confidence_band_straddles_zero(summaries, horizon):
    s = summaries[horizon]
    assert s["error_lower_pct"] < 0, (
        f"horizon={horizon}d: error_lower_pct={s['error_lower_pct']} is not negative — "
        "confidence band doesn't reach below the point forecast"
    )
    assert s["error_upper_pct"] > 0, (
        f"horizon={horizon}d: error_upper_pct={s['error_upper_pct']} is not positive — "
        "confidence band doesn't reach above the point forecast"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_calibration_coverage_at_least_seventy_percent(summaries, horizon):
    cov = summaries[horizon]["calibration_coverage"]
    assert cov >= 0.70, (
        f"horizon={horizon}d: calibration_coverage={cov:.2%} < 70% — "
        "fewer actuals than expected fell inside the stated confidence band"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_mae_values_are_positive_floats(summaries, horizon):
    s = summaries[horizon]
    assert isinstance(s["es_mae"], float) and s["es_mae"] > 0, (
        f"horizon={horizon}d: es_mae={s['es_mae']} is not a positive float"
    )
    assert isinstance(s["naive_mae"], float) and s["naive_mae"] > 0, (
        f"horizon={horizon}d: naive_mae={s['naive_mae']} is not a positive float"
    )


@pytest.mark.parametrize("horizon", HORIZONS)
def test_model_selected_is_valid(summaries, horizon):
    ms = summaries[horizon]["model_selected"]
    assert ms in ("exponential_smoothing", "naive"), (
        f"horizon={horizon}d: model_selected={ms!r} is not a recognised value"
    )

"""Out-of-sample accuracy gate.

Loads the committed EUR/USD fixture (oldest to newest), runs the full
rolling-origin backtest, and asserts that ES beats the naive baseline
on the complete window. The fixture spans 2023-01-01 to present, so
origins in 2023-2024 are evaluated against 2024-2025 actuals -- a
genuine out-of-sample check. A failure means the model's edge has
vanished and must be investigated before the next release.
"""
import json
from pathlib import Path

import pytest

from app.prediction.backtest import run_backtest, summarize

FIXTURE = Path(__file__).parent / "fixtures" / "eurusd_rates.json"
HORIZONS = [7, 30, 90, 365]


def _load_rates() -> list[float]:
    rows = json.loads(FIXTURE.read_text())
    return [r["rate"] for r in rows]


@pytest.mark.parametrize("horizon", HORIZONS)
def test_es_beats_naive_on_eurusd_holdout(horizon: int):
    rates = _load_rates()
    results = run_backtest(rates, [horizon])
    assert horizon in results, f"No backtest results for horizon={horizon}"
    summary = summarize(results[horizon])
    improvement = summary.get("mae_improvement_pct")
    assert improvement is not None, "mae_improvement_pct is None -- not enough data"
    assert improvement > 0, (
        f"ES does NOT beat naive for EUR/USD {horizon}d: "
        f"es_mae={summary['es_mae']:.4f} naive_mae={summary['naive_mae']:.4f} "
        f"improvement={improvement:.2f}%"
    )

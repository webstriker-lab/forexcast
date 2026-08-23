#!/usr/bin/env python3
"""Holdout accuracy evaluator.

Loads EUR/USD rate history from Supabase (or the committed fixture as
fallback), splits at CUTOFF_DATE, runs the backtest on all data, and
prints a table of ES vs naive MAE for each horizon.

Usage (requires SUPABASE_URL + SUPABASE_SERVICE_KEY in environment):
    python backend/scripts/eval_holdout.py

For CI or local testing without DB access, the fixture at
backend/tests/fixtures/eurusd_rates.json is used automatically.
"""
import json
import os
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.prediction.backtest import run_backtest, summarize

CUTOFF_DATE = "2024-12-31"
HORIZONS = [7, 30, 90, 365]
FIXTURE = Path(__file__).parent.parent / "tests" / "fixtures" / "eurusd_rates.json"


def _load_from_supabase() -> list[dict]:
    """Fetches EUR/USD rate history from Supabase rates_cache."""
    import httpx

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    resp = httpx.get(
        f"{url}/rest/v1/rates_cache",
        params={
            "select": "as_of,rate",
            "base_code": "eq.USD",
            "quote_code": "eq.EUR",
            "order": "as_of.asc",
        },
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return [{"date": r["as_of"][:10], "rate": r["rate"]} for r in resp.json()]


def _load_rates() -> list[dict]:
    if os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_KEY"):
        print("Loading EUR/USD from Supabase...")
        return _load_from_supabase()
    print(f"SUPABASE_URL not set -- using committed fixture at {FIXTURE}")
    return json.loads(FIXTURE.read_text())


def main():
    rows = _load_rates()
    rates = [r["rate"] for r in rows]
    dates = [r["date"] for r in rows]

    cutoff_idx = max(
        (i for i, d in enumerate(dates) if d <= CUTOFF_DATE),
        default=-1,
    )
    if cutoff_idx < 0:
        print(f"No data on or before {CUTOFF_DATE}. Cannot split.")
        sys.exit(1)

    print(f"\nData range: {dates[0]} to {dates[-1]} ({len(rates)} rows)")
    print(f"Cutoff: {CUTOFF_DATE} (index {cutoff_idx} of {len(rates)-1})")
    print(f"Training rows: {cutoff_idx+1}, Test rows: {len(rates)-cutoff_idx-1}\n")

    results = run_backtest(rates, HORIZONS)

    header = f"{'Pair':<12}{'Horizon':>9}{'ES MAE':>10}{'Naive MAE':>12}{'Improvement':>14}{'Model':>10}"
    print(header)
    print("-" * len(header))

    for h in HORIZONS:
        if h not in results:
            print(f"  EUR/USD  {h:>6}d  -- not enough data --")
            continue
        s = summarize(results[h])
        es = s["es_mae"]
        naive = s["naive_mae"]
        imp = s["mae_improvement_pct"]
        model = s["model_selected"]
        imp_str = f"+{imp:.1f}%" if imp and imp > 0 else (f"{imp:.1f}%" if imp else "N/A")
        print(f"  EUR/USD  {h:>6}d  {es*100:>8.3f}%  {naive*100:>10.3f}%  {imp_str:>12}  {model:>10}")

    print()


if __name__ == "__main__":
    main()

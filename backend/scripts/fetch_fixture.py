"""One-off script: fetch ~3 years of USD/EUR daily rates from Frankfurter
and write them to backend/tests/fixtures/eurusd_rates.json.
Run once from the repo root: python backend/scripts/fetch_fixture.py

Date range starts 2023-01-01 to give the 365-day horizon enough backtest
origins for a stable calibration_coverage measurement.
"""
import json
import pathlib

import httpx

URL = "https://api.frankfurter.dev/v1/2023-01-01..2026-08-22?base=USD&symbols=EUR"

response = httpx.get(URL, timeout=60.0)
response.raise_for_status()
data = response.json()

rows = [
    {"date": date, "rate": rates["EUR"]}
    for date, rates in sorted(data["rates"].items())
]

out = pathlib.Path(__file__).parent.parent / "tests" / "fixtures" / "eurusd_rates.json"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(rows, indent=2))
print(f"Wrote {len(rows)} rows to {out}")

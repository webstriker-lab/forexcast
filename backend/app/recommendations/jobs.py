from app.ingestion.supabase_rest import get_active_currencies
from app.recommendations.engine import choose_recommendation, invert_prediction
from app.recommendations.supabase_rest import (
    get_current_rate,
    get_latest_predictions,
    insert_recommendations,
)

PIVOT = "USD"


def _predictable_currencies() -> list[str]:
    return [code for code in get_active_currencies() if code != PIVOT]


def run_recommendations() -> int:
    """Daily job: for every USD-quoted currency, compute a recommendation
    for both directions (USD->X and X->USD) from that currency's latest
    forecast batch, and write them to `recommendations`. A currency with
    no forecast batch or no current rate yet is skipped for both
    directions.
    """
    rows = []
    for quote_code in _predictable_currencies():
        horizons = get_latest_predictions(quote_code)
        if not horizons:
            continue
        current_rate = get_current_rate(quote_code)
        if current_rate is None:
            continue

        forward = choose_recommendation(current_rate, horizons, favorable_high=True)
        rows.append(
            {
                "base_code": PIVOT,
                "quote_code": quote_code,
                "recommendation": forward["recommendation"],
                "reference_horizon_days": forward["reference_horizon_days"],
                "current_rate": forward["current_rate"],
                "expected_rate": forward["expected_rate"],
                "lower_bound": forward["lower_bound"],
                "upper_bound": forward["upper_bound"],
            }
        )

        inverted_horizons = [
            {**h, **invert_prediction(h["predicted_rate"], h["lower_bound"], h["upper_bound"])}
            for h in horizons
        ]
        reverse = choose_recommendation(1 / current_rate, inverted_horizons, favorable_high=False)
        rows.append(
            {
                "base_code": quote_code,
                "quote_code": PIVOT,
                "recommendation": reverse["recommendation"],
                "reference_horizon_days": reverse["reference_horizon_days"],
                "current_rate": reverse["current_rate"],
                "expected_rate": reverse["expected_rate"],
                "lower_bound": reverse["lower_bound"],
                "upper_bound": reverse["upper_bound"],
            }
        )

    insert_recommendations(rows)
    return len(rows)

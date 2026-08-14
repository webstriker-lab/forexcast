from app.ingestion.supabase_rest import get_usd_rate


def cross_rate(as_of: str, from_code: str, to_code: str) -> float:
    if from_code == to_code:
        return 1.0

    from_rate = get_usd_rate(as_of, from_code)
    to_rate = get_usd_rate(as_of, to_code)

    if from_rate is None:
        raise ValueError(f"No USD rate for {from_code} on {as_of}")
    if to_rate is None:
        raise ValueError(f"No USD rate for {to_code} on {as_of}")

    return to_rate / from_rate

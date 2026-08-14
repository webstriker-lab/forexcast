import httpx

FRANKFURTER_BASE_URL = "https://api.frankfurter.dev/v1"


def fetch_latest(base: str, symbols: list[str]) -> dict:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/latest",
        params={"base": base, "symbols": ",".join(symbols)},
        timeout=30.0,
    )
    response.raise_for_status()
    return response.json()


def fetch_range(base: str, symbols: list[str], start: str, end: str) -> dict:
    response = httpx.get(
        f"{FRANKFURTER_BASE_URL}/{start}..{end}",
        params={"base": base, "symbols": ",".join(symbols)},
        timeout=60.0,
    )
    response.raise_for_status()
    return response.json()

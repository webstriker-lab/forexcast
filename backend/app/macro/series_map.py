# backend/app/macro/series_map.py
# currency_code -> FRED series_id, for currencies with a confirmed OECD
# short-term interbank/policy-rate series. Verified against the live
# FRED API during implementation (see Task 3 of the FRED regression
# plan) -- a currency is present here only if a real API call returned
# a 200 with at least one observation for it. Currencies not present
# simply get no macro-adjustment; the rest of the pipeline treats that
# identically to "no coverage yet," never an error.
#
# All 30 candidate currencies from the plan's candidate table were
# checked against the live FRED API (IR3TIB01<country>M156N first,
# then IR3TIB01<country>A156N as a fallback). 22 of 30 resolved to a
# real series (all via the M156N/monthly variant -- none needed the
# A156N/annual fallback). The following 8 currencies had no confirmed
# OECD short-term-rate series on FRED and are intentionally omitted:
# MYR, INR, PHP, RON, THB, SGD, BRL, HKD.
FRED_SERIES: dict[str, str] = {
    "USD": "IR3TIB01USM156N",
    "EUR": "IR3TIB01EZM156N",
    "GBP": "IR3TIB01GBM156N",
    "JPY": "IR3TIB01JPM156N",
    "AUD": "IR3TIB01AUM156N",
    "CAD": "IR3TIB01CAM156N",
    "CHF": "IR3TIB01CHM156N",
    "CNY": "IR3TIB01CNM156N",
    "NZD": "IR3TIB01NZM156N",
    "KRW": "IR3TIB01KRM156N",
    "MXN": "IR3TIB01MXM156N",
    "NOK": "IR3TIB01NOM156N",
    "PLN": "IR3TIB01PLM156N",
    "SEK": "IR3TIB01SEM156N",
    "TRY": "IR3TIB01TRM156N",
    "ZAR": "IR3TIB01ZAM156N",
    "CZK": "IR3TIB01CZM156N",
    "IDR": "IR3TIB01IDM156N",
    "DKK": "IR3TIB01DKM156N",
    "ILS": "IR3TIB01ILM156N",
    "HUF": "IR3TIB01HUM156N",
    "ISK": "IR3TIB01ISM156N",
}

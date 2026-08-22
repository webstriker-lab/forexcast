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

# currency_code -> FRED series_id, for currencies with a confirmed
# YoY-growth-rate CPI series (OECD COICOP 659N, or the equivalent
# national-source growth-rate series for a few countries). Verified
# against the live FRED API the same way as FRED_SERIES above. Growth
# rate specifically, not an index level -- a currency whose only
# available CPI series is an index (e.g. Eurostat HICP for CZK/DKK/TRY
# as a fallback, or RON, which has no growth-rate series at all) is
# intentionally omitted rather than mixed with growth-rate values from
# other countries, which would make the differential meaningless.
# 24 of 30 confirmed; MYR, PHP, RON, THB, SGD, HKD have no usable
# CPI series at all on FRED.
CPI_SERIES: dict[str, str] = {
    "USD": "CPALTT01USM659N",
    "EUR": "CPHPTT01EZM659N",
    "GBP": "CPALTT01GBM659N",
    "JPY": "CPALTT01JPM659N",
    "AUD": "CPALTT01AUQ659N",
    "CAD": "CPALTT01CAM659N",
    "CHF": "CPALTT01CHM659N",
    "CNY": "CPALTT01CNM659N",
    "NZD": "CPALTT01NZQ659N",
    "KRW": "CPALTT01KRM659N",
    "MXN": "CPALTT01MXM659N",
    "NOK": "CPALTT01NOM659N",
    "PLN": "CPALTT01PLM659N",
    "SEK": "CPALTT01SEM659N",
    "TRY": "CPALTT01TRM659N",
    "ZAR": "CPALTT01ZAM659N",
    "CZK": "CPALTT01CZM659N",
    "IDR": "CPALTT01IDM659N",
    "DKK": "CPALTT01DKM659N",
    "ILS": "CPALTT01ILM659N",
    "HUF": "CPALTT01HUM659N",
    "ISK": "CPALTT01ISM659N",
    "INR": "CPALTT01INM659N",
    "BRL": "CPALTT01BRM659N",
}

# currency_code -> FRED series_id, OECD National Accounts real GDP
# growth rate (NAEXKP01<CC>Q657S, quarterly, SA), verified live.
# 23 of 30 confirmed; CNY has no confirmed GDP-growth series despite
# having both interest-rate and CPI coverage. MYR, PHP, RON, THB, SGD,
# HKD's only FRED coverage for GDP mixes real history with IMF forecast
# years through 2031 (checked directly) -- using that would leak future
# data into the backtest, so those 6 are intentionally omitted here too,
# same reasoning as CPI's exclusions plus this additional one.
GDP_SERIES: dict[str, str] = {
    "USD": "NAEXKP01USQ657S",
    "EUR": "NAEXKP01EZQ657S",
    "GBP": "NAEXKP01GBQ657S",
    "JPY": "NAEXKP01JPQ657S",
    "AUD": "NAEXKP01AUQ657S",
    "CAD": "NAEXKP01CAQ657S",
    "CHF": "NAEXKP01CHQ657S",
    "NZD": "NAEXKP01NZQ657S",
    "KRW": "NAEXKP01KRQ657S",
    "MXN": "NAEXKP01MXQ657S",
    "NOK": "NAEXKP01NOQ657S",
    "PLN": "NAEXKP01PLQ657S",
    "SEK": "NAEXKP01SEQ657S",
    "TRY": "NAEXKP01TRQ657S",
    "ZAR": "NAEXKP01ZAQ657S",
    "CZK": "NAEXKP01CZQ657S",
    "IDR": "NAEXKP01IDQ657S",
    "DKK": "NAEXKP01DKQ657S",
    "ILS": "NAEXKP01ILQ657S",
    "HUF": "NAEXKP01HUQ657S",
    "ISK": "NAEXKP01ISQ657S",
    "INR": "NAEXKP01INQ657S",
    "BRL": "NAEXKP01BRQ657S",
}

# currency_code -> FRED series_id, OECD current account balance (% of
# GDP, SA, quarterly, series pattern <CC3>B6BLTT02STSAQ), verified live.
# 24 of 30 confirmed -- the same 6 currencies excluded as CPI_SERIES
# (MYR, PHP, RON, THB, SGD, HKD have no usable series for either), but
# this time EUR and CZK ARE covered (unlike CPI, where only an
# index-level, not growth-rate, series exists for them).
CURRENT_ACCOUNT_SERIES: dict[str, str] = {
    "USD": "USAB6BLTT02STSAQ",
    "EUR": "EA19B6BLTT02STSAQ",
    "GBP": "GBRB6BLTT02STSAQ",
    "JPY": "JPNB6BLTT02STSAQ",
    "AUD": "AUSB6BLTT02STSAQ",
    "CAD": "CANB6BLTT02STSAQ",
    "CHF": "CHEB6BLTT02STSAQ",
    "CNY": "CHNB6BLTT02STSAQ",
    "NZD": "NZLB6BLTT02STSAQ",
    "KRW": "KORB6BLTT02STSAQ",
    "MXN": "MEXB6BLTT02STSAQ",
    "NOK": "NORB6BLTT02STSAQ",
    "PLN": "POLB6BLTT02STSAQ",
    "SEK": "SWEB6BLTT02STSAQ",
    "TRY": "TURB6BLTT02STSAQ",
    "ZAR": "ZAFB6BLTT02STSAQ",
    "CZK": "CZEB6BLTT02STSAQ",
    "IDR": "IDNB6BLTT02STSAQ",
    "DKK": "DNKB6BLTT02STSAQ",
    "ILS": "ISRB6BLTT02STSAQ",
    "HUF": "HUNB6BLTT02STSAQ",
    "ISK": "ISLB6BLTT02STSAQ",
    "INR": "INDB6BLTT02STSAQ",
    "BRL": "BRAB6BLTT02STSAQ",
}

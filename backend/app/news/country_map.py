# currency_code -> country/region proper name, used as a GDELT search
# keyword (see app.news.gdelt_client). Drafted directly, not verified
# against a live API the way app.macro.series_map's FRED IDs were --
# there's no "wrong mapping" failure mode here, since a currency with
# genuinely sparse GDELT coverage for its country name just produces a
# low article count and a normal skip (app.news.jobs' MIN_ARTICLES
# gate), not an error. Covers all 29 non-USD currencies this app
# tracks (USD itself is excluded, matching _predictable_currencies()
# in app.prediction.jobs -- there's no "USD's own sentiment" needed).
COUNTRY_NAMES: dict[str, str] = {
    "EUR": "Eurozone",
    "GBP": "United Kingdom",
    "INR": "India",
    "JPY": "Japan",
    "AUD": "Australia",
    "CAD": "Canada",
    "CHF": "Switzerland",
    "CNY": "China",
    "SGD": "Singapore",
    "NZD": "New Zealand",
    "BRL": "Brazil",
    "CZK": "Czech Republic",
    "DKK": "Denmark",
    "HKD": "Hong Kong",
    "HUF": "Hungary",
    "IDR": "Indonesia",
    "ILS": "Israel",
    "ISK": "Iceland",
    "KRW": "South Korea",
    "MXN": "Mexico",
    "MYR": "Malaysia",
    "NOK": "Norway",
    "PHP": "Philippines",
    "PLN": "Poland",
    "RON": "Romania",
    "SEK": "Sweden",
    "THB": "Thailand",
    "TRY": "Turkey",
    "ZAR": "South Africa",
}

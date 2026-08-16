from app.news.country_map import COUNTRY_NAMES


def test_country_names_is_nonempty():
    assert len(COUNTRY_NAMES) > 0


def test_country_names_keys_and_values_are_strings():
    for currency_code, country_name in COUNTRY_NAMES.items():
        assert isinstance(currency_code, str) and len(currency_code) == 3
        assert isinstance(country_name, str) and len(country_name) > 0


def test_country_names_covers_all_29_non_usd_currencies():
    expected = {
        "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "CNY", "SGD", "NZD",
        "BRL", "CZK", "DKK", "HKD", "HUF", "IDR", "ILS", "ISK", "KRW", "MXN",
        "MYR", "NOK", "PHP", "PLN", "RON", "SEK", "THB", "TRY", "ZAR",
    }
    assert set(COUNTRY_NAMES.keys()) == expected

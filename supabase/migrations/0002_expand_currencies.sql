-- Frankfurter (ECB reference rates) does not publish a rate for AED; drop it.
-- No dependent rows exist yet (no watchlist/alert entries reference it).
delete from public.currencies where code = 'AED';

-- Add the remaining currencies Frankfurter supports, to reach its full
-- 30-currency set (see design doc §4 for the verification behind this list).
insert into public.currencies (code, name) values
    ('BRL', 'Brazilian Real'),
    ('CZK', 'Czech Koruna'),
    ('DKK', 'Danish Krone'),
    ('HKD', 'Hong Kong Dollar'),
    ('HUF', 'Hungarian Forint'),
    ('IDR', 'Indonesian Rupiah'),
    ('ILS', 'Israeli New Shekel'),
    ('ISK', 'Icelandic Króna'),
    ('KRW', 'South Korean Won'),
    ('MXN', 'Mexican Peso'),
    ('MYR', 'Malaysian Ringgit'),
    ('NOK', 'Norwegian Krone'),
    ('PHP', 'Philippine Peso'),
    ('PLN', 'Polish Złoty'),
    ('RON', 'Romanian Leu'),
    ('SEK', 'Swedish Krona'),
    ('THB', 'Thai Baht'),
    ('TRY', 'Turkish Lira'),
    ('ZAR', 'South African Rand');

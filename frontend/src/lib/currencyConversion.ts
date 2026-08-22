import { supabase } from './supabaseClient'

// Latest USD->code rate (units of `code` per 1 USD) for each requested
// currency, read from rates_cache. Matches the direction convention used
// throughout this app (app.recommendations.supabase_rest.get_current_rate,
// app.planner.timeline.calculate_total_debt_summary): USD is the pivot,
// amount_in_code = amount_usd * rate.
export async function fetchUsdConversionRates(currencies: string[]): Promise<Map<string, number>> {
  const nonUsd = [...new Set(currencies)].filter(c => c !== 'USD')
  const rateByCurrency = new Map<string, number>()
  if (nonUsd.length === 0) return rateByCurrency

  const { data } = await supabase
    .from('rates_cache')
    .select('quote_code, rate, as_of')
    .eq('base_code', 'USD')
    .in('quote_code', nonUsd)
    .order('as_of', { ascending: false })

  for (const row of data ?? []) {
    if (!rateByCurrency.has(row.quote_code)) rateByCurrency.set(row.quote_code, row.rate)
  }
  return rateByCurrency
}

// Converts a USD amount into `targetCurrency` using rates already fetched
// via fetchUsdConversionRates. Returns null if targetCurrency isn't USD and
// no rate was found for it (no rates_cache data yet), rather than silently
// showing a wrong number.
export function convertUsdTo(
  amountUsd: number,
  targetCurrency: string,
  usdRates: Map<string, number>,
): number | null {
  if (targetCurrency === 'USD') return amountUsd
  const rate = usdRates.get(targetCurrency)
  return rate != null ? amountUsd * rate : null
}

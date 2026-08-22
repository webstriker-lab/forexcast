import { useState } from 'react'
import type { CurrencyPair } from '../hooks/useWatchlist'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SGD', 'NZD', 'AED']

interface Props {
  pairs: CurrencyPair[]
  selected: CurrencyPair | null
  onSelect: (pair: CurrencyPair) => void
  onAdd: (base: string, quote: string) => Promise<boolean>
  onRemove: (base: string, quote: string) => void
}

export function PairPicker({ pairs, selected, onSelect, onAdd, onRemove }: Props) {
  const [base, setBase] = useState('USD')
  const [quote, setQuote] = useState('EUR')

  const handleAdd = async () => {
    if (base === quote) return
    await onAdd(base, quote)
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select
        value={base}
        onChange={e => setBase(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <span className="text-gray-400 font-medium">→</span>
      <select
        value={quote}
        onChange={e => setQuote(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
      </select>
      <button
        onClick={handleAdd}
        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium transition-colors"
      >
        + Add
      </button>
      <div className="flex flex-wrap gap-2 ml-2">
        {pairs.map(p => {
          const isSelected = selected?.base_code === p.base_code && selected?.quote_code === p.quote_code
          return (
            <span
              key={`${p.base_code}-${p.quote_code}`}
              className={`inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium cursor-pointer transition-colors ${
                isSelected
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              <span onClick={() => onSelect(p)}>{p.base_code}/{p.quote_code}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onRemove(p.base_code, p.quote_code) }}
                className="ml-1 text-xs opacity-60 hover:opacity-100"
                title="Remove"
              >
                ×
              </button>
            </span>
          )
        })}
      </div>
    </div>
  )
}

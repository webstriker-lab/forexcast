import { useState, useEffect } from 'react'
import type { Debt } from '../hooks/useDebts'
import { getDebtTimeline } from '../lib/apiClient'
import { useDisplayCurrency } from '../hooks/useDisplayCurrency'
import { convertUsdTo, fetchUsdConversionRates } from '../lib/currencyConversion'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SGD', 'NZD', 'AED']

interface Props {
  debts: Debt[]
  onCreate: (debt: Omit<Debt, 'id' | 'is_active' | 'created_at'>) => Promise<boolean>
  onUpdate: (id: string, data: Partial<Debt>) => Promise<boolean>
  onDelete: (id: string) => Promise<boolean>
}

interface DebtSummary {
  total_balance: number
  total_minimum_payment: number
  debt_count: number
  currencies_missing_rate: string[]
}

export function DebtManager({ debts, onCreate, onUpdate, onDelete }: Props) {
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form, setForm] = useState({
    name: '',
    currency_code: 'USD',
    original_amount: '',
    current_balance: '',
    interest_rate: '',
    minimum_payment: '',
    due_day: '',
  })
  const [summary, setSummary] = useState<DebtSummary | null>(null)
  const [summaryError, setSummaryError] = useState<string | null>(null)
  const { currency: displayCurrency } = useDisplayCurrency()
  const [displayTotals, setDisplayTotals] = useState<{ balance: number; payment: number } | null>(null)

  useEffect(() => {
    getDebtTimeline()
      .then(res => {
        setSummary(res.summary as DebtSummary)
        setSummaryError(null)
      })
      .catch((err: Error) => setSummaryError(err.message))
  }, [debts])

  useEffect(() => {
    if (!summary) return
    let cancelled = false
    fetchUsdConversionRates([displayCurrency]).then(rates => {
      if (cancelled) return
      const balance = convertUsdTo(summary.total_balance, displayCurrency, rates)
      const payment = convertUsdTo(summary.total_minimum_payment, displayCurrency, rates)
      setDisplayTotals(balance !== null && payment !== null ? { balance, payment } : null)
    })
    return () => {
      cancelled = true
    }
  }, [summary, displayCurrency])

  const resetForm = () => {
    setForm({
      name: '',
      currency_code: 'USD',
      original_amount: '',
      current_balance: '',
      interest_rate: '',
      minimum_payment: '',
      due_day: '',
    })
    setEditingId(null)
    setShowForm(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const debt = {
      name: form.name,
      currency_code: form.currency_code,
      original_amount: parseFloat(form.original_amount),
      current_balance: parseFloat(form.current_balance),
      interest_rate: parseFloat(form.interest_rate),
      minimum_payment: parseFloat(form.minimum_payment),
      due_day: form.due_day ? parseInt(form.due_day) : null,
    }

    if (editingId) {
      await onUpdate(editingId, debt)
    } else {
      await onCreate(debt)
    }
    resetForm()
  }

  const startEdit = (debt: Debt) => {
    setForm({
      name: debt.name,
      currency_code: debt.currency_code,
      original_amount: debt.original_amount.toString(),
      current_balance: debt.current_balance.toString(),
      interest_rate: debt.interest_rate.toString(),
      minimum_payment: debt.minimum_payment.toString(),
      due_day: debt.due_day?.toString() || '',
    })
    setEditingId(debt.id)
    setShowForm(true)
  }

  const activeDebts = debts.filter(d => d.is_active)

  return (
    <div className="space-y-6">
      {summaryError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {summaryError}
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500">Total Debt ({displayCurrency})</p>
          <p className="text-2xl font-bold text-red-600">
            {displayTotals ? displayTotals.balance.toLocaleString(undefined, { style: 'currency', currency: displayCurrency }) : '—'}
          </p>
          {summary && summary.currencies_missing_rate.length > 0 && (
            <p className="text-xs text-gray-400 mt-1">
              Excludes debts in {summary.currencies_missing_rate.join(', ')} (no rate yet)
            </p>
          )}
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500">Monthly Payments ({displayCurrency})</p>
          <p className="text-2xl font-bold">
            {displayTotals ? displayTotals.payment.toLocaleString(undefined, { style: 'currency', currency: displayCurrency }) : '—'}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-4">
          <p className="text-sm text-gray-500">Active Debts</p>
          <p className="text-2xl font-bold">{activeDebts.length}</p>
        </div>
      </div>

      {/* Add Button */}
      <button
        onClick={() => setShowForm(true)}
        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 font-medium"
      >
        + Add Debt
      </button>

      {/* Form */}
      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-4">
          <h3 className="text-lg font-semibold">{editingId ? 'Edit Debt' : 'Add New Debt'}</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Student Loan"
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
              <select
                value={form.currency_code}
                onChange={e => setForm({ ...form, currency_code: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
              >
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Original Amount</label>
              <input
                type="number"
                step="any"
                value={form.original_amount}
                onChange={e => setForm({ ...form, original_amount: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Current Balance</label>
              <input
                type="number"
                step="any"
                value={form.current_balance}
                onChange={e => setForm({ ...form, current_balance: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Interest Rate (annual %)</label>
              <input
                type="number"
                step="any"
                value={form.interest_rate}
                onChange={e => setForm({ ...form, interest_rate: e.target.value })}
                placeholder="e.g. 5.5"
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Minimum Payment</label>
              <input
                type="number"
                step="any"
                value={form.minimum_payment}
                onChange={e => setForm({ ...form, minimum_payment: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700">
              {editingId ? 'Update' : 'Add'} Debt
            </button>
            <button type="button" onClick={resetForm} className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300">
              Cancel
            </button>
          </div>
        </form>
      )}

      {/* Debt List */}
      <div className="space-y-3">
        {activeDebts.map(debt => (
          <div key={debt.id} className="bg-white rounded-lg shadow p-4">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="font-semibold">{debt.name}</h4>
                <p className="text-sm text-gray-500">
                  {debt.currency_code} • {debt.interest_rate.toFixed(1)}% APR
                </p>
              </div>
              <div className="text-right">
                <p className="text-lg font-bold text-red-600">
                  {debt.currency_code} {debt.current_balance.toLocaleString()}
                </p>
                <p className="text-sm text-gray-500">
                  {debt.currency_code} {debt.minimum_payment}/mo
                </p>
              </div>
            </div>
            {/* Progress bar */}
            <div className="mt-3">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>Paid off</span>
                <span>{((1 - debt.current_balance / debt.original_amount) * 100).toFixed(1)}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-500 h-2 rounded-full"
                  style={{ width: `${(1 - debt.current_balance / debt.original_amount) * 100}%` }}
                />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => startEdit(debt)}
                className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
              >
                Edit
              </button>
              <button
                onClick={() => onDelete(debt.id)}
                className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
        {activeDebts.length === 0 && (
          <p className="text-center text-gray-400 py-8">No debts added yet</p>
        )}
      </div>
    </div>
  )
}

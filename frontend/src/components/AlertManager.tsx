import { useState } from 'react'
import type { Alert } from '../hooks/useAlerts'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SGD', 'NZD', 'AED']

interface Props {
  alerts: Alert[]
  onCreate: (alert: Omit<Alert, 'id' | 'is_active' | 'created_at'>) => Promise<boolean>
  onToggle: (id: string, isActive: boolean) => void
  onDelete: (id: string) => void
}

export function AlertManager({ alerts, onCreate, onToggle, onDelete }: Props) {
  const [base, setBase] = useState('USD')
  const [quote, setQuote] = useState('EUR')
  const [alertType, setAlertType] = useState<'threshold' | 'recommendation_change'>('threshold')
  const [threshold, setThreshold] = useState('')
  const [direction, setDirection] = useState<'above' | 'below'>('above')
  const [submitting, setSubmitting] = useState(false)

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    const alert: Omit<Alert, 'id' | 'is_active' | 'created_at'> = {
      base_code: base,
      quote_code: quote,
      alert_type: alertType,
      threshold_rate: alertType === 'threshold' ? parseFloat(threshold) : null,
      direction: alertType === 'threshold' ? direction : null,
    }
    await onCreate(alert)
    setThreshold('')
    setSubmitting(false)
  }

  return (
    <div className="space-y-6">
      {/* Create form */}
      <form onSubmit={handleCreate} className="bg-white rounded-lg shadow p-4 space-y-4">
        <h3 className="font-semibold text-lg">Create Alert</h3>
        <div className="flex flex-wrap gap-3">
          <select value={base} onChange={e => setBase(e.target.value)} className="px-3 py-2 border rounded-md text-sm">
            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <span className="text-gray-400 self-center">→</span>
          <select value={quote} onChange={e => setQuote(e.target.value)} className="px-3 py-2 border rounded-md text-sm">
            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={alertType} onChange={e => setAlertType(e.target.value as 'threshold' | 'recommendation_change')} className="px-3 py-2 border rounded-md text-sm">
            <option value="threshold">Threshold</option>
            <option value="recommendation_change">Recommendation change</option>
          </select>
        </div>
        {alertType === 'threshold' && (
          <div className="flex flex-wrap gap-3">
            <select value={direction} onChange={e => setDirection(e.target.value as 'above' | 'below')} className="px-3 py-2 border rounded-md text-sm">
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
            <input
              type="number"
              step="any"
              value={threshold}
              onChange={e => setThreshold(e.target.value)}
              placeholder="Threshold rate"
              className="px-3 py-2 border rounded-md text-sm w-40"
              required
            />
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
        >
          {submitting ? 'Creating...' : 'Create Alert'}
        </button>
      </form>

      {/* Alert list */}
      <div className="space-y-2">
        {alerts.length === 0 && (
          <p className="text-gray-400 text-center py-4">No alerts yet</p>
        )}
        {alerts.map(alert => (
          <div
            key={alert.id}
            className={`bg-white rounded-lg shadow p-4 flex items-center justify-between ${!alert.is_active ? 'opacity-50' : ''}`}
          >
            <div>
              <span className="font-medium">{alert.base_code}/{alert.quote_code}</span>
              <span className="text-gray-500 text-sm ml-2">
                {alert.alert_type === 'threshold'
                  ? `${alert.direction} ${alert.threshold_rate}`
                  : 'Recommendation change'}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onToggle(alert.id, !alert.is_active)}
                className={`px-3 py-1 rounded text-xs font-medium ${
                  alert.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                }`}
              >
                {alert.is_active ? 'Active' : 'Paused'}
              </button>
              <button
                onClick={() => onDelete(alert.id)}
                className="px-3 py-1 rounded text-xs font-medium bg-red-100 text-red-800 hover:bg-red-200"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

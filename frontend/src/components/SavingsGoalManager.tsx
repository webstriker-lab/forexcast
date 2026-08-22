import { useEffect, useState } from 'react'
import type { SavingsGoal } from '../hooks/useSavingsGoals'
import { getGoalsTimeline, type GoalTimelineEntry } from '../lib/apiClient'

const CURRENCIES = ['USD', 'EUR', 'GBP', 'INR', 'JPY', 'AUD', 'CAD', 'CHF', 'CNY', 'SGD', 'NZD', 'AED']

interface Props {
  goals: SavingsGoal[]
  onCreate: (goal: Omit<SavingsGoal, 'id' | 'is_active' | 'created_at'>) => Promise<boolean>
  onUpdate: (id: string, data: Partial<SavingsGoal>) => Promise<boolean>
  onDelete: (id: string) => Promise<boolean>
}

export function SavingsGoalManager({ goals, onCreate, onUpdate, onDelete }: Props) {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({
    name: '',
    target_currency: 'USD',
    target_amount: '',
    current_saved: '',
    target_date: '',
    monthly_contribution: '',
  })

  const [timelines, setTimelines] = useState<Record<string, GoalTimelineEntry>>({})
  const [timelineError, setTimelineError] = useState<string | null>(null)

  useEffect(() => {
    getGoalsTimeline()
      .then(res => {
        setTimelines(res.goals)
        setTimelineError(null)
      })
      .catch((err: Error) => setTimelineError(err.message))
  }, [goals])

  const resetForm = () => {
    setForm({
      name: '',
      target_currency: 'USD',
      target_amount: '',
      current_saved: '',
      target_date: '',
      monthly_contribution: '',
    })
    setShowForm(false)
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await onCreate({
      name: form.name,
      target_currency: form.target_currency,
      target_amount: parseFloat(form.target_amount),
      current_saved: parseFloat(form.current_saved) || 0,
      target_date: form.target_date || null,
      monthly_contribution: form.monthly_contribution ? parseFloat(form.monthly_contribution) : null,
    })
    resetForm()
  }

  const activeGoals = goals.filter(g => g.is_active)

  return (
    <div className="space-y-6">
      <button
        onClick={() => setShowForm(true)}
        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 font-medium"
      >
        + Add Savings Goal
      </button>

      {showForm && (
        <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow p-6 space-y-4">
          <h3 className="text-lg font-semibold">Add Savings Goal</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Goal Name</label>
              <input
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Europe Trip"
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Currency</label>
              <select
                value={form.target_currency}
                onChange={e => setForm({ ...form, target_currency: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
              >
                {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Target Amount</label>
              <input
                type="number"
                step="any"
                value={form.target_amount}
                onChange={e => setForm({ ...form, target_amount: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Already Saved</label>
              <input
                type="number"
                step="any"
                value={form.current_saved}
                onChange={e => setForm({ ...form, current_saved: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Target Date (optional)</label>
              <input
                type="date"
                value={form.target_date}
                onChange={e => setForm({ ...form, target_date: e.target.value })}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Monthly Contribution (optional)</label>
              <input
                type="number"
                step="any"
                value={form.monthly_contribution}
                onChange={e => setForm({ ...form, monthly_contribution: e.target.value })}
                placeholder="Leave blank to derive from target date"
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700">
              Add Goal
            </button>
            <button type="button" onClick={resetForm} className="px-4 py-2 bg-gray-200 text-gray-700 rounded-md hover:bg-gray-300">
              Cancel
            </button>
          </div>
        </form>
      )}

      {timelineError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
          {timelineError}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {activeGoals.map(goal => {
          const progress = goal.current_saved / goal.target_amount
          const isComplete = progress >= 1
          const timeline = timelines[goal.id]

          return (
            <div key={goal.id} className={`bg-white rounded-lg shadow p-6 ${isComplete ? 'ring-2 ring-green-500' : ''}`}>
              <div className="flex items-center justify-between mb-4">
                <h4 className="font-semibold text-lg">{goal.name}</h4>
                {isComplete && <span className="text-2xl">🎉</span>}
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Progress</span>
                  <span className="font-medium">{(progress * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full ${isComplete ? 'bg-green-500' : 'bg-blue-500'}`}
                    style={{ width: `${Math.min(progress * 100, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Saved</span>
                  <span className="font-medium">{goal.target_currency} {goal.current_saved.toLocaleString()}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">Target</span>
                  <span className="font-medium">{goal.target_currency} {goal.target_amount.toLocaleString()}</span>
                </div>
                {goal.target_date && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Target Date</span>
                    <span className="font-medium">{new Date(goal.target_date).toLocaleDateString()}</span>
                  </div>
                )}
                {!isComplete && timeline?.monthly_contribution != null && (
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-500">Monthly needed</span>
                    <span className="font-medium">
                      {goal.target_currency} {timeline.monthly_contribution.toLocaleString()}
                      {timeline.months_to_goal != null && ` (~${timeline.months_to_goal} mo)`}
                    </span>
                  </div>
                )}
                {!isComplete && timeline?.error && (
                  <p className="text-xs text-gray-400">{timeline.error}</p>
                )}
              </div>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={() => onUpdate(goal.id, { current_saved: goal.current_saved + 100 })}
                  className="px-3 py-1 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200"
                >
                  + $100
                </button>
                <button
                  onClick={() => onDelete(goal.id)}
                  className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                >
                  Delete
                </button>
              </div>
            </div>
          )
        })}
        {activeGoals.length === 0 && (
          <p className="text-center text-gray-400 py-8 col-span-2">No savings goals yet</p>
        )}
      </div>
    </div>
  )
}

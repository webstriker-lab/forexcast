import type { Streaks } from '../hooks/useAchievements'

interface Props {
  streaks: Streaks | null
  onCheckin: () => void
}

export function StreakCounter({ streaks, onCheckin }: Props) {
  if (!streaks) {
    return (
      <div className="bg-white rounded-lg shadow p-6 text-center">
        <p className="text-gray-400">Loading streaks...</p>
      </div>
    )
  }

  const streakItems = [
    {
      label: 'Daily Check-in',
      current: streaks.daily_checkin_current,
      best: streaks.daily_checkin_best,
      emoji: '🔥',
    },
    {
      label: 'Savings Streak',
      current: streaks.savings_current,
      best: streaks.savings_best,
      emoji: '💰',
    },
    {
      label: 'Debt Payments',
      current: streaks.debt_payment_current,
      best: streaks.debt_payment_best,
      emoji: '💳',
    },
  ]

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Streaks</h3>
        <button
          onClick={onCheckin}
          className="px-4 py-2 bg-orange-500 text-white rounded-full hover:bg-orange-600 font-medium text-sm"
        >
          🔥 Check In
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {streakItems.map(item => (
          <div key={item.label} className="text-center p-4 bg-gray-50 rounded-lg">
            <div className="text-3xl mb-2">{item.emoji}</div>
            <p className="text-2xl font-bold">{item.current}</p>
            <p className="text-sm text-gray-500">{item.label}</p>
            <p className="text-xs text-gray-400 mt-1">Best: {item.best}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

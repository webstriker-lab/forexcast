import type { Achievement } from '../hooks/useAchievements'

const ALL_BADGES = [
  { id: 'first_debt_paid_off', name: 'First Debt Paid Off', emoji: '🎯', description: 'Paid off your first debt completely' },
  { id: 'savings_goal_reached', name: 'Savings Goal Reached', emoji: '💰', description: 'Reached a savings goal' },
  { id: 'streak_30_days', name: 'Fox Friend', emoji: '🦊', description: '30-day check-in streak' },
  { id: 'multi_currency_master', name: 'Multi-Currency Master', emoji: '🌍', description: 'Active debts in 3+ currencies' },
  { id: 'financial_freedom', name: 'Financial Freedom', emoji: '🏆', description: 'All debts paid off' },
  { id: 'first_goal_set', name: 'Goal Setter', emoji: '🎯', description: 'Created your first savings goal' },
  { id: 'first_alert_created', name: 'Alert Setter', emoji: '🔔', description: 'Created your first alert' },
]

interface Props {
  achievements: Achievement[]
}

export function BadgeGrid({ achievements }: Props) {
  const earnedIds = new Set(achievements.map(a => a.badge_id))

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {ALL_BADGES.map(badge => {
        const earned = earnedIds.has(badge.id)
        const achievement = achievements.find(a => a.badge_id === badge.id)

        return (
          <div
            key={badge.id}
            className={`bg-white rounded-lg shadow p-4 text-center transition-all ${
              earned ? 'ring-2 ring-yellow-400 scale-105' : 'opacity-50 grayscale'
            }`}
          >
            <div className="text-4xl mb-2">{badge.emoji}</div>
            <h4 className="font-semibold text-sm">{badge.name}</h4>
            <p className="text-xs text-gray-500 mt-1">{badge.description}</p>
            {earned && achievement && (
              <p className="text-xs text-green-600 mt-2">
                ✓ {new Date(achievement.earned_at).toLocaleDateString()}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

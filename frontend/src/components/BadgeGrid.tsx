import type { Achievement, Badge } from '../hooks/useAchievements'

interface Props {
  achievements: Achievement[]
  badges: Record<string, Badge>
}

export function BadgeGrid({ achievements, badges }: Props) {
  const earnedIds = new Set(achievements.map(a => a.badge_id))

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {Object.entries(badges).map(([badgeId, badge]) => {
        const earned = earnedIds.has(badgeId)
        const achievement = achievements.find(a => a.badge_id === badgeId)

        return (
          <div
            key={badgeId}
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

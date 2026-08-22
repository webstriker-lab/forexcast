import { Layout } from '../components/Layout'
import { BadgeGrid } from '../components/BadgeGrid'
import { StreakCounter } from '../components/StreakCounter'
import { useAchievements } from '../hooks/useAchievements'

export default function Achievements() {
  const { achievements, streaks, badges, loading, error, recordCheckin } = useAchievements()

  return (
    <Layout>
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Achievements & Streaks</h1>
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-4 py-3">
            {error}
          </div>
        )}
        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading...</div>
        ) : (
          <>
            <StreakCounter streaks={streaks} onCheckin={recordCheckin} />

            <div>
              <h2 className="text-xl font-bold mb-4">Badges ({achievements.length} earned)</h2>
              <BadgeGrid achievements={achievements} badges={badges} />
            </div>

            {achievements.length > 0 && (
              <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-semibold mb-4">Recent Achievements</h3>
                <div className="space-y-3">
                  {achievements.slice(0, 5).map(a => (
                    <div key={a.id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                      <span className="text-2xl">{badges[a.badge_id]?.emoji ?? '🏅'}</span>
                      <div>
                        <p className="font-medium">{badges[a.badge_id]?.name ?? a.badge_id}</p>
                        <p className="text-sm text-gray-500">
                          Earned {new Date(a.earned_at).toLocaleDateString()}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Layout>
  )
}

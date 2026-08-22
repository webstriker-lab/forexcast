import { Layout } from '../components/Layout'
import { SavingsGoalManager } from '../components/SavingsGoalManager'
import { useSavingsGoals } from '../hooks/useSavingsGoals'

export default function Goals() {
  const { goals, loading, createGoal, updateGoal, deleteGoal } = useSavingsGoals()

  return (
    <Layout>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Savings Goals</h1>
        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading...</div>
        ) : (
          <SavingsGoalManager
            goals={goals}
            onCreate={createGoal}
            onUpdate={updateGoal}
            onDelete={deleteGoal}
          />
        )}
      </div>
    </Layout>
  )
}

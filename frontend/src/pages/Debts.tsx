import { Layout } from '../components/Layout'
import { DebtManager } from '../components/DebtManager'
import { useDebts } from '../hooks/useDebts'

export default function Debts() {
  const { debts, loading, createDebt, updateDebt, deleteDebt } = useDebts()

  return (
    <Layout>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Debt Management</h1>
        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading...</div>
        ) : (
          <DebtManager
            debts={debts}
            onCreate={createDebt}
            onUpdate={updateDebt}
            onDelete={deleteDebt}
          />
        )}
      </div>
    </Layout>
  )
}

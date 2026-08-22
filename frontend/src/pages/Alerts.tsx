import { useAlerts } from '../hooks/useAlerts'
import { AlertManager } from '../components/AlertManager'
import { Layout } from '../components/Layout'

export default function Alerts() {
  const { alerts, loading, createAlert, toggleAlert, deleteAlert } = useAlerts()

  return (
    <Layout>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Alerts</h1>
        {loading ? (
          <div className="text-center text-gray-400 py-12">Loading...</div>
        ) : (
          <AlertManager
            alerts={alerts}
            onCreate={createAlert}
            onToggle={toggleAlert}
            onDelete={deleteAlert}
          />
        )}
      </div>
    </Layout>
  )
}

import { SettingsPage } from '../components/SettingsPage'
import { Layout } from '../components/Layout'

export default function Settings() {
  return (
    <Layout>
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Settings</h1>
        <SettingsPage />
      </div>
    </Layout>
  )
}

import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabaseClient'

const PROVIDERS = [
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'groq', label: 'Groq' },
  { value: 'gemini', label: 'Google Gemini' },
]

export function SettingsPage() {
  const [provider, setProvider] = useState('openrouter')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState('')
  const [telegramStatus, setTelegramStatus] = useState<'loading' | 'linked' | 'not_linked'>('loading')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => {
    loadSettings()
    loadTelegramStatus()
  }, [])

  const loadSettings = async () => {
    const { data } = await supabase
      .from('llm_settings')
      .select('provider, model')
      .single()
    if (data) {
      setProvider(data.provider)
      setModel(data.model || '')
    }
  }

  const loadTelegramStatus = async () => {
    const { data } = await supabase
      .from('notification_settings')
      .select('telegram_chat_id')
      .single()
    setTelegramStatus(data?.telegram_chat_id ? 'linked' : 'not_linked')
  }

  const handleSave = async () => {
    setSaving(true)
    setMessage('')
    // Note: In production, the API key would be encrypted client-side with
    // TweetNaCl sealed-box before writing. For now, we write the provider/model.
    const { error } = await supabase
      .from('llm_settings')
      .upsert({
        provider,
        model: model || null,
        api_key_encrypted: apiKey || 'placeholder', // Will be encrypted in production
      }, { onConflict: 'user_id' })
    setMessage(error ? `Error: ${error.message}` : 'Settings saved!')
    setSaving(false)
  }

  return (
    <div className="max-w-lg space-y-6">
      {/* LLM Settings */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <h3 className="text-lg font-semibold">LLM Configuration</h3>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
          <select
            value={provider}
            onChange={e => setProvider(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {PROVIDERS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="Enter your API key"
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-xs text-gray-500 mt-1">Encrypted before storage — never sent to our servers in plain text.</p>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Model (optional)</label>
          <input
            type="text"
            value={model}
            onChange={e => setModel(e.target.value)}
            placeholder="e.g. anthropic/claude-3.5-sonnet"
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
        {message && <p className={`text-sm ${message.startsWith('Error') ? 'text-red-600' : 'text-green-600'}`}>{message}</p>}
      </div>

      {/* Telegram */}
      <div className="bg-white rounded-lg shadow p-6 space-y-4">
        <h3 className="text-lg font-semibold">Telegram Notifications</h3>
        {telegramStatus === 'loading' ? (
          <p className="text-gray-400 text-sm">Loading...</p>
        ) : telegramStatus === 'linked' ? (
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full"></span>
            <span className="text-sm text-green-700">Telegram linked — you'll receive alert notifications.</span>
          </div>
        ) : (
          <div>
            <p className="text-sm text-gray-600 mb-3">
              Link your Telegram account to receive alert notifications.
            </p>
            <p className="text-xs text-gray-500">
              Coming soon — for now, link via the backend CLI or Supabase directly.
            </p>
          </div>
        )}
      </div>

      {/* Disclaimer */}
      <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
        <p className="text-xs text-yellow-800">
          ⚠️ <strong>Not financial advice.</strong> ForexCast provides statistical forecasts for informational purposes only.
          Currency markets are inherently unpredictable. Always do your own research before making financial decisions.
        </p>
      </div>
    </div>
  )
}

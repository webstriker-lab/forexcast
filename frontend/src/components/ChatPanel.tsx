import { useState, useRef, useEffect } from 'react'
import { chat } from '../lib/apiClient'

interface Message {
  role: 'user' | 'assistant'
  content: string
  tool_calls?: { tool: string; arguments: Record<string, unknown>; result: unknown }[]
  // Local-only display message (a failed request) -- never sent back to
  // the model as conversation history, so an "Error: HTTP 400" string
  // can't end up being fed to the LLM as if it were something it said.
  isError?: boolean
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const userMsg: Message = { role: 'user', content: input.trim() }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setInput('')
    setLoading(true)

    try {
      const history = newMessages.filter(m => !m.isError).map(m => ({ role: m.role, content: m.content }))
      const res = await chat(history)
      const assistantMsg: Message = {
        role: 'assistant',
        content: res.message?.content || 'No response',
        tool_calls: res.tool_calls || [],
      }
      setMessages([...newMessages, assistantMsg])
    } catch (err) {
      setMessages([
        ...newMessages,
        {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          isError: true,
        },
      ])
    }
    setLoading(false)
  }

  return (
    <div className="flex flex-col h-[calc(100vh-10rem)] bg-white rounded-lg shadow">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 py-12">
            <p className="text-lg font-medium">ForexCast AI Assistant</p>
            <p className="text-sm mt-1">Ask about any currency pair — I'll check real data for you.</p>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {['What\'s the USD/INR forecast?', 'Should I buy EUR now?', 'Alert me if GBP drops below 1.25'].map(q => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="px-3 py-1.5 bg-gray-100 rounded-full text-sm text-gray-600 hover:bg-gray-200"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-md'
                  : 'bg-gray-100 text-gray-900 rounded-bl-md'
              }`}
            >
              <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
              {msg.tool_calls && msg.tool_calls.length > 0 && (
                <details className="mt-2 text-xs opacity-70">
                  <summary className="cursor-pointer">{msg.tool_calls.length} tool call(s)</summary>
                  <div className="mt-1 space-y-1">
                    {msg.tool_calls.map((tc, j) => (
                      <div key={j} className="font-mono text-[11px]">
                        {tc.tool}({JSON.stringify(tc.arguments)})
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-2.5 text-sm text-gray-500">
              <span className="animate-pulse">Thinking...</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t p-4">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Ask about any currency pair..."
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={loading}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="px-6 py-2.5 bg-blue-600 text-white rounded-full text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}

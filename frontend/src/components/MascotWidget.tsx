import { useState, useEffect } from 'react'

const MESSAGES = {
  welcome: [
    "Hey there! 👋 Ready to crush your financial goals?",
    "Welcome back! Let's check on your progress! 🦊",
    "Great to see you! Your finances are looking good! ✨",
  ],
  debtPaid: [
    "Amazing! You paid off a debt! 🎉",
    "One less debt! You're on fire! 🔥",
    "Debt eliminated! Keep up the great work! 💪",
  ],
  goalReached: [
    "You hit your savings goal! 🎊",
    "Goal achieved! Time to celebrate! 🥳",
    "Savings goal complete! You're a superstar! ⭐",
  ],
  streak: [
    "Nice streak! Keep it going! 🔥",
    "Consistency is key! You're doing great! 💪",
    "Another day, another step toward freedom! 🦊",
  ],
  tip: [
    "Tip: Check the forex rates before converting currency! 📊",
    "Tip: Set up alerts to catch the best rates! 🔔",
    "Tip: Use the AI chat to get personalized advice! 💬",
  ],
}

interface Props {
  context?: 'welcome' | 'debtPaid' | 'goalReached' | 'streak' | 'tip'
}

export function MascotWidget({ context = 'welcome' }: Props) {
  const [message, setMessage] = useState('')

  useEffect(() => {
    const messages = MESSAGES[context]
    setMessage(messages[Math.floor(Math.random() * messages.length)])
  }, [context])

  return (
    <div className="bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg shadow-lg p-6 text-white">
      <div className="flex items-center gap-4">
        <div className="text-6xl">🦊</div>
        <div>
          <h3 className="text-lg font-bold">Forex the Fox</h3>
          <p className="text-blue-100">{message}</p>
        </div>
      </div>
    </div>
  )
}

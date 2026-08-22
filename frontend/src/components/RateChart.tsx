import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js'
import type { RateRow } from '../hooks/useRates'
import type { Prediction } from '../hooks/usePredictions'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend)

interface Props {
  rates: RateRow[]
  predictions: Prediction[]
  pair: string
}

export function RateChart({ rates, predictions, pair }: Props) {
  if (rates.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-8 flex items-center justify-center text-gray-400 h-64">
        No rate data available for {pair}
      </div>
    )
  }

  const labels = rates.map(r => r.as_of)
  const data = rates.map(r => r.rate)
  const lastDate = rates[rates.length - 1]?.as_of

  // Add prediction points at future dates
  const predLabels = predictions.map(p => {
    const d = new Date(lastDate)
    d.setDate(d.getDate() + p.horizon_days)
    return d.toISOString().split('T')[0]
  })

  const allLabels = [...labels, ...predLabels]
  const historicalData = [...data, ...predictions.map(() => null)]
  const predictedData = [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.predicted_rate)]
  const upperData = [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.upper_bound)]
  const lowerData = [...Array(data.length - 1).fill(null), data[data.length - 1], ...predictions.map(p => p.lower_bound)]

  const chartData = {
    labels: allLabels,
    datasets: [
      {
        label: pair,
        data: historicalData,
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.05)',
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: 'Predicted',
        data: predictedData,
        borderColor: 'rgb(16, 185, 129)',
        borderDash: [6, 3],
        pointRadius: 5,
        pointBackgroundColor: predictions.map(p =>
          p.confidence === 'low' ? 'rgb(245, 158, 11)' : 'rgb(16, 185, 129)'
        ),
        borderWidth: 2,
      },
      {
        label: 'Upper bound',
        data: upperData,
        borderColor: 'rgba(16, 185, 129, 0.3)',
        borderDash: [2, 2],
        pointRadius: 0,
        fill: false,
        borderWidth: 1,
      },
      {
        label: 'Lower bound',
        data: lowerData,
        borderColor: 'rgba(16, 185, 129, 0.3)',
        borderDash: [2, 2],
        pointRadius: 0,
        fill: '-1',
        backgroundColor: 'rgba(16, 185, 129, 0.08)',
        borderWidth: 1,
      },
    ],
  }

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <Line
        data={chartData}
        options={{
          responsive: true,
          maintainAspectRatio: false,
          interaction: { intersect: false, mode: 'index' },
          plugins: {
            legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16 } },
            tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(4) ?? '—'}` } },
          },
          scales: {
            x: { display: true, ticks: { maxTicksLimit: 8, maxRotation: 0 } },
            y: { display: true },
          },
        }}
        height={300}
      />
    </div>
  )
}

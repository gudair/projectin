'use client'

import { useState, useEffect } from 'react'
import { BarChart3 } from 'lucide-react'

interface PerformanceChartProps {
  portfolioId?: string
}

export default function PerformanceChart({ portfolioId }: PerformanceChartProps) {
  const [chartData, setChartData] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Simulate loading data
    const timer = setTimeout(() => {
      // Mock data for demonstration
      const mockData = Array.from({ length: 30 }, (_, i) => ({
        date: new Date(Date.now() - (29 - i) * 24 * 60 * 60 * 1000).toLocaleDateString(),
        value: 10000 + Math.random() * 2000 - 1000,
        change: Math.random() * 200 - 100
      }))
      setChartData(mockData)
      setIsLoading(false)
    }, 1000)

    return () => clearTimeout(timer)
  }, [portfolioId])

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="h-64 bg-gray-200 rounded"></div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center mb-4">
        <BarChart3 className="h-5 w-5 text-gray-500 mr-2" />
        <h2 className="text-lg font-semibold">Performance Chart</h2>
      </div>

      <div className="h-64 flex items-end justify-between space-x-1">
        {chartData.slice(-20).map((point, index) => {
          const height = Math.max(10, (point.value / 12000) * 100)
          const isPositive = point.change >= 0

          return (
            <div key={index} className="flex flex-col items-center">
              <div
                className={`w-4 rounded-t ${
                  isPositive ? 'bg-green-500' : 'bg-red-500'
                }`}
                style={{ height: `${height}%` }}
                title={`${point.date}: $${point.value.toLocaleString()}`}
              />
              {index % 5 === 0 && (
                <span className="text-xs text-gray-500 mt-1 rotate-45 origin-left">
                  {point.date.split('/').slice(0, 2).join('/')}
                </span>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-4 flex justify-between text-sm text-gray-500">
        <span>30 days ago</span>
        <span>Today</span>
      </div>
    </div>
  )
}
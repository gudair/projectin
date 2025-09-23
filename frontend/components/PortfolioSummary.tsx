'use client'

import { DollarSign, TrendingUp, TrendingDown } from 'lucide-react'

interface Portfolio {
  id: string
  total_value: number
  daily_change: number
  daily_change_percent: number
  cash_balance: number
}

interface PortfolioSummaryProps {
  portfolio?: Portfolio | null
  isLoading: boolean
}

export default function PortfolioSummary({ portfolio, isLoading }: PortfolioSummaryProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/4 mb-4"></div>
          <div className="h-8 bg-gray-200 rounded w-1/2 mb-2"></div>
          <div className="h-4 bg-gray-200 rounded w-1/3"></div>
        </div>
      </div>
    )
  }

  if (!portfolio) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Portfolio Summary</h2>
        <p className="text-gray-500">No portfolio data available</p>
      </div>
    )
  }

  const isPositive = portfolio.daily_change >= 0

  return (
    <div className="trading-card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Portfolio Summary</h2>
        <div className="p-2 bg-gradient-to-r from-blue-500 to-purple-500 rounded-lg">
          <DollarSign className="h-6 w-6 text-white" />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="metric-card text-center">
          <div className="flex items-center justify-center mb-3">
            <div className="p-3 bg-gradient-to-r from-blue-500 to-cyan-500 rounded-full">
              <DollarSign className="h-6 w-6 text-white" />
            </div>
          </div>
          <p className="text-sm font-medium text-gray-600 mb-1">Total Value</p>
          <p className="text-3xl font-bold text-gray-900">
            ${portfolio.total_value.toLocaleString()}
          </p>
        </div>

        <div className="metric-card text-center">
          <div className="flex items-center justify-center mb-3">
            <div className={`p-3 rounded-full ${isPositive ? 'bg-gradient-to-r from-emerald-500 to-green-500' : 'bg-gradient-to-r from-red-500 to-pink-500'}`}>
              {isPositive ? (
                <TrendingUp className="h-6 w-6 text-white" />
              ) : (
                <TrendingDown className="h-6 w-6 text-white" />
              )}
            </div>
          </div>
          <p className="text-sm font-medium text-gray-600 mb-1">Daily Change</p>
          <p className={`text-3xl font-bold ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
            {isPositive ? '+' : ''}${Math.abs(portfolio.daily_change).toLocaleString()}
          </p>
          <p className={`text-sm font-semibold ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
            ({isPositive ? '+' : ''}{portfolio.daily_change_percent.toFixed(2)}%)
          </p>
        </div>

        <div className="metric-card text-center">
          <div className="flex items-center justify-center mb-3">
            <div className="p-3 bg-gradient-to-r from-purple-500 to-indigo-500 rounded-full">
              <DollarSign className="h-6 w-6 text-white" />
            </div>
          </div>
          <p className="text-sm font-medium text-gray-600 mb-1">Cash Balance</p>
          <p className="text-3xl font-bold text-gray-900">
            ${portfolio.cash_balance.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  )
}
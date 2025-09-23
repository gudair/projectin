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
  portfolio?: Portfolio
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
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Portfolio Summary</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            <DollarSign className="h-5 w-5 text-gray-500 mr-1" />
            <span className="text-sm text-gray-500">Total Value</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">
            ${portfolio.total_value.toLocaleString()}
          </p>
        </div>

        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            {isPositive ? (
              <TrendingUp className="h-5 w-5 text-green-500 mr-1" />
            ) : (
              <TrendingDown className="h-5 w-5 text-red-500 mr-1" />
            )}
            <span className="text-sm text-gray-500">Daily Change</span>
          </div>
          <p className={`text-2xl font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
            ${portfolio.daily_change.toLocaleString()}
          </p>
          <p className={`text-sm ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
            ({portfolio.daily_change_percent.toFixed(2)}%)
          </p>
        </div>

        <div className="text-center">
          <div className="flex items-center justify-center mb-2">
            <DollarSign className="h-5 w-5 text-gray-500 mr-1" />
            <span className="text-sm text-gray-500">Cash Balance</span>
          </div>
          <p className="text-2xl font-bold text-gray-900">
            ${portfolio.cash_balance.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  )
}
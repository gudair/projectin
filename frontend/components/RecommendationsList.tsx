'use client'

import { Star, TrendingUp, TrendingDown } from 'lucide-react'

interface Recommendation {
  id: string
  symbol: string
  recommendation: 'BUY' | 'SELL' | 'HOLD'
  target_price: number
  current_price: number
  reason: string
  analyst: string
  timestamp: string
}

interface RecommendationsListProps {
  recommendations?: Recommendation[]
  isLoading: boolean
}

export default function RecommendationsList({ recommendations, isLoading }: RecommendationsListProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="space-y-4">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="h-20 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  const getRecommendationColor = (type: string) => {
    switch (type) {
      case 'BUY':
        return 'text-green-600 bg-green-50 border-green-200'
      case 'SELL':
        return 'text-red-600 bg-red-50 border-red-200'
      default:
        return 'text-gray-600 bg-gray-50 border-gray-200'
    }
  }

  const getRecommendationIcon = (type: string) => {
    switch (type) {
      case 'BUY':
        return <TrendingUp className="h-4 w-4" />
      case 'SELL':
        return <TrendingDown className="h-4 w-4" />
      default:
        return <Star className="h-4 w-4" />
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Analyst Recommendations</h2>

      {!recommendations || recommendations.length === 0 ? (
        <p className="text-gray-500">No recommendations available</p>
      ) : (
        <div className="space-y-4">
          {recommendations.slice(0, 6).map((rec) => (
            <div
              key={rec.id}
              className={`p-4 rounded-lg border ${getRecommendationColor(rec.recommendation)}`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center">
                  {getRecommendationIcon(rec.recommendation)}
                  <h3 className="font-medium ml-2">{rec.symbol}</h3>
                </div>
                <span className="text-sm font-medium">
                  {rec.recommendation}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-2 text-sm">
                <div>
                  <span className="text-gray-600">Current: </span>
                  <span className="font-medium">${rec.current_price.toFixed(2)}</span>
                </div>
                <div>
                  <span className="text-gray-600">Target: </span>
                  <span className="font-medium">${rec.target_price.toFixed(2)}</span>
                </div>
              </div>

              <p className="text-sm text-gray-700 mb-2">{rec.reason}</p>
              <p className="text-xs text-gray-500">By {rec.analyst}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
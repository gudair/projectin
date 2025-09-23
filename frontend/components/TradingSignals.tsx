'use client'

import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

interface Signal {
  id: string
  symbol: string
  signal_type: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  price: number
  timestamp: string
}

interface TradingSignalsProps {
  signals?: Signal[]
  isLoading: boolean
}

export default function TradingSignals({ signals, isLoading }: TradingSignalsProps) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  const getSignalIcon = (type: string) => {
    switch (type) {
      case 'BUY':
        return <TrendingUp className="h-4 w-4 text-green-500" />
      case 'SELL':
        return <TrendingDown className="h-4 w-4 text-red-500" />
      default:
        return <Minus className="h-4 w-4 text-gray-500" />
    }
  }

  const getSignalColor = (type: string) => {
    switch (type) {
      case 'BUY':
        return 'text-green-600 bg-green-50'
      case 'SELL':
        return 'text-red-600 bg-red-50'
      default:
        return 'text-gray-600 bg-gray-50'
    }
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h2 className="text-lg font-semibold mb-4">Trading Signals</h2>

      {!signals || signals.length === 0 ? (
        <p className="text-gray-500">No trading signals available</p>
      ) : (
        <div className="space-y-3">
          {signals.slice(0, 5).map((signal) => (
            <div
              key={signal.id}
              className="flex items-center justify-between p-3 rounded-lg border"
            >
              <div className="flex items-center">
                {getSignalIcon(signal.signal_type)}
                <div className="ml-3">
                  <p className="font-medium">{signal.symbol}</p>
                  <p className="text-sm text-gray-500">
                    ${signal.price.toFixed(2)}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <span
                  className={`px-2 py-1 rounded-full text-xs font-medium ${getSignalColor(
                    signal.signal_type
                  )}`}
                >
                  {signal.signal_type}
                </span>
                <p className="text-xs text-gray-500 mt-1">
                  {signal.confidence}% confidence
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
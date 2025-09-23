'use client'

import { Clock, TrendingUp, TrendingDown } from 'lucide-react'

interface Trade {
  id: string
  symbol: string
  type: 'BUY' | 'SELL'
  quantity: number
  price: number
  timestamp: string
  profit_loss?: number
}

interface RecentTradesProps {
  trades?: Trade[] | null
}

export default function RecentTrades({ trades }: RecentTradesProps) {
  const getTradeIcon = (type: string) => {
    return type === 'BUY' ? (
      <TrendingUp className="h-4 w-4 text-green-500" />
    ) : (
      <TrendingDown className="h-4 w-4 text-red-500" />
    )
  }

  const getTradeColor = (type: string) => {
    return type === 'BUY' ? 'text-green-600' : 'text-red-600'
  }

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center mb-4">
        <Clock className="h-5 w-5 text-gray-500 mr-2" />
        <h2 className="text-lg font-semibold">Recent Trades</h2>
      </div>

      {!trades || trades.length === 0 ? (
        <p className="text-gray-500">No recent trades</p>
      ) : (
        <div className="space-y-3">
          {trades.slice(0, 10).map((trade) => (
            <div
              key={trade.id}
              className="flex items-center justify-between p-3 rounded-lg border hover:bg-gray-50"
            >
              <div className="flex items-center">
                {getTradeIcon(trade.type)}
                <div className="ml-3">
                  <div className="flex items-center">
                    <span className="font-medium">{trade.symbol}</span>
                    <span className={`ml-2 text-sm font-medium ${getTradeColor(trade.type)}`}>
                      {trade.type}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500">
                    {trade.quantity} shares @ ${trade.price.toFixed(2)}
                  </p>
                </div>
              </div>

              <div className="text-right">
                <p className="text-sm font-medium">
                  ${(trade.quantity * trade.price).toLocaleString()}
                </p>
                {trade.profit_loss !== undefined && (
                  <p className={`text-xs ${trade.profit_loss >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                    {trade.profit_loss >= 0 ? '+' : ''}${trade.profit_loss.toFixed(2)}
                  </p>
                )}
                <p className="text-xs text-gray-500">
                  {formatTime(trade.timestamp)}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
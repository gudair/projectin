'use client'

import { useState } from 'react'
import { ShoppingCart, TrendingUp, TrendingDown, Search, DollarSign } from 'lucide-react'

interface Stock {
  symbol: string
  name: string
  price: number
  change: number
  change_percent: number
}

interface TradingPanelProps {
  onTrade?: (symbol: string, type: 'BUY' | 'SELL', quantity: number, price: number) => void
}

export default function TradingPanel({ onTrade }: TradingPanelProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null)
  const [quantity, setQuantity] = useState(1)
  const [tradeType, setTradeType] = useState<'BUY' | 'SELL'>('BUY')

  // Mock popular stocks data
  const popularStocks: Stock[] = [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 175.50, change: 2.30, change_percent: 1.33 },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 2450.30, change: -15.20, change_percent: -0.62 },
    { symbol: 'MSFT', name: 'Microsoft Corp.', price: 380.20, change: 5.80, change_percent: 1.55 },
    { symbol: 'TSLA', name: 'Tesla Inc.', price: 215.30, change: -8.50, change_percent: -3.80 },
    { symbol: 'AMZN', name: 'Amazon.com Inc.', price: 145.20, change: 3.10, change_percent: 2.18 },
    { symbol: 'NVDA', name: 'NVIDIA Corp.', price: 875.45, change: 25.30, change_percent: 2.98 }
  ]

  const filteredStocks = popularStocks.filter(stock =>
    stock.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
    stock.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  const handleTrade = () => {
    if (selectedStock && quantity > 0) {
      onTrade?.(selectedStock.symbol, tradeType, quantity, selectedStock.price)
      // Reset form
      setQuantity(1)
      setSelectedStock(null)
      setSearchTerm('')
    }
  }

  const totalCost = selectedStock ? selectedStock.price * quantity : 0

  return (
    <div className="trading-card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Trading Panel</h2>
        <div className="p-2 bg-gradient-to-r from-emerald-500 to-green-500 rounded-lg">
          <ShoppingCart className="h-6 w-6 text-white" />
        </div>
      </div>

      {/* Search Stocks */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 h-5 w-5" />
          <input
            type="text"
            placeholder="Search stocks (AAPL, GOOGL, MSFT...)"
            className="w-full pl-10 pr-4 py-3 bg-gray-50 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {/* Stock List */}
      <div className="mb-6 max-h-64 overflow-y-auto">
        <div className="grid gap-2">
          {filteredStocks.map((stock) => {
            const isPositive = stock.change >= 0
            const isSelected = selectedStock?.symbol === stock.symbol

            return (
              <div
                key={stock.symbol}
                onClick={() => setSelectedStock(stock)}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-blue-50 border-blue-300 ring-2 ring-blue-500'
                    : 'bg-white border-gray-200 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-bold text-lg">{stock.symbol}</h3>
                    <p className="text-sm text-gray-600">{stock.name}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-bold text-lg">${stock.price.toFixed(2)}</p>
                    <div className={`flex items-center text-sm ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
                      {isPositive ? (
                        <TrendingUp className="h-4 w-4 mr-1" />
                      ) : (
                        <TrendingDown className="h-4 w-4 mr-1" />
                      )}
                      {isPositive ? '+' : ''}{stock.change.toFixed(2)} ({isPositive ? '+' : ''}{stock.change_percent.toFixed(2)}%)
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Trading Form */}
      {selectedStock && (
        <div className="bg-gray-50 rounded-lg p-6">
          <h3 className="font-bold text-lg mb-4">Trade {selectedStock.symbol}</h3>

          {/* Trade Type */}
          <div className="flex space-x-2 mb-4">
            <button
              onClick={() => setTradeType('BUY')}
              className={`flex-1 py-2 px-4 rounded-lg font-semibold transition-all ${
                tradeType === 'BUY'
                  ? 'btn-buy'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              BUY
            </button>
            <button
              onClick={() => setTradeType('SELL')}
              className={`flex-1 py-2 px-4 rounded-lg font-semibold transition-all ${
                tradeType === 'SELL'
                  ? 'btn-sell'
                  : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              }`}
            >
              SELL
            </button>
          </div>

          {/* Quantity */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Quantity
            </label>
            <input
              type="number"
              min="1"
              value={quantity}
              onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
              className="w-full py-2 px-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Total Cost */}
          <div className="mb-6 p-4 bg-white rounded-lg border">
            <div className="flex items-center justify-between">
              <span className="text-gray-600">Total {tradeType === 'BUY' ? 'Cost' : 'Value'}:</span>
              <div className="flex items-center">
                <DollarSign className="h-5 w-5 text-gray-500 mr-1" />
                <span className="text-xl font-bold">{totalCost.toLocaleString()}</span>
              </div>
            </div>
          </div>

          {/* Execute Trade Button */}
          <button
            onClick={handleTrade}
            className={`w-full py-3 px-6 rounded-lg font-bold text-white transition-all transform hover:scale-105 ${
              tradeType === 'BUY' ? 'btn-buy' : 'btn-sell'
            }`}
          >
            {tradeType === 'BUY' ? 'BUY' : 'SELL'} {quantity} {quantity === 1 ? 'share' : 'shares'} of {selectedStock.symbol}
          </button>
        </div>
      )}
    </div>
  )
}
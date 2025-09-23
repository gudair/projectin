'use client'

import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  BarChart3,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Clock
} from 'lucide-react'
import PortfolioSummary from '@/components/PortfolioSummary'
import TradingSignals from '@/components/TradingSignals'
import RecommendationsList from '@/components/RecommendationsList'
import PerformanceChart from '@/components/PerformanceChart'
import RecentTrades from '@/components/RecentTrades'
import MarketNews from '@/components/MarketNews'
import TradingPanel from '@/components/TradingPanel'
import { usePortfolio } from '@/hooks/usePortfolio'
import { useSignals } from '@/hooks/useSignals'
import { useRecommendations } from '@/hooks/useRecommendations'

export default function Dashboard() {
  const [isAutoRefresh, setIsAutoRefresh] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date())

  const {
    data: portfolio,
    isLoading: portfolioLoading,
    error: portfolioError,
    refetch: refetchPortfolio
  } = usePortfolio()

  const {
    data: signals,
    isLoading: signalsLoading,
    refetch: refetchSignals
  } = useSignals()

  const {
    data: recommendations,
    isLoading: recommendationsLoading,
    refetch: refetchRecommendations
  } = useRecommendations()

  // Auto refresh every 30 seconds
  useEffect(() => {
    if (!isAutoRefresh) return

    const interval = setInterval(() => {
      refetchPortfolio()
      refetchSignals()
      refetchRecommendations()
      setLastUpdated(new Date())
    }, 30000)

    return () => clearInterval(interval)
  }, [isAutoRefresh, refetchPortfolio, refetchSignals, refetchRecommendations])

  const handleManualRefresh = async () => {
    await Promise.all([
      refetchPortfolio(),
      refetchSignals(),
      refetchRecommendations()
    ])
    setLastUpdated(new Date())
  }

  const handleTrade = async (symbol: string, type: 'BUY' | 'SELL', quantity: number, price: number) => {
    try {
      // TODO: Integrate with real backend API
      console.log('Trade executed:', { symbol, type, quantity, price, total: quantity * price })

      // Simulate trade success
      alert(`${type} order placed for ${quantity} shares of ${symbol} at $${price.toFixed(2)} each. Total: $${(quantity * price).toLocaleString()}`)

      // Refresh portfolio data after trade
      await refetchPortfolio()
    } catch (error) {
      console.error('Trade failed:', error)
      alert('Trade failed. Please try again.')
    }
  }

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="glass border-b border-white/20 sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-20">
            <div className="flex items-center">
              <div className="p-2 bg-gradient-to-r from-emerald-500 to-blue-500 rounded-xl mr-4">
                <TrendingUp className="h-8 w-8 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold bg-gradient-to-r from-emerald-600 to-blue-600 bg-clip-text text-transparent">
                  Trading Simulator
                </h1>
                <p className="text-white/80 font-medium">Real-time Portfolio Dashboard</p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center text-sm text-white/70 bg-white/10 px-3 py-2 rounded-lg backdrop-blur-sm">
                <Clock className="h-4 w-4 mr-2" />
                Last updated: {formatTime(lastUpdated)}
              </div>

              <button
                onClick={() => setIsAutoRefresh(!isAutoRefresh)}
                className={`flex items-center px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  isAutoRefresh
                    ? 'bg-emerald-500/20 text-emerald-100 border border-emerald-400/30'
                    : 'bg-red-500/20 text-red-100 border border-red-400/30'
                }`}
              >
                {isAutoRefresh ? (
                  <>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Auto-refresh ON
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 mr-2" />
                    Auto-refresh OFF
                  </>
                )}
              </button>

              <button
                onClick={handleManualRefresh}
                className="btn-trading btn-primary"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {portfolioError && (
          <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 bg-red-50 border border-red-200 rounded-md p-4"
          >
            <div className="flex">
              <AlertCircle className="h-5 w-5 text-red-400 mr-2" />
              <div>
                <h3 className="text-sm font-medium text-red-800">
                  Error loading portfolio data
                </h3>
                <p className="mt-1 text-sm text-red-700">
                  Please check your connection and try refreshing the page.
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {/* Portfolio Summary */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="mb-8"
        >
          <PortfolioSummary
            portfolio={portfolio}
            isLoading={portfolioLoading}
          />
        </motion.div>

        {/* Trading Panel and Performance */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
          >
            <TradingPanel onTrade={handleTrade} />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
          >
            <PerformanceChart portfolioId={portfolio?.id} />
          </motion.div>
        </div>

        {/* Trading Signals */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <TradingSignals
            signals={signals}
            isLoading={signalsLoading}
          />
        </motion.div>

        {/* Recommendations and News */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="lg:col-span-2"
          >
            <RecommendationsList
              recommendations={recommendations}
              isLoading={recommendationsLoading}
            />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <MarketNews />
          </motion.div>
        </div>

        {/* Recent Trades */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
        >
          <RecentTrades trades={portfolio?.recent_trades} />
        </motion.div>

        {/* Footer */}
        <motion.footer
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="mt-12 text-center text-sm text-gray-500"
        >
          <p>Trading Simulator v1.0.0 - Educational Purposes Only</p>
          <p className="mt-1">
            Data updates every 30 seconds during market hours •
            Not financial advice •
            Past performance does not guarantee future results
          </p>
        </motion.footer>
      </main>
    </div>
  )
}
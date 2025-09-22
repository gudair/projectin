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

  const formatTime = (date: Date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <TrendingUp className="h-8 w-8 text-green-600 mr-3" />
              <div>
                <h1 className="text-2xl font-bold text-gray-900">Trading Simulator</h1>
                <p className="text-sm text-gray-500">Real-time Portfolio Dashboard</p>
              </div>
            </div>

            <div className="flex items-center space-x-4">
              <div className="flex items-center text-sm text-gray-500">
                <Clock className="h-4 w-4 mr-1" />
                Last updated: {formatTime(lastUpdated)}
              </div>

              <button
                onClick={() => setIsAutoRefresh(!isAutoRefresh)}
                className={`flex items-center px-3 py-1 rounded-md text-sm font-medium ${
                  isAutoRefresh
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {isAutoRefresh ? (
                  <>
                    <CheckCircle className="h-4 w-4 mr-1" />
                    Auto-refresh ON
                  </>
                ) : (
                  <>
                    <AlertCircle className="h-4 w-4 mr-1" />
                    Auto-refresh OFF
                  </>
                )}
              </button>

              <button
                onClick={handleManualRefresh}
                className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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

        {/* Charts and Performance */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
          >
            <PerformanceChart portfolioId={portfolio?.id} />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
          >
            <TradingSignals
              signals={signals}
              isLoading={signalsLoading}
            />
          </motion.div>
        </div>

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
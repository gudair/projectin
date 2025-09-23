'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/services/api'

interface Portfolio {
  id: string
  name: string
  initial_capital: number
  cash: number
  total_value: number
  total_return_percent: number
  positions_count: number
  created_at: string
  recent_trades?: any[]
}

export function usePortfolio() {
  const [data, setData] = useState<Portfolio | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchPortfolio = async () => {
    try {
      setIsLoading(true)
      setError(null)

      const response = await apiClient.getPortfolio()

      // DEBUG: Log the raw response
      console.log('🔍 Portfolio API Response:', response)

      if (response.error) {
        throw new Error(response.error)
      }

      if (response.data) {
        // DEBUG: Log the raw data from API
        console.log('📊 Raw Portfolio Data from API:', response.data)

        // Transform API response to match frontend interface
        const portfolioData: Portfolio = {
          id: response.data.id,
          name: response.data.name || 'Trading Simulator',
          initial_capital: response.data.initial_capital || 10000,
          cash: response.data.cash || 0,
          total_value: response.data.total_value || 0,
          total_return_percent: response.data.total_return_percent || 0,
          positions_count: response.data.positions_count || 0,
          created_at: response.data.created_at || new Date().toISOString(),
          recent_trades: []
        }

        // DEBUG: Log the transformed data
        console.log('✨ Transformed Portfolio Data:', portfolioData)
        setData(portfolioData)
      }
    } catch (err) {
      console.error('Portfolio fetch error:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch portfolio data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchPortfolio()
  }, [])

  const refetch = () => {
    return fetchPortfolio()
  }

  return {
    data,
    isLoading,
    error,
    refetch
  }
}
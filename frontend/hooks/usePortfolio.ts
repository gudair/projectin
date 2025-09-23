'use client'

import { useState, useEffect } from 'react'

interface Portfolio {
  id: string
  total_value: number
  daily_change: number
  daily_change_percent: number
  cash_balance: number
  recent_trades?: any[]
}

export function usePortfolio() {
  const [data, setData] = useState<Portfolio | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchPortfolio = async () => {
    try {
      setIsLoading(true)
      // Mock data for now
      const mockPortfolio: Portfolio = {
        id: '1',
        total_value: 12543.50,
        daily_change: 234.12,
        daily_change_percent: 1.9,
        cash_balance: 2543.50,
        recent_trades: []
      }

      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 1000))

      setData(mockPortfolio)
      setError(null)
    } catch (err) {
      setError('Failed to fetch portfolio data')
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
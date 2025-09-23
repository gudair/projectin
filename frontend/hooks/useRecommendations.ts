'use client'

import { useState, useEffect } from 'react'

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

export function useRecommendations() {
  const [data, setData] = useState<Recommendation[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchRecommendations = async () => {
    try {
      setIsLoading(true)
      // Mock data for now
      const mockRecommendations: Recommendation[] = [
        {
          id: '1',
          symbol: 'AAPL',
          recommendation: 'BUY',
          target_price: 190.00,
          current_price: 175.50,
          reason: 'Strong quarterly earnings and positive outlook for new product launches',
          analyst: 'Goldman Sachs',
          timestamp: new Date().toISOString()
        },
        {
          id: '2',
          symbol: 'TSLA',
          recommendation: 'HOLD',
          target_price: 220.00,
          current_price: 215.30,
          reason: 'Mixed signals on production targets, awaiting Q4 delivery numbers',
          analyst: 'Morgan Stanley',
          timestamp: new Date().toISOString()
        },
        {
          id: '3',
          symbol: 'AMZN',
          recommendation: 'BUY',
          target_price: 160.00,
          current_price: 145.20,
          reason: 'Cloud services growth and e-commerce recovery expected',
          analyst: 'JP Morgan',
          timestamp: new Date().toISOString()
        }
      ]

      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 900))

      setData(mockRecommendations)
      setError(null)
    } catch (err) {
      setError('Failed to fetch recommendations')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchRecommendations()
  }, [])

  const refetch = () => {
    return fetchRecommendations()
  }

  return {
    data,
    isLoading,
    error,
    refetch
  }
}
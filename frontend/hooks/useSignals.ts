'use client'

import { useState, useEffect } from 'react'

interface Signal {
  id: string
  symbol: string
  signal_type: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  price: number
  timestamp: string
}

export function useSignals() {
  const [data, setData] = useState<Signal[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchSignals = async () => {
    try {
      setIsLoading(true)
      // Mock data for now
      const mockSignals: Signal[] = [
        {
          id: '1',
          symbol: 'AAPL',
          signal_type: 'BUY',
          confidence: 85,
          price: 175.50,
          timestamp: new Date().toISOString()
        },
        {
          id: '2',
          symbol: 'GOOGL',
          signal_type: 'HOLD',
          confidence: 72,
          price: 2450.30,
          timestamp: new Date().toISOString()
        },
        {
          id: '3',
          symbol: 'MSFT',
          signal_type: 'SELL',
          confidence: 68,
          price: 380.20,
          timestamp: new Date().toISOString()
        }
      ]

      // Simulate API delay
      await new Promise(resolve => setTimeout(resolve, 800))

      setData(mockSignals)
      setError(null)
    } catch (err) {
      setError('Failed to fetch trading signals')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchSignals()
  }, [])

  const refetch = () => {
    return fetchSignals()
  }

  return {
    data,
    isLoading,
    error,
    refetch
  }
}
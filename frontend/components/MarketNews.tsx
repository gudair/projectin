'use client'

import { useState, useEffect } from 'react'
import { Newspaper, ExternalLink } from 'lucide-react'

interface NewsItem {
  id: string
  title: string
  summary: string
  url: string
  source: string
  timestamp: string
}

export default function MarketNews() {
  const [news, setNews] = useState<NewsItem[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    // Simulate loading news
    const timer = setTimeout(() => {
      // Mock news data
      const mockNews = [
        {
          id: '1',
          title: 'Tech Stocks Rally on Strong Earnings',
          summary: 'Major technology companies report better than expected quarterly results...',
          url: '#',
          source: 'Financial Times',
          timestamp: new Date(Date.now() - 1 * 60 * 60 * 1000).toISOString()
        },
        {
          id: '2',
          title: 'Federal Reserve Signals Interest Rate Changes',
          summary: 'Central bank hints at policy adjustments in upcoming meeting...',
          url: '#',
          source: 'Reuters',
          timestamp: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString()
        },
        {
          id: '3',
          title: 'Oil Prices Surge on Supply Concerns',
          summary: 'Crude oil futures jump as geopolitical tensions affect supply chains...',
          url: '#',
          source: 'Bloomberg',
          timestamp: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString()
        }
      ]
      setNews(mockNews)
      setIsLoading(false)
    }, 800)

    return () => clearTimeout(timer)
  }, [])

  const formatTimeAgo = (timestamp: string) => {
    const now = new Date()
    const time = new Date(timestamp)
    const diffInHours = Math.floor((now.getTime() - time.getTime()) / (1000 * 60 * 60))

    if (diffInHours < 1) return 'Just now'
    if (diffInHours === 1) return '1 hour ago'
    return `${diffInHours} hours ago`
  }

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="space-y-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-20 bg-gray-200 rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center mb-4">
        <Newspaper className="h-5 w-5 text-gray-500 mr-2" />
        <h2 className="text-lg font-semibold">Market News</h2>
      </div>

      <div className="space-y-4">
        {news.map((item) => (
          <div key={item.id} className="border-b border-gray-100 pb-4 last:border-b-0">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h3 className="font-medium text-gray-900 mb-1 line-clamp-2">
                  {item.title}
                </h3>
                <p className="text-sm text-gray-600 mb-2 line-clamp-2">
                  {item.summary}
                </p>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>{item.source}</span>
                  <span>{formatTimeAgo(item.timestamp)}</span>
                </div>
              </div>
              <button className="ml-2 p-1 text-gray-400 hover:text-gray-600">
                <ExternalLink className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 text-center">
        <button className="text-sm text-blue-600 hover:text-blue-800">
          View more news
        </button>
      </div>
    </div>
  )
}
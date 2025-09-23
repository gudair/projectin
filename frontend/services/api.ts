const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

console.log('🔧 Environment variable NEXT_PUBLIC_API_URL:', process.env.NEXT_PUBLIC_API_URL)
console.log('🔧 Using API_BASE_URL:', API_BASE_URL)

interface ApiResponse<T> {
  data?: T
  error?: string
}

class ApiClient {
  private baseURL: string

  constructor(baseURL: string = API_BASE_URL) {
    this.baseURL = baseURL
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<ApiResponse<T>> {
    try {
      const url = `${this.baseURL}${endpoint}`
      console.log('🌐 API Request URL:', url)
      console.log('🌐 API Base URL:', this.baseURL)
      console.log('🌐 Full fetch options:', { headers: { 'Content-Type': 'application/json', ...options.headers }, ...options })

      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
        ...options,
      })

      console.log('📡 Response status:', response.status)
      console.log('📡 Response headers:', Object.fromEntries(response.headers.entries()))

      if (!response.ok) {
        const errorText = await response.text()
        console.error('❌ API Error:', response.status, errorText)
        throw new Error(`HTTP ${response.status}: ${errorText}`)
      }

      const data = await response.json()
      console.log('✅ API Response data:', data)
      return { data }
    } catch (error) {
      console.error('💥 API Request failed:', error)
      return { error: error instanceof Error ? error.message : 'Unknown error' }
    }
  }

  // Portfolio endpoints
  async getPortfolio() {
    return this.request('/api/v1/portfolio/')
  }

  async getPortfolioPositions() {
    return this.request('/api/v1/portfolio/positions')
  }

  async getPortfolioPerformance(days: number = 30) {
    return this.request(`/api/v1/performance/?days=${days}`)
  }

  // Trading endpoints
  async createTrade(trade: {
    symbol: string
    side: 'BUY' | 'SELL'
    quantity: number
    price: number
    trade_type?: 'MARKET' | 'LIMIT'
  }) {
    return this.request('/api/v1/trades/', {
      method: 'POST',
      body: JSON.stringify(trade),
    })
  }

  async getTrades() {
    return this.request('/api/v1/trades/')
  }

  // Market data endpoints
  async getMarketData(symbol: string) {
    return this.request(`/api/v1/market/price/${symbol}`)
  }

  async searchStocks(query: string) {
    return this.request(`/api/v1/market/search?q=${encodeURIComponent(query)}`)
  }

  // Signals endpoints
  async getTradingSignals() {
    return this.request('/api/v1/signals/')
  }

  // Recommendations endpoints
  async getRecommendations() {
    return this.request('/api/v1/recommendations/')
  }

  // Health check
  async healthCheck() {
    return this.request('/health')
  }
}

export const apiClient = new ApiClient()
export default apiClient
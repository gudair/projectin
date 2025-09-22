import yfinance as yf
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, List, Optional, Tuple
from config.settings import ALPHA_VANTAGE_API_KEY, WATCHLIST, INITIAL_STOCK

class MarketDataCollector:
    def __init__(self):
        self.alpha_vantage_key = ALPHA_VANTAGE_API_KEY
        self.base_url = "https://www.alphavantage.co/query"
        self.logger = logging.getLogger(__name__)

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current stock price using yfinance"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="1m")
            if not data.empty:
                return float(data['Close'].iloc[-1])
            return None
        except Exception as e:
            self.logger.error(f"Error getting current price for {symbol}: {e}")
            return None

    def get_intraday_data(self, symbol: str, interval: str = "5min") -> pd.DataFrame:
        """Get intraday data for technical analysis"""
        try:
            # Try yfinance first (free)
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval=interval)

            if data.empty:
                # Fallback to Alpha Vantage
                return self._get_alpha_vantage_intraday(symbol, interval)

            return data

        except Exception as e:
            self.logger.error(f"Error getting intraday data for {symbol}: {e}")
            return pd.DataFrame()

    def _get_alpha_vantage_intraday(self, symbol: str, interval: str) -> pd.DataFrame:
        """Backup data source using Alpha Vantage"""
        try:
            url = f"{self.base_url}?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval={interval}&apikey={self.alpha_vantage_key}"
            response = requests.get(url)
            data = response.json()

            if f"Time Series ({interval})" in data:
                df = pd.DataFrame(data[f"Time Series ({interval})"]).T
                df.index = pd.to_datetime(df.index)
                df = df.astype(float)
                df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
                return df.sort_index()

            return pd.DataFrame()

        except Exception as e:
            self.logger.error(f"Error with Alpha Vantage for {symbol}: {e}")
            return pd.DataFrame()

    def get_technical_indicators(self, symbol: str) -> Dict:
        """Get technical indicators for the symbol"""
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="3mo")  # 3 months for indicators

            if data.empty:
                return {}

            # Calculate indicators
            indicators = {}

            # Moving Averages
            indicators['sma_20'] = data['Close'].rolling(window=20).mean().iloc[-1]
            indicators['sma_50'] = data['Close'].rolling(window=50).mean().iloc[-1]
            indicators['ema_12'] = data['Close'].ewm(span=12).mean().iloc[-1]
            indicators['ema_26'] = data['Close'].ewm(span=26).mean().iloc[-1]

            # RSI
            indicators['rsi'] = self._calculate_rsi(data['Close'])

            # MACD
            macd_line, signal_line = self._calculate_macd(data['Close'])
            indicators['macd'] = macd_line
            indicators['macd_signal'] = signal_line
            indicators['macd_histogram'] = macd_line - signal_line

            # Bollinger Bands
            bb_upper, bb_lower = self._calculate_bollinger_bands(data['Close'])
            indicators['bb_upper'] = bb_upper
            indicators['bb_lower'] = bb_lower
            indicators['bb_width'] = (bb_upper - bb_lower) / data['Close'].iloc[-1]

            # Volume indicators
            indicators['volume_sma'] = data['Volume'].rolling(window=20).mean().iloc[-1]
            indicators['volume_ratio'] = data['Volume'].iloc[-1] / indicators['volume_sma']

            # Price position
            indicators['current_price'] = data['Close'].iloc[-1]
            indicators['daily_change'] = (data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]

            return indicators

        except Exception as e:
            self.logger.error(f"Error calculating technical indicators for {symbol}: {e}")
            return {}

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50

    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[float, float]:
        """Calculate MACD"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        return macd_line.iloc[-1], signal_line.iloc[-1]

    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[float, float]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band.iloc[-1], lower_band.iloc[-1]

    def get_market_snapshot(self) -> Dict:
        """Get complete market snapshot for all watched stocks"""
        snapshot = {}
        symbols = [INITIAL_STOCK] + WATCHLIST

        for symbol in symbols:
            try:
                price = self.get_current_price(symbol)
                indicators = self.get_technical_indicators(symbol)

                snapshot[symbol] = {
                    'current_price': price,
                    'timestamp': datetime.now(),
                    **indicators
                }

                # Rate limiting
                time.sleep(0.1)

            except Exception as e:
                self.logger.error(f"Error getting snapshot for {symbol}: {e}")

        return snapshot

    def get_options_flow(self, symbol: str) -> Dict:
        """Get basic options data (limited with free APIs)"""
        try:
            ticker = yf.Ticker(symbol)
            options_dates = ticker.options

            if options_dates:
                # Get nearest expiration
                nearest_exp = options_dates[0]
                option_chain = ticker.option_chain(nearest_exp)

                calls = option_chain.calls
                puts = option_chain.puts

                # Calculate put/call ratio
                total_call_volume = calls['volume'].fillna(0).sum()
                total_put_volume = puts['volume'].fillna(0).sum()
                put_call_ratio = total_put_volume / total_call_volume if total_call_volume > 0 else 0

                return {
                    'put_call_ratio': put_call_ratio,
                    'total_call_volume': total_call_volume,
                    'total_put_volume': total_put_volume,
                    'expiration': nearest_exp
                }

        except Exception as e:
            self.logger.error(f"Error getting options data for {symbol}: {e}")

        return {}

if __name__ == "__main__":
    # Test the collector
    collector = MarketDataCollector()
    print("Testing TSLA data collection...")

    price = collector.get_current_price("TSLA")
    print(f"TSLA Current Price: ${price}")

    indicators = collector.get_technical_indicators("TSLA")
    print(f"TSLA RSI: {indicators.get('rsi', 'N/A')}")
    print(f"TSLA MACD: {indicators.get('macd', 'N/A')}")

    snapshot = collector.get_market_snapshot()
    print(f"Market snapshot collected for {len(snapshot)} symbols")
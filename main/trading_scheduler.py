import schedule
import time
import logging
import threading
from datetime import datetime, time as dt_time
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.portfolio_manager import PortfolioManager
from signals.signal_generator import SignalGenerator
from analytics.recommendation_engine import RecommendationEngine
from data.collectors.market_data import MarketDataCollector
from data.collectors.news_collector import NewsCollector
from config.settings import (
    MARKET_OPEN, MARKET_CLOSE, PRE_MARKET_START, AFTER_HOURS_END,
    DATA_UPDATE_INTERVAL, SIGNAL_UPDATE_INTERVAL, PORTFOLIO_UPDATE_INTERVAL,
    LOG_FILE, LOG_LEVEL
)

class TradingScheduler:
    def __init__(self):
        self.setup_logging()
        self.logger = logging.getLogger(__name__)

        # Initialize components
        self.portfolio_manager = PortfolioManager()
        self.signal_generator = SignalGenerator()
        self.recommendation_engine = RecommendationEngine()
        self.market_data = MarketDataCollector()
        self.news_collector = NewsCollector()

        # Control flags
        self.running = False
        self.dashboard_thread = None

        self.logger.info("Trading Scheduler initialized")

    def setup_logging(self):
        """Setup logging configuration"""
        os.makedirs('logs', exist_ok=True)

        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(LOG_FILE),
                logging.StreamHandler()
            ]
        )

    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        now = datetime.now().time()
        market_open = dt_time.fromisoformat(MARKET_OPEN)
        market_close = dt_time.fromisoformat(MARKET_CLOSE)

        return market_open <= now <= market_close

    def is_extended_hours(self) -> bool:
        """Check if current time is within extended trading hours"""
        now = datetime.now().time()
        pre_market = dt_time.fromisoformat(PRE_MARKET_START)
        after_hours = dt_time.fromisoformat(AFTER_HOURS_END)

        return pre_market <= now <= after_hours

    def update_market_data(self):
        """Update market data for all tracked symbols"""
        try:
            self.logger.info("Updating market data...")
            market_snapshot = self.market_data.get_market_snapshot()

            if market_snapshot:
                # Update portfolio with current prices
                self.portfolio_manager.update_positions(market_snapshot)
                self.logger.info(f"Updated market data for {len(market_snapshot)} symbols")
            else:
                self.logger.warning("No market data received")

        except Exception as e:
            self.logger.error(f"Error updating market data: {e}")

    def update_portfolio(self):
        """Update portfolio calculations and daily P&L"""
        try:
            self.logger.info("Updating portfolio...")
            self.portfolio_manager.update_daily_pnl()

            # Get portfolio summary
            summary = self.portfolio_manager.get_portfolio_summary()
            self.logger.info(f"Portfolio Value: ${summary['total_value']:.2f}, "
                           f"Daily P&L: ${summary['daily_pnl']:.2f}, "
                           f"Total Return: {summary['total_return_percent']:.2f}%")

        except Exception as e:
            self.logger.error(f"Error updating portfolio: {e}")

    def generate_signals(self):
        """Generate trading signals for all symbols"""
        try:
            self.logger.info("Generating trading signals...")
            signals = self.signal_generator.generate_watchlist_signals()

            # Log key signals
            actionable_signals = [s for s in signals.values() if s.signal_type.value != 'hold']
            self.logger.info(f"Generated {len(actionable_signals)} actionable signals out of {len(signals)} total")

            for signal in actionable_signals:
                self.logger.info(f"{signal.symbol}: {signal.signal_type.value} "
                               f"(confidence: {signal.confidence:.2f}, strength: {signal.strength:.2f})")

        except Exception as e:
            self.logger.error(f"Error generating signals: {e}")

    def generate_recommendations(self):
        """Generate daily trading recommendations"""
        try:
            self.logger.info("Generating recommendations...")
            recommendations = self.recommendation_engine.get_daily_recommendations()

            summary = recommendations['summary']
            self.logger.info(f"Generated {summary['total_recommendations']} recommendations: "
                           f"{summary['buy_recommendations']} buy, "
                           f"{summary['sell_recommendations']} sell, "
                           f"{summary['adjustment_recommendations']} adjustments")

            # Log high priority recommendations
            for rec in recommendations['high_priority']:
                self.logger.info(f"HIGH PRIORITY: {rec['action'].upper()} {rec['shares']:.4f} "
                               f"{rec['symbol']} @ ${rec['current_price']:.2f} - {rec['reasoning']}")

        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")

    def collect_news(self):
        """Collect and analyze news for portfolio positions"""
        try:
            self.logger.info("Collecting news...")

            # Get portfolio positions
            portfolio_summary = self.portfolio_manager.get_portfolio_summary()
            symbols = list(portfolio_summary['positions'].keys())

            total_articles = 0
            for symbol in symbols:
                news = self.news_collector.get_stock_news(symbol, hours_back=6)
                total_articles += len(news)

                if news:
                    self.logger.info(f"Collected {len(news)} news articles for {symbol}")

            self.logger.info(f"Total articles collected: {total_articles}")

        except Exception as e:
            self.logger.error(f"Error collecting news: {e}")

    def morning_routine(self):
        """Pre-market morning routine"""
        self.logger.info("🌅 Starting morning routine...")

        # Update market data
        self.update_market_data()

        # Collect overnight news
        self.collect_news()

        # Generate signals and recommendations
        self.generate_signals()
        self.generate_recommendations()

        self.logger.info("✅ Morning routine completed")

    def market_hours_routine(self):
        """Regular market hours updates"""
        if not self.is_market_hours():
            return

        self.logger.debug("📈 Market hours routine...")

        # Quick updates during market hours
        self.update_market_data()
        self.update_portfolio()

    def evening_routine(self):
        """After-market evening routine"""
        self.logger.info("🌙 Starting evening routine...")

        # Final updates
        self.update_market_data()
        self.update_portfolio()

        # Generate end-of-day reports
        self.generate_signals()
        self.generate_recommendations()

        # Portfolio summary
        summary = self.portfolio_manager.get_portfolio_summary()
        self.logger.info(f"📊 End of day portfolio: ${summary['total_value']:.2f} "
                        f"(Daily P&L: ${summary['daily_pnl']:.2f})")

        self.logger.info("✅ Evening routine completed")

    def setup_schedule(self):
        """Setup the trading schedule"""
        self.logger.info("Setting up trading schedule...")

        # Morning routine (before market open)
        schedule.every().day.at("08:30").do(self.morning_routine)

        # Market hours updates (every 5 minutes during market hours)
        for hour in range(9, 17):  # 9 AM to 4 PM
            for minute in range(0, 60, PORTFOLIO_UPDATE_INTERVAL):
                time_str = f"{hour:02d}:{minute:02d}"
                schedule.every().day.at(time_str).do(self.market_hours_routine)

        # Signal updates (every 5 minutes during market hours)
        for hour in range(9, 17):
            for minute in range(0, 60, SIGNAL_UPDATE_INTERVAL):
                time_str = f"{hour:02d}:{minute:02d}"
                schedule.every().day.at(time_str).do(self.generate_signals)

        # Evening routine (after market close)
        schedule.every().day.at("17:30").do(self.evening_routine)

        # News collection (every 2 hours)
        schedule.every(2).hours.do(self.collect_news)

        self.logger.info("Schedule configured successfully")

    def start_dashboard(self):
        """Start the dashboard in a separate thread"""
        try:
            from dashboard.trading_dashboard import TradingDashboard

            dashboard = TradingDashboard()
            dashboard.run()

        except Exception as e:
            self.logger.error(f"Error starting dashboard: {e}")

    def start(self):
        """Start the trading scheduler"""
        self.logger.info("🚀 Starting Trading Scheduler...")

        # Setup schedule
        self.setup_schedule()

        # Start dashboard in separate thread
        self.dashboard_thread = threading.Thread(target=self.start_dashboard, daemon=True)
        self.dashboard_thread.start()
        self.logger.info("Dashboard started in background")

        # Run initial morning routine if it's early
        current_time = datetime.now().time()
        if current_time < dt_time(9, 30):  # Before market open
            self.morning_routine()

        self.running = True
        self.logger.info("Trading Scheduler is running...")

        try:
            while self.running:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds

        except KeyboardInterrupt:
            self.logger.info("Received shutdown signal")
            self.stop()

    def stop(self):
        """Stop the trading scheduler"""
        self.logger.info("🛑 Stopping Trading Scheduler...")
        self.running = False

        # Final portfolio update
        try:
            self.update_portfolio()
            summary = self.portfolio_manager.get_portfolio_summary()
            self.logger.info(f"Final portfolio value: ${summary['total_value']:.2f}")
        except Exception as e:
            self.logger.error(f"Error in final update: {e}")

        self.logger.info("Trading Scheduler stopped")

    def run_manual_update(self):
        """Run a manual update cycle (for testing)"""
        self.logger.info("🔄 Running manual update cycle...")

        self.update_market_data()
        self.update_portfolio()
        self.collect_news()
        self.generate_signals()
        self.generate_recommendations()

        self.logger.info("✅ Manual update completed")

def main():
    """Main entry point"""
    scheduler = TradingScheduler()

    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--manual":
            scheduler.run_manual_update()
            return
        elif sys.argv[1] == "--dashboard-only":
            # Run only dashboard
            from dashboard.trading_dashboard import TradingDashboard
            dashboard = TradingDashboard()
            dashboard.run()
            return

    # Start normal scheduler
    scheduler.start()

if __name__ == "__main__":
    main()
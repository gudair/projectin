#!/usr/bin/env python3
"""
Trading Simulator - Main Entry Point

A comprehensive stock trading simulation system with:
- Real-time market data collection
- Automated trading signal generation
- News sentiment analysis
- Portfolio management with $200 starting Tesla position
- Web dashboard for monitoring
- Daily trading recommendations
- Performance tracking

Author: Trading Simulator
Version: 1.0.0
"""

import sys
import os
import argparse
import logging
from datetime import datetime

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def setup_logging():
    """Setup basic logging"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def run_dashboard():
    """Run the web dashboard"""
    from dashboard.trading_dashboard import TradingDashboard

    print("🚀 Starting Trading Dashboard...")
    print("📊 Dashboard will be available at: http://127.0.0.1:8050")
    print("🔄 Data updates every 30 seconds")
    print("💡 Press Ctrl+C to stop")

    dashboard = TradingDashboard()
    dashboard.run()

def run_scheduler():
    """Run the full trading scheduler"""
    from main.trading_scheduler import TradingScheduler

    print("🚀 Starting Trading Scheduler...")
    print("📈 Market data collection: Every 5 minutes during market hours")
    print("🎯 Signal generation: Every 5 minutes during market hours")
    print("📰 News collection: Every 2 hours")
    print("📊 Dashboard: http://127.0.0.1:8050")
    print("💡 Press Ctrl+C to stop")

    scheduler = TradingScheduler()
    scheduler.start()

def run_manual_update():
    """Run a single manual update cycle"""
    from main.trading_scheduler import TradingScheduler

    print("🔄 Running manual update...")
    scheduler = TradingScheduler()
    scheduler.run_manual_update()

def show_portfolio():
    """Show current portfolio status"""
    from portfolio.portfolio_manager import PortfolioManager
    from analytics.performance_tracker import PerformanceTracker

    portfolio = PortfolioManager()
    tracker = PerformanceTracker(portfolio)

    # Update with current market data
    from data.collectors.market_data import MarketDataCollector
    market_data = MarketDataCollector()
    snapshot = market_data.get_market_snapshot()
    portfolio.update_positions(snapshot)

    # Get summary
    summary = portfolio.get_portfolio_summary()
    report = tracker.generate_performance_report()

    print("📊 Portfolio Summary:")
    print(f"   Total Value: ${summary['total_value']:.2f}")
    print(f"   Cash: ${summary['cash']:.2f}")
    print(f"   Daily P&L: ${summary['daily_pnl']:.2f}")
    print(f"   Total Return: {summary['total_return_percent']:.2f}%")
    print(f"   Positions: {summary['positions_count']}")

    print("\n📈 Performance Metrics:")
    metrics = report['performance_metrics']
    print(f"   Annualized Return: {metrics['annualized_return_percent']:.2f}%")
    print(f"   Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
    print(f"   Max Drawdown: {metrics['max_drawdown_percent']:.2f}%")
    print(f"   Days Active: {metrics['days_active']}")

    print("\n💼 Current Positions:")
    for symbol, pos in summary['positions'].items():
        print(f"   {symbol}: {pos['shares']:.6f} shares @ ${pos['current_price']:.2f}")
        print(f"      Value: ${pos['current_value']:.2f} | P&L: ${pos['unrealized_pnl']:.2f} ({pos['unrealized_pnl_percent']:.2f}%)")

def show_recommendations():
    """Show current trading recommendations"""
    from analytics.recommendation_engine import RecommendationEngine

    engine = RecommendationEngine()
    recommendations = engine.get_daily_recommendations()

    summary = recommendations['summary']
    print("🎯 Trading Recommendations:")
    print(f"   Total: {summary['total_recommendations']}")
    print(f"   Buy: {summary['buy_recommendations']}")
    print(f"   Sell: {summary['sell_recommendations']}")
    print(f"   Adjustments: {summary['adjustment_recommendations']}")

    if recommendations['high_priority']:
        print("\n🔥 High Priority Recommendations:")
        for rec in recommendations['high_priority']:
            action_emoji = "📈" if 'buy' in rec['action'] else "📉" if 'sell' in rec['action'] else "⚖️"
            print(f"   {action_emoji} {rec['action'].upper()} {rec['shares']:.4f} {rec['symbol']} @ ${rec['current_price']:.2f}")
            print(f"      Investment: ${rec['investment_amount']:.2f}")
            print(f"      Expected Return: {rec['expected_return']}")
            print(f"      Confidence: {rec['confidence']}")
            print(f"      Reason: {rec['reasoning']}")
            print()

def show_signals():
    """Show current trading signals"""
    from signals.signal_generator import SignalGenerator

    generator = SignalGenerator()
    signals = generator.generate_watchlist_signals()
    top_opportunities = generator.get_top_opportunities(signals, limit=5)

    print("🎯 Current Trading Signals:")

    for signal in top_opportunities:
        signal_emoji = "📈" if 'buy' in signal.signal_type.value else "📉" if 'sell' in signal.signal_type.value else "⚠️"
        print(f"   {signal_emoji} {signal.symbol}: {signal.signal_type.value.upper().replace('_', ' ')}")
        print(f"      Confidence: {signal.confidence:.1%} | Strength: {signal.strength:.2f}")
        if signal.target_price:
            print(f"      Target: ${signal.target_price:.2f}")
        if signal.stop_loss:
            print(f"      Stop Loss: ${signal.stop_loss:.2f}")
        print(f"      Reasoning: {signal.reasoning}")
        print()

def run_setup():
    """Setup the trading simulator"""
    print("🔧 Setting up Trading Simulator...")

    # Create necessary directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('analytics', exist_ok=True)
    os.makedirs('portfolio', exist_ok=True)

    # Create .env file if it doesn't exist
    if not os.path.exists('.env'):
        print("📝 Creating .env file...")
        with open('.env', 'w') as f:
            f.write("# Trading Simulator Environment Variables\n")
            f.write("# Get free API keys from:\n")
            f.write("# Alpha Vantage: https://www.alphavantage.co/support/#api-key\n")
            f.write("# NewsAPI: https://newsapi.org/register\n\n")
            f.write("ALPHA_VANTAGE_API_KEY=demo\n")
            f.write("NEWS_API_KEY=demo\n")

    print("✅ Setup complete!")
    print("\n📋 Next steps:")
    print("1. Get free API keys:")
    print("   - Alpha Vantage: https://www.alphavantage.co/support/#api-key")
    print("   - NewsAPI: https://newsapi.org/register")
    print("2. Update the .env file with your API keys")
    print("3. Install dependencies: pip install -r requirements.txt")
    print("4. Run the simulator: python main.py --dashboard")

def main():
    """Main entry point"""
    setup_logging()

    parser = argparse.ArgumentParser(description='Trading Simulator - Stock Trading Simulation System')
    parser.add_argument('--dashboard', action='store_true', help='Run web dashboard only')
    parser.add_argument('--scheduler', action='store_true', help='Run full trading scheduler with dashboard')
    parser.add_argument('--portfolio', action='store_true', help='Show current portfolio status')
    parser.add_argument('--recommendations', action='store_true', help='Show trading recommendations')
    parser.add_argument('--signals', action='store_true', help='Show current trading signals')
    parser.add_argument('--update', action='store_true', help='Run manual data update')
    parser.add_argument('--setup', action='store_true', help='Setup the trading simulator')

    args = parser.parse_args()

    # Print header
    print("=" * 60)
    print("🚀 TRADING SIMULATOR")
    print("=" * 60)
    print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("💰 Starting Capital: $200 (Tesla Position)")
    print("📊 Simulation Mode: Paper Trading Only")
    print("=" * 60)

    try:
        if args.setup:
            run_setup()
        elif args.dashboard:
            run_dashboard()
        elif args.scheduler:
            run_scheduler()
        elif args.portfolio:
            show_portfolio()
        elif args.recommendations:
            show_recommendations()
        elif args.signals:
            show_signals()
        elif args.update:
            run_manual_update()
        else:
            # Default: show help and current status
            parser.print_help()
            print("\n" + "=" * 60)
            print("📊 Quick Status Check:")
            print("=" * 60)

            try:
                show_portfolio()
            except Exception as e:
                print(f"⚠️  Error loading portfolio: {e}")
                print("💡 Try running: python main.py --setup")

    except KeyboardInterrupt:
        print("\n👋 Trading Simulator stopped by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Try running: python main.py --setup")

if __name__ == "__main__":
    main()
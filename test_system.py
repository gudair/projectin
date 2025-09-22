#!/usr/bin/env python3
"""
Test script to verify all Trading Simulator components work correctly
"""

import sys
import os
import logging

# Add current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all modules can be imported"""
    print("🔍 Testing imports...")

    try:
        from config.settings import INITIAL_CAPITAL, INITIAL_STOCK
        print("✅ Config module imported")

        from data.collectors.market_data import MarketDataCollector
        print("✅ Market data collector imported")

        from data.collectors.news_collector import NewsCollector
        print("✅ News collector imported")

        from data.processors.sentiment_analyzer import SentimentAnalyzer
        print("✅ Sentiment analyzer imported")

        from portfolio.portfolio_manager import PortfolioManager
        print("✅ Portfolio manager imported")

        from signals.signal_generator import SignalGenerator
        print("✅ Signal generator imported")

        from analytics.recommendation_engine import RecommendationEngine
        print("✅ Recommendation engine imported")

        from analytics.performance_tracker import PerformanceTracker
        print("✅ Performance tracker imported")

        return True

    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

def test_market_data():
    """Test market data collection"""
    print("\n📊 Testing market data collection...")

    try:
        from data.collectors.market_data import MarketDataCollector

        collector = MarketDataCollector()

        # Test current price
        price = collector.get_current_price("TSLA")
        if price and price > 0:
            print(f"✅ TSLA current price: ${price:.2f}")
        else:
            print("⚠️  Could not get TSLA price (may be market closed)")

        # Test technical indicators
        indicators = collector.get_technical_indicators("TSLA")
        if indicators:
            print(f"✅ Technical indicators: RSI={indicators.get('rsi', 'N/A'):.1f}")
        else:
            print("⚠️  Could not get technical indicators")

        return True

    except Exception as e:
        print(f"❌ Market data error: {e}")
        return False

def test_portfolio():
    """Test portfolio management"""
    print("\n💼 Testing portfolio management...")

    try:
        from portfolio.portfolio_manager import PortfolioManager

        portfolio = PortfolioManager()
        summary = portfolio.get_portfolio_summary()

        print(f"✅ Portfolio initialized: ${summary['total_value']:.2f}")
        print(f"   Cash: ${summary['cash']:.2f}")
        print(f"   Positions: {summary['positions_count']}")

        if 'TSLA' in summary['positions']:
            tsla_pos = summary['positions']['TSLA']
            print(f"   TSLA: {tsla_pos['shares']:.6f} shares @ ${tsla_pos['current_price']:.2f}")

        return True

    except Exception as e:
        print(f"❌ Portfolio error: {e}")
        return False

def test_signals():
    """Test signal generation"""
    print("\n🎯 Testing signal generation...")

    try:
        from signals.signal_generator import SignalGenerator

        generator = SignalGenerator()
        signal = generator.generate_signal("TSLA")

        print(f"✅ Signal generated for TSLA:")
        print(f"   Type: {signal.signal_type.value}")
        print(f"   Confidence: {signal.confidence:.2f}")
        print(f"   Strength: {signal.strength:.2f}")

        return True

    except Exception as e:
        print(f"❌ Signal generation error: {e}")
        return False

def test_recommendations():
    """Test recommendation engine"""
    print("\n💡 Testing recommendation engine...")

    try:
        from analytics.recommendation_engine import RecommendationEngine

        engine = RecommendationEngine()
        recommendations = engine.get_daily_recommendations()

        summary = recommendations['summary']
        print(f"✅ Recommendations generated:")
        print(f"   Total: {summary['total_recommendations']}")
        print(f"   Buy: {summary['buy_recommendations']}")
        print(f"   Sell: {summary['sell_recommendations']}")

        return True

    except Exception as e:
        print(f"❌ Recommendation engine error: {e}")
        return False

def test_sentiment():
    """Test sentiment analysis"""
    print("\n📰 Testing sentiment analysis...")

    try:
        from data.processors.sentiment_analyzer import SentimentAnalyzer

        analyzer = SentimentAnalyzer()

        # Test with sample text
        test_text = "Tesla reports record quarterly earnings, beating estimates"
        result = analyzer.analyze_text(test_text)

        print(f"✅ Sentiment analysis working:")
        print(f"   Text: {test_text}")
        print(f"   Sentiment: {result['sentiment']} (score: {result['score']:.2f})")

        return True

    except Exception as e:
        print(f"❌ Sentiment analysis error: {e}")
        return False

def test_news():
    """Test news collection"""
    print("\n📰 Testing news collection...")

    try:
        from data.collectors.news_collector import NewsCollector

        collector = NewsCollector()
        news = collector.get_stock_news("TSLA", hours_back=24)

        print(f"✅ News collection working:")
        print(f"   Found {len(news)} TSLA articles in last 24h")

        if news:
            latest = news[0]
            print(f"   Latest: {latest['title'][:50]}...")

        return True

    except Exception as e:
        print(f"❌ News collection error: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("🧪 Trading Simulator System Test")
    print("=" * 50)

    # Suppress some logging during tests
    logging.getLogger().setLevel(logging.WARNING)

    tests = [
        ("Imports", test_imports),
        ("Market Data", test_market_data),
        ("Portfolio", test_portfolio),
        ("Signals", test_signals),
        ("Recommendations", test_recommendations),
        ("Sentiment", test_sentiment),
        ("News", test_news),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} test failed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 50)
    print("📋 Test Results Summary:")
    print("=" * 50)

    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1

    print(f"\n📊 Results: {passed}/{len(tests)} tests passed")

    if passed == len(tests):
        print("🎉 All tests passed! System is ready to use.")
        print("\nNext steps:")
        print("1. Get API keys (see README.md)")
        print("2. Run: python main.py --dashboard")
    else:
        print("⚠️  Some tests failed. Check errors above.")
        print("Make sure you have installed all requirements:")
        print("pip install -r requirements.txt")

if __name__ == "__main__":
    run_all_tests()
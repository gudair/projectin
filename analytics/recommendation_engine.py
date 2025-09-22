from datetime import datetime, timedelta
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json
import os

from portfolio.portfolio_manager import PortfolioManager
from signals.signal_generator import SignalGenerator, SignalType, TradingSignal
from data.collectors.market_data import MarketDataCollector
from config.settings import INITIAL_STOCK, WATCHLIST, MAX_POSITIONS, MAX_POSITION_SIZE

class ActionType(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    REDUCE = "reduce"
    ADD = "add"

@dataclass
class Recommendation:
    action: ActionType
    symbol: str
    shares: float
    current_price: float
    target_price: Optional[float]
    stop_loss: Optional[float]
    reasoning: str
    confidence: float
    urgency: str  # 'low', 'medium', 'high'
    expected_return: float
    risk_level: str  # 'low', 'medium', 'high'
    time_horizon: str  # 'short', 'medium', 'long'
    timestamp: datetime

class RecommendationEngine:
    def __init__(self):
        self.portfolio_manager = PortfolioManager()
        self.signal_generator = SignalGenerator()
        self.market_data = MarketDataCollector()
        self.logger = logging.getLogger(__name__)

        # Recommendation history
        self.recommendation_history: List[Recommendation] = []
        self.load_recommendation_history()

    def generate_recommendations(self) -> List[Recommendation]:
        """Generate comprehensive trading recommendations"""
        recommendations = []

        try:
            # Update portfolio with current market data
            market_snapshot = self.market_data.get_market_snapshot()
            self.portfolio_manager.update_positions(market_snapshot)

            # Get current portfolio state
            portfolio_summary = self.portfolio_manager.get_portfolio_summary()

            # Generate signals for all watchlist symbols
            signals = self.signal_generator.generate_watchlist_signals()

            # Generate recommendations based on different scenarios

            # 1. Exit recommendations (stop losses, take profits, position management)
            exit_recommendations = self._generate_exit_recommendations(portfolio_summary, signals)
            recommendations.extend(exit_recommendations)

            # 2. Entry recommendations (new positions)
            entry_recommendations = self._generate_entry_recommendations(portfolio_summary, signals)
            recommendations.extend(entry_recommendations)

            # 3. Position adjustment recommendations
            adjustment_recommendations = self._generate_adjustment_recommendations(portfolio_summary, signals)
            recommendations.extend(adjustment_recommendations)

            # Sort by urgency and confidence
            recommendations.sort(key=lambda x: (
                {'high': 3, 'medium': 2, 'low': 1}[x.urgency],
                x.confidence
            ), reverse=True)

            # Save recommendations
            self.recommendation_history.extend(recommendations)
            self.save_recommendation_history()

            return recommendations[:10]  # Return top 10 recommendations

        except Exception as e:
            self.logger.error(f"Error generating recommendations: {e}")
            return []

    def _generate_exit_recommendations(self, portfolio_summary: Dict, signals: Dict[str, TradingSignal]) -> List[Recommendation]:
        """Generate exit/sell recommendations for current positions"""
        recommendations = []

        for symbol, position_data in portfolio_summary['positions'].items():
            signal = signals.get(symbol)
            if not signal:
                continue

            current_price = position_data['current_price']
            unrealized_pnl_percent = position_data['unrealized_pnl_percent']
            shares = position_data['shares']

            # Exit conditions

            # 1. Strong sell signal
            if signal.signal_type in [SignalType.STRONG_SELL, SignalType.SELL]:
                recommendation = Recommendation(
                    action=ActionType.SELL,
                    symbol=symbol,
                    shares=shares,
                    current_price=current_price,
                    target_price=signal.target_price,
                    stop_loss=None,
                    reasoning=f"Strong sell signal: {signal.reasoning}",
                    confidence=signal.confidence,
                    urgency='high' if signal.signal_type == SignalType.STRONG_SELL else 'medium',
                    expected_return=self._calculate_expected_return(current_price, signal.target_price),
                    risk_level='medium',
                    time_horizon='short',
                    timestamp=datetime.now()
                )
                recommendations.append(recommendation)

            # 2. Take profits (>15% gain with weakening signals)
            elif unrealized_pnl_percent > 15 and signal.signal_type in [SignalType.HOLD, SignalType.WEAK_SELL]:
                recommendation = Recommendation(
                    action=ActionType.SELL,
                    symbol=symbol,
                    shares=shares * 0.5,  # Sell half
                    current_price=current_price,
                    target_price=None,
                    stop_loss=None,
                    reasoning=f"Take profits: {unrealized_pnl_percent:.1f}% gain with neutral signals",
                    confidence=0.7,
                    urgency='medium',
                    expected_return=unrealized_pnl_percent / 2,  # Lock in half the gains
                    risk_level='low',
                    time_horizon='immediate',
                    timestamp=datetime.now()
                )
                recommendations.append(recommendation)

            # 3. Stop loss recommendation (>8% loss)
            elif unrealized_pnl_percent < -8:
                recommendation = Recommendation(
                    action=ActionType.SELL,
                    symbol=symbol,
                    shares=shares,
                    current_price=current_price,
                    target_price=None,
                    stop_loss=None,
                    reasoning=f"Stop loss triggered: {unrealized_pnl_percent:.1f}% loss",
                    confidence=0.9,
                    urgency='high',
                    expected_return=unrealized_pnl_percent,
                    risk_level='high',
                    time_horizon='immediate',
                    timestamp=datetime.now()
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_entry_recommendations(self, portfolio_summary: Dict, signals: Dict[str, TradingSignal]) -> List[Recommendation]:
        """Generate buy/entry recommendations for new positions"""
        recommendations = []

        # Check if we can open new positions
        current_positions = len(portfolio_summary['positions'])
        available_cash = portfolio_summary['cash']
        portfolio_value = portfolio_summary['total_value']

        if current_positions >= MAX_POSITIONS:
            self.logger.info("Maximum positions reached, no entry recommendations")
            return recommendations

        if available_cash < 50:  # Minimum $50 for new position
            self.logger.info("Insufficient cash for new positions")
            return recommendations

        # Evaluate buy signals for symbols not in portfolio
        for symbol, signal in signals.items():
            if symbol in portfolio_summary['positions']:
                continue  # Skip existing positions

            if signal.signal_type in [SignalType.STRONG_BUY, SignalType.BUY, SignalType.WEAK_BUY]:
                current_price = signal.timestamp  # This should be current price from market data
                market_snapshot = self.market_data.get_market_snapshot()
                current_price = market_snapshot.get(symbol, {}).get('current_price', 0)

                if current_price <= 0:
                    continue

                # Calculate position size
                max_position_value = portfolio_value * MAX_POSITION_SIZE
                suggested_investment = min(available_cash * 0.8, max_position_value)
                suggested_shares = suggested_investment / current_price

                if suggested_investment < 25:  # Minimum $25 position
                    continue

                # Determine urgency based on signal strength
                if signal.signal_type == SignalType.STRONG_BUY and signal.confidence > 0.8:
                    urgency = 'high'
                elif signal.signal_type == SignalType.BUY and signal.confidence > 0.6:
                    urgency = 'medium'
                else:
                    urgency = 'low'

                recommendation = Recommendation(
                    action=ActionType.BUY,
                    symbol=symbol,
                    shares=suggested_shares,
                    current_price=current_price,
                    target_price=signal.target_price,
                    stop_loss=signal.stop_loss,
                    reasoning=f"Buy signal: {signal.reasoning}",
                    confidence=signal.confidence,
                    urgency=urgency,
                    expected_return=self._calculate_expected_return(current_price, signal.target_price),
                    risk_level=self._assess_risk_level(signal),
                    time_horizon=self._determine_time_horizon(signal),
                    timestamp=datetime.now()
                )
                recommendations.append(recommendation)

        return recommendations

    def _generate_adjustment_recommendations(self, portfolio_summary: Dict, signals: Dict[str, TradingSignal]) -> List[Recommendation]:
        """Generate position adjustment recommendations"""
        recommendations = []

        for symbol, position_data in portfolio_summary['positions'].items():
            signal = signals.get(symbol)
            if not signal:
                continue

            current_price = position_data['current_price']
            current_shares = position_data['shares']
            position_value = position_data['current_value']
            unrealized_pnl_percent = position_data['unrealized_pnl_percent']

            # Add to position (averaging down or up)
            if signal.signal_type in [SignalType.STRONG_BUY, SignalType.BUY]:

                # Average down if losing money but strong buy signal
                if unrealized_pnl_percent < -5 and signal.confidence > 0.7:
                    available_cash = portfolio_summary['cash']
                    max_additional = min(available_cash * 0.5, position_value * 0.3)

                    if max_additional > 25:
                        additional_shares = max_additional / current_price

                        recommendation = Recommendation(
                            action=ActionType.ADD,
                            symbol=symbol,
                            shares=additional_shares,
                            current_price=current_price,
                            target_price=signal.target_price,
                            stop_loss=signal.stop_loss,
                            reasoning=f"Average down: Strong buy signal with {unrealized_pnl_percent:.1f}% loss",
                            confidence=signal.confidence * 0.8,  # Slightly lower confidence for averaging down
                            urgency='medium',
                            expected_return=self._calculate_expected_return(current_price, signal.target_price),
                            risk_level='medium',
                            time_horizon='medium',
                            timestamp=datetime.now()
                        )
                        recommendations.append(recommendation)

                # Add to winning position if very strong signal
                elif unrealized_pnl_percent > 5 and signal.signal_type == SignalType.STRONG_BUY and signal.confidence > 0.8:
                    available_cash = portfolio_summary['cash']
                    max_additional = min(available_cash * 0.3, position_value * 0.2)

                    if max_additional > 25:
                        additional_shares = max_additional / current_price

                        recommendation = Recommendation(
                            action=ActionType.ADD,
                            symbol=symbol,
                            shares=additional_shares,
                            current_price=current_price,
                            target_price=signal.target_price,
                            stop_loss=signal.stop_loss,
                            reasoning=f"Add to winner: Very strong signal with {unrealized_pnl_percent:.1f}% gain",
                            confidence=signal.confidence,
                            urgency='low',
                            expected_return=self._calculate_expected_return(current_price, signal.target_price),
                            risk_level='low',
                            time_horizon='medium',
                            timestamp=datetime.now()
                        )
                        recommendations.append(recommendation)

            # Reduce position (partial sell)
            elif signal.signal_type in [SignalType.WEAK_SELL] and unrealized_pnl_percent > 5:
                shares_to_sell = current_shares * 0.3  # Sell 30%

                recommendation = Recommendation(
                    action=ActionType.REDUCE,
                    symbol=symbol,
                    shares=shares_to_sell,
                    current_price=current_price,
                    target_price=None,
                    stop_loss=None,
                    reasoning=f"Reduce position: Weak sell signal with {unrealized_pnl_percent:.1f}% gain",
                    confidence=signal.confidence,
                    urgency='low',
                    expected_return=unrealized_pnl_percent * 0.3,  # Lock in partial gains
                    risk_level='low',
                    time_horizon='short',
                    timestamp=datetime.now()
                )
                recommendations.append(recommendation)

        return recommendations

    def _calculate_expected_return(self, current_price: float, target_price: Optional[float]) -> float:
        """Calculate expected return percentage"""
        if not target_price or current_price <= 0:
            return 0.0
        return ((target_price - current_price) / current_price) * 100

    def _assess_risk_level(self, signal: TradingSignal) -> str:
        """Assess risk level based on signal characteristics"""
        if signal.confidence > 0.8 and signal.strength > 0.7:
            return 'low'
        elif signal.confidence > 0.6 and signal.strength > 0.5:
            return 'medium'
        else:
            return 'high'

    def _determine_time_horizon(self, signal: TradingSignal) -> str:
        """Determine time horizon based on signal type"""
        if signal.signal_type in [SignalType.STRONG_BUY, SignalType.STRONG_SELL]:
            return 'short'  # 1-7 days
        elif signal.signal_type in [SignalType.BUY, SignalType.SELL]:
            return 'medium'  # 1-4 weeks
        else:
            return 'long'  # 1-3 months

    def get_daily_recommendations(self) -> Dict:
        """Get formatted daily recommendations for display"""
        recommendations = self.generate_recommendations()

        # Group recommendations by action type
        grouped_recs = {
            'high_priority': [],
            'medium_priority': [],
            'low_priority': [],
            'summary': {
                'total_recommendations': len(recommendations),
                'buy_recommendations': len([r for r in recommendations if r.action == ActionType.BUY]),
                'sell_recommendations': len([r for r in recommendations if r.action == ActionType.SELL]),
                'adjustment_recommendations': len([r for r in recommendations if r.action in [ActionType.ADD, ActionType.REDUCE]]),
            }
        }

        for rec in recommendations:
            rec_dict = {
                'action': rec.action.value,
                'symbol': rec.symbol,
                'shares': round(rec.shares, 6),
                'current_price': rec.current_price,
                'target_price': rec.target_price,
                'stop_loss': rec.stop_loss,
                'reasoning': rec.reasoning,
                'confidence': f"{rec.confidence:.1%}",
                'expected_return': f"{rec.expected_return:.1f}%",
                'risk_level': rec.risk_level,
                'time_horizon': rec.time_horizon,
                'investment_amount': rec.shares * rec.current_price
            }

            if rec.urgency == 'high':
                grouped_recs['high_priority'].append(rec_dict)
            elif rec.urgency == 'medium':
                grouped_recs['medium_priority'].append(rec_dict)
            else:
                grouped_recs['low_priority'].append(rec_dict)

        return grouped_recs

    def save_recommendation_history(self):
        """Save recommendation history to file"""
        try:
            os.makedirs('analytics', exist_ok=True)

            # Keep only last 100 recommendations
            recent_recommendations = self.recommendation_history[-100:]

            data = []
            for rec in recent_recommendations:
                data.append({
                    'action': rec.action.value,
                    'symbol': rec.symbol,
                    'shares': rec.shares,
                    'current_price': rec.current_price,
                    'target_price': rec.target_price,
                    'stop_loss': rec.stop_loss,
                    'reasoning': rec.reasoning,
                    'confidence': rec.confidence,
                    'urgency': rec.urgency,
                    'expected_return': rec.expected_return,
                    'risk_level': rec.risk_level,
                    'time_horizon': rec.time_horizon,
                    'timestamp': rec.timestamp.isoformat()
                })

            with open('analytics/recommendation_history.json', 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            self.logger.error(f"Error saving recommendation history: {e}")

    def load_recommendation_history(self):
        """Load recommendation history from file"""
        try:
            if os.path.exists('analytics/recommendation_history.json'):
                with open('analytics/recommendation_history.json', 'r') as f:
                    data = json.load(f)

                for rec_data in data:
                    rec = Recommendation(
                        action=ActionType(rec_data['action']),
                        symbol=rec_data['symbol'],
                        shares=rec_data['shares'],
                        current_price=rec_data['current_price'],
                        target_price=rec_data.get('target_price'),
                        stop_loss=rec_data.get('stop_loss'),
                        reasoning=rec_data['reasoning'],
                        confidence=rec_data['confidence'],
                        urgency=rec_data['urgency'],
                        expected_return=rec_data['expected_return'],
                        risk_level=rec_data['risk_level'],
                        time_horizon=rec_data['time_horizon'],
                        timestamp=datetime.fromisoformat(rec_data['timestamp'])
                    )
                    self.recommendation_history.append(rec)

        except Exception as e:
            self.logger.error(f"Error loading recommendation history: {e}")

    def execute_recommendation_simulation(self, recommendation: Recommendation) -> bool:
        """Execute a recommendation in the simulation (for testing)"""
        try:
            if recommendation.action == ActionType.BUY:
                return self.portfolio_manager.execute_buy_order(
                    recommendation.symbol,
                    recommendation.shares,
                    recommendation.current_price,
                    f"Recommendation: {recommendation.reasoning}"
                )
            elif recommendation.action in [ActionType.SELL, ActionType.REDUCE]:
                return self.portfolio_manager.execute_sell_order(
                    recommendation.symbol,
                    recommendation.shares,
                    recommendation.current_price,
                    f"Recommendation: {recommendation.reasoning}"
                )
            elif recommendation.action == ActionType.ADD:
                return self.portfolio_manager.execute_buy_order(
                    recommendation.symbol,
                    recommendation.shares,
                    recommendation.current_price,
                    f"Add to position: {recommendation.reasoning}"
                )
            else:
                return False

        except Exception as e:
            self.logger.error(f"Error executing recommendation: {e}")
            return False

if __name__ == "__main__":
    # Test recommendation engine
    engine = RecommendationEngine()

    print("Generating daily recommendations...")
    daily_recs = engine.get_daily_recommendations()

    print(f"\nRecommendation Summary:")
    print(f"Total: {daily_recs['summary']['total_recommendations']}")
    print(f"Buy: {daily_recs['summary']['buy_recommendations']}")
    print(f"Sell: {daily_recs['summary']['sell_recommendations']}")
    print(f"Adjustments: {daily_recs['summary']['adjustment_recommendations']}")

    print(f"\nHigh Priority Recommendations ({len(daily_recs['high_priority'])}):")
    for rec in daily_recs['high_priority']:
        print(f"  {rec['action'].upper()} {rec['shares']:.4f} {rec['symbol']} @ ${rec['current_price']:.2f}")
        print(f"    Reason: {rec['reasoning']}")
        print(f"    Expected Return: {rec['expected_return']} | Confidence: {rec['confidence']}")
        print()
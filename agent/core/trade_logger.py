"""
Trade Logger - Detailed reasoning and decision logging

Saves comprehensive information about WHY each trade was made,
enabling learning from past decisions and debugging.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class TradeDecisionLog:
    """Complete log of a trade decision"""
    # Identification
    timestamp: str
    symbol: str
    action: str  # BUY, SELL, HOLD, SKIP

    # Decision details
    confidence: float
    entry_price: float
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    target_3: Optional[float] = None
    position_size: Optional[float] = None

    # Technical indicators at decision time
    technical_data: Dict[str, Any] = field(default_factory=dict)

    # Market context
    market_context: Dict[str, Any] = field(default_factory=dict)

    # Analyst ratings (from Yahoo Finance)
    analyst_ratings: Dict[str, Any] = field(default_factory=dict)

    # News/Sentiment
    news_sentiment: Dict[str, Any] = field(default_factory=dict)

    # LLM Reasoning - THE KEY PART
    reasoning: str = ""
    reasoning_summary: str = ""

    # Score breakdown
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    # Setup type (for momentum trades)
    setup_type: str = ""

    # Outcome tracking (filled in later)
    outcome: Optional[Dict[str, Any]] = None

    # Execution details
    executed: bool = False
    execution_price: Optional[float] = None
    execution_time: Optional[str] = None
    order_id: Optional[str] = None
    error_message: Optional[str] = None


class TradeLogger:
    """
    Logs all trade decisions with detailed reasoning.

    Enables:
    - Post-trade analysis
    - Learning from mistakes
    - Debugging strategy issues
    - Building training data for future ML models
    """

    def __init__(self, log_dir: str = "logs/trades"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)

        # Current day's log file
        self._current_date = None
        self._current_file = None
        self._decisions: List[TradeDecisionLog] = []

    def _get_log_file(self) -> Path:
        """Get today's log file path"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            self._current_file = self.log_dir / f"trades_{today}.jsonl"
        return self._current_file

    def log_decision(
        self,
        symbol: str,
        action: str,
        confidence: float,
        entry_price: float,
        reasoning: str,
        technical_data: Optional[Dict] = None,
        market_context: Optional[Dict] = None,
        analyst_ratings: Optional[Dict] = None,
        news_sentiment: Optional[Dict] = None,
        stop_loss: Optional[float] = None,
        targets: Optional[tuple] = None,
        position_size: Optional[float] = None,
        setup_type: str = "",
        score_breakdown: Optional[Dict[str, float]] = None,
    ) -> TradeDecisionLog:
        """
        Log a trade decision with full reasoning.

        Args:
            symbol: Stock ticker
            action: BUY, SELL, HOLD, or SKIP
            confidence: 0-1 confidence score
            entry_price: Current/entry price
            reasoning: Full LLM reasoning text
            technical_data: RSI, MACD, volume, etc.
            market_context: VIX, SPY, regime, etc.
            analyst_ratings: Yahoo Finance ratings
            news_sentiment: News analysis results
            stop_loss: Stop loss price
            targets: Tuple of (target_1, target_2, target_3)
            position_size: Dollar amount or shares
            setup_type: Momentum setup type if applicable
            score_breakdown: Individual score components

        Returns:
            TradeDecisionLog object
        """
        # Create summary from reasoning (first 200 chars or first sentence)
        reasoning_summary = reasoning.split('.')[0][:200] if reasoning else ""

        # Unpack targets
        t1, t2, t3 = targets if targets else (None, None, None)

        decision = TradeDecisionLog(
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            action=action,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_1=t1,
            target_2=t2,
            target_3=t3,
            position_size=position_size,
            technical_data=technical_data or {},
            market_context=market_context or {},
            analyst_ratings=analyst_ratings or {},
            news_sentiment=news_sentiment or {},
            reasoning=reasoning,
            reasoning_summary=reasoning_summary,
            score_breakdown=score_breakdown or {},
            setup_type=setup_type,
        )

        # Save to file
        self._write_decision(decision)
        self._decisions.append(decision)

        # Mirror to Supabase (non-blocking — failure doesn't stop the agent)
        try:
            from agent.core.supabase_logger import log_trade
            log_trade(
                symbol=symbol,
                action=action,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=t1,
                confidence=confidence,
                reasoning=reasoning,
                executed=False,
            )
        except Exception as e:
            self.logger.warning(f"Supabase mirror failed (non-critical): {e}")

        self.logger.info(
            f"📝 Logged {action} decision for {symbol} | "
            f"Confidence: {confidence:.0%} | "
            f"Reason: {reasoning_summary[:50]}..."
        )

        return decision

    def log_execution(
        self,
        symbol: str,
        order_id: str,
        execution_price: float,
        success: bool,
        error_message: Optional[str] = None,
    ):
        """Update the most recent decision for this symbol with execution results"""
        # Find the most recent decision for this symbol
        for decision in reversed(self._decisions):
            if decision.symbol == symbol and not decision.executed:
                decision.executed = success
                decision.execution_price = execution_price
                decision.execution_time = datetime.now().isoformat()
                decision.order_id = order_id
                decision.error_message = error_message

                # Re-write to update the file
                self._write_decision(decision, update=True)

                # Update Supabase row to mark as executed
                if success and order_id:
                    try:
                        from agent.core import supabase_logger
                        supabase_logger._get_client() and supabase_logger._get_client().table("trades").update({
                            "executed": True,
                            "order_id": order_id,
                        }).eq("symbol", symbol).eq("executed", False).execute()
                    except Exception:
                        pass

                self.logger.info(
                    f"📝 Updated execution for {symbol}: "
                    f"{'SUCCESS' if success else 'FAILED'} @ ${execution_price:.2f}"
                )
                return

    def log_outcome(
        self,
        symbol: str,
        order_id: str,
        exit_price: float,
        exit_reason: str,
        pnl_dollars: float,
        pnl_percent: float,
        hold_duration_minutes: int,
    ):
        """Log the final outcome of a trade (when position is closed)"""
        # Find the decision by order_id
        for decision in reversed(self._decisions):
            if decision.order_id == order_id:
                decision.outcome = {
                    "exit_price": exit_price,
                    "exit_reason": exit_reason,
                    "pnl_dollars": pnl_dollars,
                    "pnl_percent": pnl_percent,
                    "hold_duration_minutes": hold_duration_minutes,
                    "exit_time": datetime.now().isoformat(),
                    "profitable": pnl_dollars > 0,
                }

                self._write_decision(decision, update=True)

                # Update Supabase with outcome
                if decision.order_id:
                    try:
                        from agent.core.supabase_logger import update_trade_outcome
                        update_trade_outcome(
                            order_id=decision.order_id,
                            exit_price=exit_price,
                            exit_reason=exit_reason,
                            pnl_dollars=pnl_dollars,
                            pnl_percent=pnl_percent,
                        )
                    except Exception:
                        pass

                emoji = "💰" if pnl_dollars > 0 else "📉"
                self.logger.info(
                    f"{emoji} Trade outcome logged for {symbol}: "
                    f"{pnl_percent:+.2f}% (${pnl_dollars:+.2f}) | "
                    f"Reason: {exit_reason}"
                )
                return

    def _write_decision(self, decision: TradeDecisionLog, update: bool = False):
        """Write decision to JSONL file"""
        log_file = self._get_log_file()

        # Convert to dict, handling None values
        data = asdict(decision)

        # Append to file (JSONL format - one JSON object per line)
        with open(log_file, 'a') as f:
            f.write(json.dumps(data, default=str) + '\n')

    def get_recent_decisions(self, symbol: Optional[str] = None, limit: int = 10) -> List[TradeDecisionLog]:
        """Get recent decisions, optionally filtered by symbol"""
        decisions = self._decisions
        if symbol:
            decisions = [d for d in decisions if d.symbol == symbol]
        return decisions[-limit:]

    def get_trades_for_date(self, date: datetime) -> List[Dict]:
        """
        Load trade logs for a specific date.
        Used by HindsightAnalyzer to compare agent trades with optimal scenarios.

        Returns list of trade dictionaries with entry/exit info.
        """
        date_str = date.strftime("%Y-%m-%d")
        log_file = self.log_dir / f"trades_{date_str}.jsonl"

        if not log_file.exists():
            return []

        trades = []
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        # Only include executed trades with outcomes
                        if data.get('executed') and data.get('outcome'):
                            outcome = data['outcome']
                            trades.append({
                                'symbol': data.get('symbol'),
                                'entry_price': data.get('execution', {}).get('fill_price'),
                                'exit_price': outcome.get('exit_price'),
                                'entry_time': data.get('execution', {}).get('fill_time'),
                                'exit_time': outcome.get('exit_time'),
                                'pnl_pct': outcome.get('pnl_percent'),
                                'pnl_dollars': outcome.get('pnl_dollars'),
                                'side': data.get('decision', {}).get('action'),
                            })
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            self.logger.error(f"Error reading trade logs for {date_str}: {e}")

        return trades

    def get_win_rate(self, days: int = 7) -> Dict[str, Any]:
        """Calculate win rate from logged trades"""
        # Load recent log files
        all_decisions = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            log_file = self.log_dir / f"trades_{date}.jsonl"
            if log_file.exists():
                with open(log_file, 'r') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            all_decisions.append(data)
                        except json.JSONDecodeError:
                            continue

        # Calculate stats
        executed = [d for d in all_decisions if d.get('executed')]
        with_outcome = [d for d in executed if d.get('outcome')]

        if not with_outcome:
            return {"win_rate": 0, "total_trades": 0, "avg_pnl": 0}

        wins = [d for d in with_outcome if d['outcome'].get('profitable')]
        total_pnl = sum(d['outcome'].get('pnl_percent', 0) for d in with_outcome)

        return {
            "win_rate": len(wins) / len(with_outcome) if with_outcome else 0,
            "total_trades": len(with_outcome),
            "wins": len(wins),
            "losses": len(with_outcome) - len(wins),
            "avg_pnl_percent": total_pnl / len(with_outcome) if with_outcome else 0,
            "decisions_logged": len(all_decisions),
        }

    def get_reasoning_patterns(self, profitable_only: bool = True) -> List[str]:
        """Extract reasoning patterns from profitable trades"""
        patterns = []
        for decision in self._decisions:
            if decision.outcome:
                if profitable_only and not decision.outcome.get('profitable'):
                    continue
                if decision.reasoning:
                    patterns.append(decision.reasoning)
        return patterns


# Import timedelta for get_win_rate
from datetime import timedelta

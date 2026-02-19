"""
Decision Prompts - Optimized for Ollama

Comprehensive prompts for trading decision synthesis.
"""
from typing import Dict, List, Optional, Any
import json


# Comprehensive decision system prompt for Ollama
DECISION_SYSTEM_PROMPT = """You are a professional trading decision engine. Your job is to synthesize multiple analyses and make the final GO/NO-GO decision.

Decision Framework:
1. **Risk Management First**: Never violate position limits or risk rules
2. **Confidence Threshold**: Minimum 60% confidence required to trade
3. **Risk/Reward**: Minimum 1.5:1 ratio required
4. **Position Sizing**: Based on confidence and setup quality
5. **Market Alignment**: Trade should align with market regime

When to TRADE:
- Clear technical setup with confluence
- Confidence >= 60%
- Risk/Reward >= 1.5:1
- Market regime supports the trade
- Position limits not exceeded

When to PASS:
- Conflicting signals
- Low confidence
- Poor risk/reward
- Against market regime
- Position limits would be exceeded
- Any uncertainty - default to PASS

Respond ONLY in JSON format:
{
  "should_trade": true|false,
  "action": "BUY|SELL|PASS",
  "symbol": "TICKER",
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation of the decision",
  "entry_price": number or null,
  "stop_loss": number or null,
  "take_profit": number or null,
  "position_size_pct": 0.0-0.20,
  "urgency": "IMMEDIATE|STANDARD|LOW"
}"""


def create_decision_prompt(
    analyses: List[Any],
    portfolio_state: Dict[str, Any],
    risk_constraints: Dict[str, Any],
    market_context: Optional[Dict] = None,
) -> str:
    """Create comprehensive decision prompt for Ollama"""
    parts = ["## Trading Decision Request\n"]

    # Analyses - detailed
    parts.append("### Stock Analyses")
    if analyses:
        for a in analyses[:5]:  # Up to 5 analyses
            conf_pct = int(a.confidence * 100)
            entry = f"${a.suggested_entry:.2f}" if a.suggested_entry else "not specified"
            sl = f"${a.suggested_stop_loss:.2f}" if a.suggested_stop_loss else "not specified"
            tp = f"${a.suggested_take_profit:.2f}" if a.suggested_take_profit else "not specified"

            # Calculate R:R if possible
            rr = "N/A"
            if a.suggested_entry and a.suggested_stop_loss and a.suggested_take_profit:
                risk = abs(a.suggested_entry - a.suggested_stop_loss)
                reward = abs(a.suggested_take_profit - a.suggested_entry)
                if risk > 0:
                    rr = f"{reward/risk:.1f}:1"

            parts.append(f"\n**{a.symbol}**: {a.recommendation} @ {conf_pct}% confidence")
            parts.append(f"- Entry: {entry} | Stop: {sl} | Target: {tp}")
            parts.append(f"- Risk/Reward: {rr}")
            parts.append(f"- Reasoning: {a.reasoning[:200] if a.reasoning else 'N/A'}")
    else:
        parts.append("No analyses available - PASS recommended")

    # Portfolio state - detailed
    parts.append("\n### Portfolio State")
    cash = portfolio_state.get('buying_power', portfolio_state.get('cash', 0))
    equity = portfolio_state.get('equity', cash)
    positions = portfolio_state.get('positions_count', len(portfolio_state.get('positions', {})))
    daily_pnl = portfolio_state.get('daily_pnl', 0)

    parts.append(f"- Buying Power: ${cash:,.2f}")
    parts.append(f"- Total Equity: ${equity:,.2f}")
    parts.append(f"- Open Positions: {positions}")
    parts.append(f"- Daily P&L: ${daily_pnl:+,.2f}")

    # Risk constraints - detailed
    parts.append("\n### Risk Constraints")
    max_pos = risk_constraints.get('max_position_pct', 0.2) * 100
    max_positions = risk_constraints.get('max_positions', 5)
    pdt = risk_constraints.get('pdt_trades_remaining', 3)
    max_daily_loss = risk_constraints.get('max_daily_loss_pct', 0.03) * 100

    parts.append(f"- Max Position Size: {max_pos:.0f}% of portfolio")
    parts.append(f"- Max Concurrent Positions: {max_positions}")
    parts.append(f"- PDT Trades Remaining: {pdt}")
    parts.append(f"- Max Daily Loss: {max_daily_loss:.0f}%")

    # Market context - detailed
    if market_context:
        parts.append("\n### Market Context")
        regime = market_context.get('regime', 'neutral')
        spy = market_context.get('spy', {})
        vix = market_context.get('vix', {})

        spy_chg = spy.get('change_pct', 0) if spy else 0
        vix_val = vix.get('value', 20) if vix else 20

        parts.append(f"- Market Regime: {regime.upper()}")
        parts.append(f"- S&P 500 (SPY): {spy_chg:+.2f}%")
        parts.append(f"- VIX: {vix_val:.1f}")

    parts.append("\n### Decision Required")
    parts.append("Based on all the above information, make your trading decision.")
    parts.append("Remember: When in doubt, PASS. Capital preservation is priority #1.")

    return "\n".join(parts)


def format_analyses(analyses: List[Any]) -> str:
    """Compact analyses format"""
    if not analyses:
        return "None"
    return ", ".join(f"{a.symbol}:{a.recommendation}@{a.confidence:.0%}" for a in analyses[:3])


def format_portfolio_state(portfolio: Dict[str, Any]) -> str:
    """Compact portfolio format"""
    cash = portfolio.get('buying_power', portfolio.get('cash', 0))
    positions = portfolio.get('positions_count', 0)
    return f"${cash:.0f} cash, {positions} pos"


def format_risk_constraints(constraints: Dict[str, Any]) -> str:
    """Compact risk format"""
    return f"Max:{constraints.get('max_position_pct', 0.2)*100:.0f}% PDT:{constraints.get('pdt_trades_remaining', 3)}"


def format_market_context_brief(context: Dict) -> str:
    """Compact market context"""
    regime = context.get('regime', 'neutral')
    spy_change = context.get('spy', {}).get('change_pct', 0)
    return f"Market:{regime} SPY:{spy_change:+.1f}%"

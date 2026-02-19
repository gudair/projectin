"""
Ultra-Compact Prompts for Ollama - Machine-Optimized

Reduces tokens by 60-70% using:
- Abbreviated keys
- No natural language explanations
- Minimal JSON output
- Data-only format
"""
from typing import Dict, List, Optional, Any


# Minimal system prompt - keys must match parser expectations
COMPACT_ANALYSIS_SYSTEM = """Stock analyst. Respond with valid JSON only.
Rules: Only recommend BUY if confidence>=0.6 and risk:reward>=1.5.
Example: {"recommendation":"BUY","confidence":0.75,"entry_price":150.00,"stop_loss":147.00,"take_profit":156.00,"reasoning":"RSI oversold, MACD bullish"}"""


COMPACT_DECISION_SYSTEM = """Trade decision maker. Respond with valid JSON only.
Rules: Only trade if confidence>=0.6 and risk:reward>=1.5, max 20% position size.
Example: {"should_trade":true,"action":"BUY","confidence":0.7,"entry_price":150.00,"stop_loss":147.00,"take_profit":156.00,"position_size_pct":0.15}"""


def compact_analysis_prompt(
    symbol: str,
    technical: Dict[str, Any],
    market: Optional[Dict] = None,
    news: Optional[Dict] = None,
) -> str:
    """Compact analysis prompt - readable but efficient"""

    # Core price data
    p = technical.get('current_price', 0)
    chg = technical.get('change_pct', technical.get('daily_change', 0))
    if isinstance(chg, float) and abs(chg) < 1:
        chg *= 100

    # Indicators
    rsi = technical.get('rsi', 50)
    macd = technical.get('macd', 0)
    macd_sig = technical.get('macd_signal', 0)
    vol = technical.get('volume_ratio', 1)

    # Range
    hi = technical.get('high', technical.get('day_high', p))
    lo = technical.get('low', technical.get('day_low', p))

    # Build readable analysis request
    parts = [f"ANALYZE {symbol} FOR TRADING:\n"]
    parts.append(f"Price: ${p:.2f} ({chg:+.1f}% today)\n")
    parts.append(f"Range: ${lo:.2f} - ${hi:.2f}\n")

    # Technical signals
    rsi_signal = "OVERSOLD (buy signal)" if rsi < 30 else ("OVERBOUGHT (sell signal)" if rsi > 70 else "neutral")
    macd_signal = "bullish (MACD above signal)" if macd > macd_sig else "bearish (MACD below signal)"
    parts.append(f"RSI: {rsi:.0f} - {rsi_signal}\n")
    parts.append(f"MACD: {macd_signal}\n")
    parts.append(f"Volume: {vol:.1f}x average\n")

    # Market context
    if market:
        regime = market.get('regime', 'neutral')
        spy = market.get('spy', {})
        vix = market.get('vix', {})
        spy_chg = spy.get('change_pct', 0) if isinstance(spy, dict) else 0
        vix_val = vix.get('value', 20) if isinstance(vix, dict) else 20
        parts.append(f"Market: {regime}, SPY {spy_chg:+.1f}%, VIX {vix_val:.0f}\n")

    # News sentiment
    if news and news.get('article_count', 0) > 0:
        sent = news.get('overall_sentiment', 'neutral')
        score = news.get('overall_score', 0)
        parts.append(f"News: {sent} sentiment (score: {score:+.1f})\n")

    parts.append("\nGive BUY/SELL/HOLD recommendation with entry, stop-loss, and target prices.")

    return "".join(parts)


def compact_decision_prompt(
    analyses: List[Any],
    portfolio: Dict[str, Any],
    risk: Dict[str, Any],
    market: Optional[Dict] = None,
) -> str:
    """Compact decision prompt - still readable but efficient"""

    parts = ["DECIDE IF WE SHOULD TRADE:\n"]

    # Analyses - make it clear what we're analyzing
    if analyses:
        for a in analyses[:3]:
            current = a.suggested_entry or 0
            # Calculate sensible stop/take if not provided
            sl = a.suggested_stop_loss or (current * 0.98)  # 2% stop
            tp = a.suggested_take_profit or (current * 1.04)  # 4% target
            parts.append(
                f"ANALYSIS: {a.symbol} -> {a.recommendation} "
                f"(conf:{a.confidence:.0%}) "
                f"price:${current:.2f} stop:${sl:.2f} target:${tp:.2f}\n"
            )
    else:
        parts.append("NO SIGNALS TO TRADE\n")

    # Portfolio state
    cash = portfolio.get('buying_power', portfolio.get('cash', 0))
    equity = portfolio.get('equity', cash)
    pos_count = portfolio.get('positions_count', 0)
    parts.append(f"PORTFOLIO: ${cash:.0f} cash, ${equity:.0f} equity, {pos_count} positions\n")

    # Risk rules
    max_pos = risk.get('max_position_pct', 0.2) * 100
    pdt = risk.get('pdt_trades_remaining', 3)
    parts.append(f"RULES: max {max_pos:.0f}% per trade, {pdt} day-trades left\n")

    # Market context
    if market:
        regime = market.get('regime', 'neutral')
        parts.append(f"MARKET: {regime}\n")

    parts.append("\nRespond with JSON: should we trade?")

    return "".join(parts)


def compact_exit_prompt(
    symbol: str,
    position_data: Dict[str, Any],
    market: Optional[Dict] = None,
    news: Optional[Dict] = None,
) -> str:
    """Ultra-compact exit analysis prompt"""

    p = position_data.get('current_price', 0)
    entry = position_data.get('entry_price', p)
    pnl = position_data.get('pnl_percent', 0)
    high = position_data.get('highest_price', p)
    drop = position_data.get('drop_from_high', 0)

    parts = [f"EXIT?|S:{symbol}|P:{p:.2f}|ENTRY:{entry:.2f}|PNL:{pnl:+.1f}%|HI:{high:.2f}|DROP:{drop:+.1f}%"]

    if market:
        regime = market.get('regime', 'N')[:1].upper()
        parts.append(f"|MKT:{regime}")

    if news:
        sent = news.get('sentiment', 'N')[:1].upper()
        parts.append(f"|NEWS:{sent}")

    parts.append("|OUT:{sell:bool,reason:str<30}")

    return "".join(parts)


# Compact system prompt for exit decisions
COMPACT_EXIT_SYSTEM = """Exit decision. JSON only.
Sell if: PNL<-2% or DROP>3% from high or bad news.
{"sell":true/false,"reasoning":"<30chars"}"""

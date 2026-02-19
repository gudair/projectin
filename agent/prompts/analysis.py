"""
Analysis Prompts - Optimized for Ollama (local LLM)

Comprehensive prompts for trading setup analysis.
Since Ollama is free, we can use more detailed analysis.
"""
from typing import Dict, List, Optional, Any
import json


# Comprehensive system prompt for Ollama
ANALYSIS_SYSTEM_PROMPT = """You are an expert day trader and technical analyst. Analyze stock setups thoroughly.

Your analysis should consider:
1. **Technical Analysis**: Price action, support/resistance, trend direction, momentum
2. **Volume Analysis**: Volume confirmation, unusual volume, accumulation/distribution
3. **Indicators**: RSI (overbought >70, oversold <30), MACD crossovers, moving averages
4. **Risk/Reward**: Calculate precise entry, stop-loss, and take-profit levels
5. **Market Context**: Consider overall market conditions (SPY, VIX) in your analysis

Trading Rules:
- Be conservative - only recommend trades with clear setups
- Always specify exact entry, stop-loss, and take-profit prices
- Minimum 1.5:1 risk/reward ratio required
- Consider the current market regime (risk-on vs risk-off)
- Account for volatility when setting stop-loss

Respond ONLY in JSON format:
{
  "recommendation": "BUY|SELL|HOLD",
  "confidence": 0.0-1.0,
  "reasoning": "detailed explanation of the trade thesis",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["risk1", "risk2"],
  "entry_price": number,
  "stop_loss": number,
  "take_profit": number,
  "position_size": "FULL|HALF|QUARTER",
  "time_horizon": "scalp|intraday|swing",
  "technical_setup": "description of chart pattern or setup"
}"""


def create_analysis_prompt(
    symbol: str,
    technical_data: Dict[str, Any],
    news_sentiment: Optional[Dict] = None,
    market_context: Optional[Dict] = None,
    memory_context: Optional[str] = None,
) -> str:
    """Create comprehensive analysis prompt for Ollama"""
    parts = [f"## Stock Analysis Request: {symbol}\n"]

    # Technical data - detailed format
    parts.append("### Technical Data")
    parts.append(format_technical_detailed(technical_data))

    # Market context
    if market_context:
        parts.append("\n### Market Context")
        parts.append(format_market_detailed(market_context))

    # News sentiment
    if news_sentiment and news_sentiment.get('article_count', 0) > 0:
        parts.append("\n### News Sentiment")
        parts.append(format_news_detailed(news_sentiment))

    # Trading history
    if memory_context:
        parts.append("\n### Historical Performance")
        parts.append(f"{memory_context[:300]}")  # More context

    parts.append("\n### Required Analysis")
    parts.append("Provide a complete trading recommendation with:")
    parts.append("1. Clear BUY/SELL/HOLD recommendation with confidence level")
    parts.append("2. Specific entry price, stop-loss, and take-profit levels")
    parts.append("3. Key technical factors supporting the trade")
    parts.append("4. Main risks to consider")
    parts.append("5. Suggested position size based on setup quality")

    return "\n".join(parts)


def format_technical_detailed(data: Dict[str, Any]) -> str:
    """Format technical data in detailed form for Ollama"""
    price = data.get('current_price', 0)
    change = data.get('change_pct', data.get('daily_change', 0))
    if isinstance(change, float) and abs(change) < 1:
        change *= 100  # Convert decimal to percentage

    rsi = data.get('rsi', 50)
    macd = data.get('macd', 0)
    macd_sig = data.get('macd_signal', 0)
    macd_hist = data.get('macd_histogram', macd - macd_sig)
    vol_ratio = data.get('volume_ratio', 1)
    volume = data.get('volume', 0)
    avg_volume = data.get('avg_volume', 0)

    # Moving averages
    sma_20 = data.get('sma_20', data.get('sma20', 0))
    sma_50 = data.get('sma_50', data.get('sma50', 0))
    ema_9 = data.get('ema_9', data.get('ema9', 0))

    # Support/Resistance
    high = data.get('high', data.get('day_high', 0))
    low = data.get('low', data.get('day_low', 0))
    open_price = data.get('open', 0)
    prev_close = data.get('prev_close', 0)

    # ATR for volatility
    atr = data.get('atr', 0)

    lines = [
        f"- Current Price: ${price:.2f} ({change:+.2f}% today)",
        f"- Day Range: ${low:.2f} - ${high:.2f}",
        f"- Open: ${open_price:.2f} | Prev Close: ${prev_close:.2f}",
        f"- Volume: {volume:,.0f} ({vol_ratio:.1f}x average)",
    ]

    # Indicators
    rsi_signal = "OVERSOLD" if rsi < 30 else ("OVERBOUGHT" if rsi > 70 else "NEUTRAL")
    lines.append(f"- RSI(14): {rsi:.1f} ({rsi_signal})")

    macd_signal = "BULLISH" if macd > macd_sig else "BEARISH"
    lines.append(f"- MACD: {macd:.3f} | Signal: {macd_sig:.3f} | Histogram: {macd_hist:.3f} ({macd_signal})")

    if sma_20 > 0:
        trend = "ABOVE" if price > sma_20 else "BELOW"
        lines.append(f"- SMA(20): ${sma_20:.2f} (price is {trend})")

    if sma_50 > 0:
        trend = "ABOVE" if price > sma_50 else "BELOW"
        lines.append(f"- SMA(50): ${sma_50:.2f} (price is {trend})")

    if atr > 0:
        lines.append(f"- ATR(14): ${atr:.2f} (volatility measure)")

    return "\n".join(lines)


def format_technical_compact(data: Dict[str, Any]) -> str:
    """Format technical data in compact form (legacy)"""
    price = data.get('current_price', 0)
    change = data.get('change_pct', data.get('daily_change', 0))
    if isinstance(change, float) and abs(change) < 1:
        change *= 100  # Convert decimal to percentage

    rsi = data.get('rsi', 50)
    macd = data.get('macd', 0)
    macd_sig = data.get('macd_signal', 0)
    vol_ratio = data.get('volume_ratio', 1)

    # Build compact string
    macd_dir = "+" if macd > macd_sig else "-"
    return f"${price:.2f} {change:+.1f}% RSI:{rsi:.0f} MACD:{macd_dir} Vol:{vol_ratio:.1f}x"


def format_market_detailed(context: Dict) -> str:
    """Format market context in detail for Ollama"""
    spy = context.get('spy', {})
    vix = context.get('vix', {})
    qqq = context.get('qqq', {})
    regime = context.get('regime', 'neutral')

    spy_chg = spy.get('change_pct', 0) if spy else 0
    spy_price = spy.get('price', 0) if spy else 0
    vix_val = vix.get('value', 20) if vix else 20
    qqq_chg = qqq.get('change_pct', 0) if qqq else 0

    # Interpret VIX
    if vix_val < 15:
        vix_interp = "LOW VOLATILITY - Complacency, good for momentum"
    elif vix_val < 20:
        vix_interp = "NORMAL - Healthy market conditions"
    elif vix_val < 30:
        vix_interp = "ELEVATED - Caution advised, tighter stops"
    else:
        vix_interp = "HIGH FEAR - Extreme caution, potential reversal"

    # Regime interpretation
    regime_map = {
        'risk_on': 'RISK-ON: Favorable for long positions',
        'risk_off': 'RISK-OFF: Favor cash or defensive positions',
        'neutral': 'NEUTRAL: Mixed signals, be selective',
        'high_volatility': 'HIGH VOLATILITY: Reduce position sizes'
    }
    regime_desc = regime_map.get(regime, regime)

    lines = [
        f"- Market Regime: {regime_desc}",
        f"- S&P 500 (SPY): ${spy_price:.2f} ({spy_chg:+.2f}%)",
        f"- NASDAQ (QQQ): {qqq_chg:+.2f}%",
        f"- VIX: {vix_val:.1f} ({vix_interp})",
    ]

    return "\n".join(lines)


def format_market_compact(context: Dict) -> str:
    """Format market context compactly (legacy)"""
    spy = context.get('spy', {})
    vix = context.get('vix', {})
    regime = context.get('regime', 'neutral')

    spy_chg = spy.get('change_pct', 0) if spy else 0
    vix_val = vix.get('value', 20) if vix else 20

    return f"Mkt:{regime} SPY:{spy_chg:+.1f}% VIX:{vix_val:.0f}"


def format_news_detailed(sentiment: Dict) -> str:
    """Format news sentiment in detail for Ollama"""
    overall = sentiment.get('overall_sentiment', 'neutral')
    score = sentiment.get('overall_score', 0)
    article_count = sentiment.get('article_count', 0)
    headlines = sentiment.get('headlines', [])

    # Interpret sentiment
    if score > 0.3:
        interp = "POSITIVE - Bullish catalyst"
    elif score < -0.3:
        interp = "NEGATIVE - Bearish headwind"
    else:
        interp = "NEUTRAL - No strong sentiment"

    lines = [
        f"- Overall Sentiment: {overall.upper()} (score: {score:+.2f})",
        f"- Interpretation: {interp}",
        f"- Articles Analyzed: {article_count}",
    ]

    if headlines:
        lines.append("- Recent Headlines:")
        for h in headlines[:3]:  # Top 3 headlines
            lines.append(f"  • {h[:100]}")

    return "\n".join(lines)


def format_news_compact(sentiment: Dict) -> str:
    """Format news sentiment compactly (legacy)"""
    overall = sentiment.get('overall_sentiment', 'neutral')
    score = sentiment.get('overall_score', 0)
    return f"News:{overall}({score:+.1f})"


# Legacy functions for backward compatibility
def format_technical_data(symbol: str, data: Dict[str, Any]) -> str:
    """Legacy format - redirects to compact"""
    return f"**{symbol}**\n{format_technical_compact(data)}"


def format_news_sentiment(sentiment: Dict) -> str:
    """Legacy format"""
    return format_news_compact(sentiment)


def format_market_context(context: Dict) -> str:
    """Legacy format"""
    return format_market_compact(context)

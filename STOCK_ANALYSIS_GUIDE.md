# 📊 Stock Analysis Guide - Claude Prompt-Based System

## 🎯 Purpose
This guide provides instructions for using Claude to analyze stocks in real-time and make informed investment decisions without requiring code execution or deployment.

## 🚀 How to Use This System

### 1. Daily Stock Analysis Workflow

**Morning Routine** (Before Market Opens - 9:30 AM EST):
```
Ask Claude: "Analyze my holdings in HOLDINGS.md and provide pre-market insights.
Check news, sentiment, and technical indicators for each stock."
```

**During Market Hours** (9:30 AM - 4:00 PM EST):
```
Ask Claude: "Give me real-time analysis for [TICKER]. Include:
- Current price and price movement
- Recent news and sentiment analysis
- Technical indicators (RSI, MACD, moving averages)
- Trading signals and recommendations"
```

**End of Day Review** (After 4:00 PM EST):
```
Ask Claude: "Review today's performance for my holdings in HOLDINGS.md.
Provide summary of gains/losses and recommendations for tomorrow."
```

### 2. Analysis Types You Can Request

#### 📈 Technical Analysis
Ask Claude to analyze:
- **Price Trends**: Moving averages (SMA, EMA), support/resistance levels
- **Momentum Indicators**: RSI, MACD, Stochastic Oscillator
- **Volume Analysis**: Volume trends, unusual activity
- **Chart Patterns**: Head & shoulders, triangles, breakouts
- **Volatility**: Bollinger Bands, ATR

Example prompt:
```
"Analyze TSLA technical indicators. Show RSI, MACD, 50/200 day moving averages,
and identify key support/resistance levels."
```

#### 📰 News & Sentiment Analysis
Ask Claude to:
- Search recent news (last 24-48 hours)
- Analyze sentiment (positive, negative, neutral)
- Assess impact on stock price
- Identify market-moving catalysts

Example prompt:
```
"Search for AAPL news from the last 24 hours. Analyze sentiment and
potential impact on stock price."
```

#### 💡 Trading Signals & Recommendations
Ask Claude for:
- **BUY signals**: Strong positive indicators
- **SELL signals**: Warning signs or negative trends
- **HOLD recommendations**: Maintain current position
- **Price targets**: Entry/exit points
- **Stop-loss levels**: Risk management

Example prompt:
```
"Based on current market conditions, should I buy, sell, or hold NVDA?
Provide confidence level and reasoning."
```

#### 📊 Portfolio Analysis
Ask Claude to:
- Review overall portfolio performance
- Analyze diversification and risk
- Suggest rebalancing strategies
- Calculate returns and metrics

Example prompt:
```
"Analyze my portfolio in HOLDINGS.md. Check diversification, calculate total return,
and suggest any rebalancing needed."
```

### 3. Real-Time Data Sources

Claude can access real-time information through:
- **Web Search**: Latest news, analyst reports, financial data
- **Market Data**: Current prices, volume, market cap
- **News APIs**: Recent headlines and sentiment
- **Financial Websites**: Yahoo Finance, MarketWatch, Bloomberg, etc.

### 4. Advanced Analysis Requests

#### Sector Analysis
```
"Analyze the technology sector today. Which tech stocks are showing strength?
Compare AAPL, MSFT, GOOGL, and NVDA."
```

#### Comparative Analysis
```
"Compare TSLA vs RIVN. Which is a better buy right now based on fundamentals,
technicals, and recent news?"
```

#### Market Overview
```
"What's the overall market sentiment today? Analyze major indices (SPY, QQQ, DIA)
and identify key market drivers."
```

#### Earnings Analysis
```
"When is MSFT's next earnings date? Analyze last quarter's results and
expectations for upcoming report."
```

### 5. Risk Management Prompts

```
"For my position in [TICKER], calculate:
- Appropriate position size (max 15% of portfolio)
- Stop-loss level (2% below entry)
- Take-profit target (risk/reward ratio 1:3)
- Overall portfolio risk"
```

### 6. Decision-Making Framework

When asking Claude for trading advice, always request:

1. **Current Analysis**
   - Real-time price and movement
   - Technical indicator status
   - News sentiment

2. **Historical Context**
   - Recent price action
   - Support/resistance levels
   - Volume trends

3. **Future Outlook**
   - Short-term (1-7 days)
   - Medium-term (1-4 weeks)
   - Catalysts to watch

4. **Action Recommendation**
   - Clear BUY/SELL/HOLD signal
   - Confidence level (High/Medium/Low)
   - Reasoning and risk factors

### 7. Tracking Your Decisions

After each trading decision:
```
"Update HOLDINGS.md with my [BUY/SELL] of [SHARES] shares of [TICKER] at $[PRICE].
Calculate new position size and portfolio allocation."
```

Log your trades:
```
"Add to TRADE_LOG.md: Date, ticker, action, shares, price, reasoning,
and expected outcome."
```

### 8. Weekly/Monthly Reviews

**Weekly Review**:
```
"Review my trading performance for this week. Analyze:
- Total return vs SPY benchmark
- Best/worst performers
- Win rate and average gain/loss
- Lessons learned and adjustments needed"
```

**Monthly Review**:
```
"Provide comprehensive monthly analysis:
- Portfolio return vs benchmarks
- Risk metrics (volatility, max drawdown)
- Strategy effectiveness
- Recommendations for next month"
```

## 🎯 Best Practices

### DO:
✅ Ask Claude to verify information from multiple sources
✅ Request confidence levels with all recommendations
✅ Use Claude for both fundamental and technical analysis
✅ Keep your HOLDINGS.md updated after each trade
✅ Ask for risk assessment before making decisions
✅ Review Claude's reasoning, don't blindly follow

### DON'T:
❌ Make decisions based solely on one analysis
❌ Forget to update your holdings file
❌ Ignore risk management principles
❌ Trade emotionally - use Claude for objective analysis
❌ Risk more than you can afford to lose

## 📋 Sample Daily Workflow

**9:00 AM** - Pre-market analysis
```
"Analyze my holdings and check pre-market movers. Any urgent actions needed?"
```

**10:00 AM** - Market open review
```
"How are markets opening? Check my holdings for any significant moves."
```

**12:00 PM** - Mid-day check
```
"Mid-day market update. Any news affecting my positions?"
```

**3:30 PM** - Before close
```
"Final 30 minutes. Any positions I should close today?"
```

**5:00 PM** - End of day
```
"Summarize today's performance and prepare watchlist for tomorrow."
```

## 🔧 Customization

You can customize your analysis by:
- Modifying the watchlist in HOLDINGS.md
- Adjusting risk parameters (stop-loss %, position size)
- Focusing on specific sectors or strategies
- Setting alerts for price targets

## ⚠️ Important Disclaimers

- **Not Financial Advice**: Claude provides analysis, not investment advice
- **DYOR**: Always do your own research before trading
- **Risk Management**: Never risk more than you can afford to lose
- **Real-Time Data**: Market data may have slight delays
- **Educational Purpose**: This system is for learning and analysis

## 📞 Getting Help

If you need specific analysis:
1. Be clear and specific in your prompts
2. Provide context (your holdings, risk tolerance, timeframe)
3. Ask follow-up questions to clarify
4. Request different perspectives or scenarios

## 🎓 Learning Resources

Ask Claude to explain:
- Trading concepts (options, shorts, margin)
- Technical indicators (how RSI works, MACD interpretation)
- Fundamental analysis (P/E ratio, revenue growth)
- Market mechanics (bid/ask, market orders, limit orders)

---

**Remember**: Claude is your analytical partner. Use it to make informed decisions, but always maintain your own judgment and risk management principles.

# Claude Instructions - AI Trading Agent Project

## CRITICAL RULES - ALWAYS FOLLOW

### 🔴 NEVER Say "Fixed" Without Proof

**WRONG**: "I fixed the bug, everything should work now"
**RIGHT**: "I made changes. Running validation test... [test output]. Test passed ✅"

**Rule**: Every fix MUST include a validation test that proves it works.

---

## Pre-Deployment Validation (MANDATORY)

Before telling the user "it's ready to run", you MUST execute ALL these steps:

### 1. Stop Loss & Take Profit Validation

```bash
source .venv/bin/activate && python3 << 'EOF'
from agent.strategies.aggressive_dip import AggressiveDipStrategy, AggressiveDipConfig

config = AggressiveDipConfig()
strategy = AggressiveDipStrategy(config)

# Test data
closes = [55, 54, 53, 52.5, 52, 51.5, 51, 50.5, 50, 49.5, 49, 48.5, 48, 47.5, 53.84]
highs = [c * 1.05 for c in closes]
lows = [c * 0.95 for c in closes]

signal = strategy.generate_signal('TEST', closes, highs, lows, has_position=False)

# CRITICAL CHECKS
stop_ok = signal.stop_loss < signal.entry_price  # Stop MUST be below entry
target_ok = signal.take_profit > signal.entry_price  # Target MUST be above entry
stop_pct = ((signal.stop_loss - signal.entry_price) / signal.entry_price) * 100
target_pct = ((signal.take_profit - signal.entry_price) / signal.entry_price) * 100

print(f"Entry: ${signal.entry_price:.2f}")
print(f"Stop: ${signal.stop_loss:.2f} ({stop_pct:+.1f}%) - Expected: -2.0%")
print(f"Target: ${signal.take_profit:.2f} ({target_pct:+.1f}%) - Expected: +10.0%")

assert stop_ok, f"❌ STOP LOSS ABOVE ENTRY: {signal.stop_loss} >= {signal.entry_price}"
assert target_ok, f"❌ TAKE PROFIT BELOW ENTRY: {signal.take_profit} <= {signal.entry_price}"
assert abs(stop_pct + 2.0) < 0.1, f"❌ STOP PCT WRONG: {stop_pct}% != -2.0%"
assert abs(target_pct - 10.0) < 0.1, f"❌ TARGET PCT WRONG: {target_pct}% != +10.0%"

print("✅ ALL CHECKS PASSED")
EOF
```

### 2. Clear Python Cache

```bash
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
echo "✅ Cache cleared"
```

### 3. Check for Running Processes

```bash
ps aux | grep "[p]ython.*aggressive"
# If any process found: kill <PID>
```

### 4. Verify Alpaca Connection

```bash
source .venv/bin/activate && python3 << 'EOF'
import asyncio
from alpaca.client import AlpacaClient

async def test():
    client = AlpacaClient()
    account = await client.get_account()
    print(f"✅ Account: ${float(account.equity):,.2f}")

asyncio.run(test())
EOF
```

---

## Common Bugs & How to Avoid Them

### Bug History (Last 7 Days)

| Date | Bug | Root Cause | Prevention |
|------|-----|------------|------------|
| Mar 3 | Stop loss inverted (above entry instead of below) | Wrong sign in calculation: `(1 + pct)` instead of `(1 - pct)` | Always run validation test #1 |
| Mar 2 | Qty mismatch after buy | Position sync didn't handle pre-existing positions | Always validate qty immediately after buy |
| Mar 2 | Network errors spamming logs | No retry logic | Add exponential backoff for all network calls |
| Feb 27 | Agent didn't trade for 2 days | Old process running with cached bytecode | Always check for running processes, clear cache |

### Critical Calculations

**ALWAYS verify these patterns:**

```python
# CORRECT ✅
stop_loss = current_price * (1 - stop_pct)      # MINUS for stop
take_profit = current_price * (1 + profit_pct)  # PLUS for target

# WRONG ❌
stop_loss = current_price * (1 + stop_pct)      # Would put stop ABOVE entry
take_profit = current_price * (1 - profit_pct)  # Would put target BELOW entry
```

---

## Development Workflow

### Making Changes to Trading Logic

1. **Read the current code first**
   ```bash
   # Never edit without reading
   Read agent/strategies/aggressive_dip.py
   ```

2. **Make changes**
   - Edit only what's needed
   - Don't refactor unnecessarily

3. **Clear cache** (mandatory after any .py file change)
   ```bash
   find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
   ```

4. **Run validation tests** (all of them, see section above)

5. **Only then** tell user it's ready

### Adding New Symbols

See `AGENT_MAINTENANCE.md` for the full process. Summary:
1. Backtest first: `python -m backtest.daily --symbols SYMBOL1,SYMBOL2`
2. Only add if backtest shows positive results
3. Update `aggressive_dip.py` config
4. Clear cache before restart

### Updating Groq Model

1. Check available models: https://console.groq.com/docs/models
2. Update `agent/core/groq_client.py`: `model="new-model-name"`
3. Clear cache
4. Test with validation #4 (Alpaca connection includes Groq test)

---

## Debugging Failed Trades

### When User Reports "Agent Sold Too Early"

1. **Check the logs** (never assume)
   ```bash
   cat logs/trades/trades_YYYY-MM-DD.jsonl | grep "symbol.*SOXL"
   ```

2. **Extract exact values**
   ```python
   import json
   with open('logs/trades/trades_2026-03-03.jsonl') as f:
       for line in f:
           trade = json.loads(line)
           if trade['symbol'] == 'SOXL':
               print(f"Entry: {trade['entry_price']}")
               print(f"Stop: {trade['stop_loss']}")
               print(f"Target: {trade['target_1']}")
   ```

3. **Verify calculation logic**
   - Is stop_loss < entry_price? ✅
   - Is take_profit > entry_price? ✅
   - Are percentages correct? ✅

4. **Check for running processes with old code**
   ```bash
   ps aux | grep python
   # Check start time - if > 1 hour old, might have stale code
   ```

### When Agent Doesn't Trade

1. **Check if process is running**
   ```bash
   ps aux | grep "[p]ython.*aggressive"
   ```

2. **Check logs for errors**
   ```bash
   tail -50 logs/trades/trades_$(date +%Y-%m-%d).jsonl
   ```

3. **Verify market hours**
   - Agent only scans at 15:45 ET (12:45 PT)
   - Market must be open

4. **Check if signals are generated but rejected**
   - Look for "SKIP" actions in logs
   - Check AI rejection reasons

---

## Code Quality Standards

### DO

- ✅ Test every change before saying it works
- ✅ Clear cache after editing .py files
- ✅ Check for running processes before starting agent
- ✅ Validate calculations match expected percentages
- ✅ Include actual test output when reporting "fixed"
- ✅ Check git status before making changes
- ✅ Read existing code before editing

### DON'T

- ❌ Say "should work" without testing
- ❌ Assume cache is clean
- ❌ Skip validation tests
- ❌ Make assumptions about what's running
- ❌ Change code without reading it first
- ❌ Refactor unnecessarily
- ❌ Add features not explicitly requested

---

## Quick Reference

### Start Agent (After Validation)
```bash
cd /Users/gustavoiribarne/Documents/projects/projectin
source .venv/bin/activate
python -m cli.main --aggressive
```

### Stop Agent
```bash
ps aux | grep "[p]ython.*aggressive" | awk '{print $2}' | xargs kill
```

### View Today's Trades
```bash
cat logs/trades/trades_$(date +%Y-%m-%d).jsonl | python3 -m json.tool
```

### Run Backtest
```bash
python -m backtest.daily --start 2025-09-01 --end 2025-12-31
```

---

## Architecture Notes

### Key Files

- `agent/strategies/aggressive_dip.py` - Signal generation logic (CRITICAL)
- `agent/core/aggressive_agent.py` - Main agent orchestration
- `agent/core/groq_client.py` - AI filter using Groq Llama 3.3 70B
- `agent/core/trade_logger.py` - Trade logging for learning
- `alpaca/client.py` - Alpaca API integration
- `alpaca/executor.py` - Order execution with risk management

### How the Agent Works

1. **15:45 ET**: Scan all symbols
2. **Generate signals**: Using `aggressive_dip.py` strategy
3. **AI filter**: Groq analyzes each signal (optional)
4. **Risk check**: Verify position limits, PDT rules
5. **Execute**: Submit order to Alpaca
6. **Monitor**: Check stop loss, trailing stop, take profit every 30s
7. **Close**: Sell when conditions met
8. **Log**: Save decision + outcome to JSONL

### Strategy Parameters (CONFIRMED VIA BACKTEST)

```python
stop_loss_pct: 0.02        # 2% stop loss
take_profit_pct: 0.10      # 10% take profit
trailing_stop_pct: 0.02    # 2% trailing stop
max_positions: 2           # Max 2 concurrent positions
position_size_pct: 0.50    # 50% of equity per position
max_rsi: 45.0             # RSI must be < 45 for entry
min_prev_day_drop: -0.01  # Previous day must be red
```

**Do NOT change these without backtesting first.**

---

## User Expectations

The user expects:
1. **No surprises**: If you say it works, it MUST work
2. **Proof**: Show test output, not assumptions
3. **Honesty**: If unsure, say so - don't guess
4. **Quality**: One fix should work, not daily patches
5. **Speed**: Fix issues decisively, not iteratively

Remember: This is real money (paper trading, but still). Bugs cost user time and trust.

---

## Emergency Procedures

### If Agent is Losing Money

1. **Stop immediately**
   ```bash
   ps aux | grep "[p]ython.*aggressive" | awk '{print $2}' | xargs kill
   ```

2. **Close all positions manually** (if needed)
   ```bash
   # Log into Alpaca dashboard: https://app.alpaca.markets
   # Or use CLI to close positions
   ```

3. **Investigate logs**
   ```bash
   cat logs/trades/trades_$(date +%Y-%m-%d).jsonl
   ```

4. **Don't restart until root cause is found**

### If Agent Won't Start

1. Check for running processes
2. Check logs for Python tracebacks
3. Verify .env has API keys
4. Test Alpaca connection separately
5. Clear all cache
6. Check Python version (should be 3.14)

---

## Final Checklist Before Deployment

```
□ Ran stop loss validation test (test #1)
□ Cleared all __pycache__ directories
□ No processes running (ps aux check)
□ Alpaca connection verified (test #4)
□ Recent logs reviewed for anomalies
□ User informed with ACTUAL test output (not assumptions)
```

If ALL checkboxes checked: ✅ Ready to deploy
If ANY checkbox unchecked: ❌ DO NOT DEPLOY

# Agent Maintenance Guide

Manual instructions for maintaining and improving the aggressive trading agent.

---

## 1. Analyze Trade Logs

### Quick Stats (últimos 7 días)
```bash
source .venv/bin/activate
python -c "
from agent.core.trade_logger import TradeLogger
logger = TradeLogger()
stats = logger.get_win_rate(days=7)
print(f'Win Rate: {stats[\"win_rate\"]:.0%}')
print(f'Total Trades: {stats[\"total_trades\"]}')
print(f'Wins: {stats[\"wins\"]} | Losses: {stats[\"losses\"]}')
print(f'Avg P&L: {stats[\"avg_pnl_percent\"]:.2f}%')
"
```

### View Recent Trades
```bash
# Ver últimos 10 trades de hoy
cat logs/trades/trades_$(date +%Y-%m-%d).jsonl | python -m json.tool | head -100

# Ver todos los trades de un día específico
cat logs/trades/trades_2026-02-27.jsonl | python -m json.tool

# Contar trades por símbolo
cat logs/trades/trades_*.jsonl | grep -o '"symbol": "[^"]*"' | sort | uniq -c | sort -rn
```

### Analyze Winning vs Losing Patterns
```bash
source .venv/bin/activate
python -c "
import json
from pathlib import Path

wins, losses = [], []
for f in Path('logs/trades').glob('trades_*.jsonl'):
    for line in open(f):
        try:
            d = json.loads(line)
            if d.get('outcome') and d.get('executed'):
                if d['outcome'].get('profitable'):
                    wins.append(d)
                else:
                    losses.append(d)
        except: pass

print(f'=== WINNING TRADES ({len(wins)}) ===')
for w in wins[-5:]:
    print(f\"{w['symbol']}: {w['outcome']['pnl_percent']:+.1f}% | RSI={w['technical_data'].get('rsi', 'N/A'):.0f} | {w['reasoning'][:60]}...\")

print(f'\n=== LOSING TRADES ({len(losses)}) ===')
for l in losses[-5:]:
    print(f\"{l['symbol']}: {l['outcome']['pnl_percent']:+.1f}% | RSI={l['technical_data'].get('rsi', 'N/A'):.0f} | {l['reasoning'][:60]}...\")
"
```

---

## 2. Analyze New Symbols

### Step 1: Run Backtest for Candidate Symbol
```bash
source .venv/bin/activate
python -c "
import asyncio
from backtest.aggressive_ai_backtest import run_single_symbol_backtest

# Cambiar 'SYMBOL' por el símbolo a analizar
asyncio.run(run_single_symbol_backtest('PLTR', months=6))
"
```

Si el método no existe, usar el backtest completo modificando temporalmente los símbolos:

```bash
# 1. Editar agent/core/aggressive_agent.py línea ~103
# Cambiar la lista de symbols temporalmente para incluir el nuevo

# 2. Correr backtest
source .venv/bin/activate
python -c "
import asyncio
from backtest.aggressive_ai_backtest import run_comparison
asyncio.run(run_comparison('h1_2025'))
"

# 3. Revertir cambios en aggressive_agent.py
```

### Step 2: Criteria for Adding Symbol
Un símbolo es candidato si:
- [ ] Retorno mensual promedio > 5%
- [ ] Win rate > 40%
- [ ] Tiene suficiente volatilidad (rango diario > 2%)
- [ ] Es líquido (spread bajo, fácil de ejecutar)
- [ ] No está altamente correlacionado con símbolos existentes

### Step 3: Add Symbol to Agent
Editar `agent/core/aggressive_agent.py` línea ~103:
```python
self.symbols = [
    'SOXL', 'SMCI', 'MARA', 'COIN',
    'MU', 'AMD', 'NVDA', 'TSLA',
    'NEW_SYMBOL',  # Agregar aquí
]
```

---

## 3. Update Groq Model

### Step 1: Check Available Models
```bash
# Ver modelos disponibles en Groq
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY" | python -m json.tool | grep '"id"'
```

O visitar: https://console.groq.com/docs/models

### Step 2: Compare Model Performance (Optional)
```bash
source .venv/bin/activate
python -c "
import asyncio
from agent.core.groq_client import GroqClient

async def test_model(model_name):
    # Temporarily test a different model
    client = GroqClient()
    client.MODEL = model_name  # Override

    result = await client.analyze_trade(
        symbol='NVDA',
        current_price=180.0,
        prev_day_change=-0.025,
        day_range=0.035,
        rsi=38.0,
        support_distance=0.02,
        market_trend='NEUTRAL',
    )
    print(f'Model: {model_name}')
    print(f'Action: {result.action} | Confidence: {result.confidence:.0%}')
    print(f'Reasoning: {result.reasoning}')

# Cambiar 'llama-3.3-70b-versatile' por el modelo a probar
asyncio.run(test_model('llama-3.3-70b-versatile'))
"
```

### Step 3: Update Model in Code
Editar `agent/core/groq_client.py` línea ~46:
```python
MODEL = "nuevo-modelo-aqui"  # Cambiar este valor
```

### Current Model Info
- **Model**: `llama-3.3-70b-versatile`
- **Updated**: Feb 2026
- **Rate Limits (Free)**: 30 RPM, 1000 RPD, 100K TPD

---

## 4. Adjust Strategy Parameters

### Current Parameters (aggressive_agent.py ~76-82)
```python
min_prev_day_drop: float = -0.01   # Día anterior debe ser rojo
min_day_range: float = 0.02        # 2% rango mínimo
max_rsi: float = 45.0              # RSI < 45
stop_loss_pct: float = 0.02        # 2% stop loss
take_profit_pct: float = 0.10      # 10% take profit
trailing_stop_pct: float = 0.02    # 2% trailing stop
max_hold_days: int = 4             # Máximo 4 días
```

### To Test Parameter Changes
1. Modificar parámetros en `agent/core/aggressive_agent.py`
2. Correr backtest:
```bash
source .venv/bin/activate
python -c "
import asyncio
from backtest.aggressive_ai_backtest import run_comparison
asyncio.run(run_comparison('h1_2025'))
"
```
3. Comparar resultados con baseline (+51.4% H1 2025)
4. Si mejora, mantener. Si empeora, revertir.

---

## 5. Check Agent Health

### Verify All Components Working
```bash
source .venv/bin/activate
python -c "
import asyncio
from agent.core.aggressive_agent import AggressiveTradingAgent

async def health_check():
    agent = AggressiveTradingAgent()

    # 1. Alpaca
    account = await agent.alpaca_client.get_account()
    print(f'✅ Alpaca: \${float(account.equity):.2f}')

    # 2. Groq
    if agent.groq_client:
        ok = await agent.groq_client.test_connection()
        print(f'{'✅' if ok else '❌'} Groq AI: {'Connected' if ok else 'Failed'}')

    # 3. Quote
    quote = await agent.alpaca_client.get_quote('NVDA')
    print(f'✅ Quotes: NVDA \${(quote.bid_price + quote.ask_price) / 2:.2f}')

    # 4. TradeLogger
    print(f'✅ TradeLogger: {agent.trade_logger.log_dir}')

    await agent.alpaca_client.close()

asyncio.run(health_check())
"
```

### Check Logs for Errors
```bash
# Errores de hoy
grep -i error logs/agent.log | tail -20

# Errores de la última semana
grep -i error logs/agent.log | grep "$(date +%Y-%m)" | tail -50
```

---

## 6. Clear Cache (if issues)

```bash
# Limpiar cache de Python (si hay comportamiento extraño)
find /Users/gustavoiribarne/Documents/projects/projectin -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# Limpiar cache de backtest
rm -rf backtest/cache/*.json
```

---

## 7. API Keys & Limits

### Groq (Free Tier)
- **Limits**: 30 requests/min, 1000/day, 100K tokens/day
- **Dashboard**: https://console.groq.com/
- **Key Location**: `.env` → `GROQ_API_KEY`

### Alpaca (Paper Trading)
- **Dashboard**: https://app.alpaca.markets/paper/dashboard
- **Key Location**: `.env` → `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`

---

## Quick Reference

| Task | Command |
|------|---------|
| Run agent | `python -m cli.main --aggressive` |
| Health check | See Section 5 |
| View trade logs | `cat logs/trades/trades_$(date +%Y-%m-%d).jsonl` |
| Win rate stats | See Section 1 |
| Test new symbol | See Section 2 |
| Update Groq model | Edit `groq_client.py` line 46 |
| Add symbol | Edit `aggressive_agent.py` line ~103 |
| Clear cache | `find . -name "__pycache__" -exec rm -rf {} +` |

---

## File Locations

| Component | File |
|-----------|------|
| Agent config | `agent/core/aggressive_agent.py` |
| Groq client | `agent/core/groq_client.py` |
| Trade logger | `agent/core/trade_logger.py` |
| Trade logs | `logs/trades/trades_YYYY-MM-DD.jsonl` |
| API keys | `.env` |
| Backtest | `backtest/aggressive_ai_backtest.py` |

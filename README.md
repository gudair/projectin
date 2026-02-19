# 📊 Stock Analysis System - Claude Prompt-Based

A Claude-powered stock analysis system for real-time market insights and investment decision-making. No code execution or deployment required.

---

## 🤖 AI Trading Agent (v2.0 - Advanced)

An autonomous AI trading agent with Alpaca integration, advanced risk management, and machine learning capabilities.

### Core Features
- **Real-time market data** via Alpaca WebSocket
- **AI-powered analysis** using Ollama (local LLM - free) or Claude API
- **Autonomous trading** with intelligent position management
- **Learning from past trades** via Layered Memory System
- **Advanced risk management** with multiple safety layers

### 🆕 Advanced Features (Recently Implemented)

| Feature | Description |
|---------|-------------|
| **ATR Dynamic Stops** | Volatility-based stop-loss that adapts to market conditions |
| **Periodic Reflection** | Agent learns from every N trades, adjusts confidence |
| **Layered Memory** | 3-tier memory (Working/Short-term/Deep) for pattern learning |
| **Position Intelligence** | Kelly Criterion + Drawdown Protection + Session Awareness |
| **Trade Intelligence** | Bull/Bear debate + Self-reflection before each trade |
| **News Sentiment** | Alpaca News API + LLM analysis |
| **Analyst Ratings** | Yahoo Finance integration |
| **Momentum Scanner** | High-probability setup detection |

### Quick Start

```bash
# 1. Create virtual environment and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure API keys in .env
cp .env.example .env
# Edit .env with your Alpaca and Anthropic API keys

# 3. Verify setup
source .venv/bin/activate
python agent_setup.py

# 4. Run the agent
source .venv/bin/activate
python -m cli.main --dashboard          # Recommended: Dashboard visual en vivo
```

### Getting API Keys

| Servicio | URL | Costo |
|----------|-----|-------|
| **Alpaca** (Paper Trading) | https://app.alpaca.markets/paper/dashboard/overview | Gratis |
| **Anthropic** (Claude API) | https://console.anthropic.com/ | ~$0.01/análisis |

> **Nota**: Claude.ai (suscripción Max/Pro) y Anthropic API son productos **separados**. Necesitas crear cuenta en console.anthropic.com para obtener API key.

### Alpaca para Usuarios Internacionales

Alpaca **sí acepta usuarios fuera de USA**:
- Mínimo de cuenta: $1 USD
- Depósitos via Rapyd (transferencia internacional)
- Sin comisiones en trading de acciones USA
- KYC: Pasaporte + selfie

### CLI Commands

| Comando | Descripción |
|---------|-------------|
| `python -m cli.main --auto` | **🤖 AUTÓNOMO**: Ejecuta trades automáticamente + resumen diario |
| `python -m cli.main --dashboard` | Dashboard visual con confirmación manual |
| `python -m cli.main --paper` | Modo simple (terminal básica) |
| `python -m cli.main --watch AAPL TSLA` | Watchlist personalizada |
| `python -m cli.main --no-trade` | Solo análisis, sin ejecutar trades |
| `python -m cli.main --help` | Ver todas las opciones |

### Modos de Operación

| Flag | Modo | Confirmación | Resumen |
|------|------|--------------|---------|
| `--auto` | **Autónomo** | ❌ Automática | ✅ Al cerrar mercado |
| `--dashboard` | Manual | ✅ Tú decides | ❌ |
| `--paper` | Manual simple | ✅ Tú decides | ❌ |

### 🤖 Modo Autónomo (--auto)

El modo autónomo ejecuta trades **sin confirmación manual**. Ideal para paper trading.

```bash
# Ejecutar en modo autónomo
python -m cli.main --auto

# Con watchlist personalizada
python -m cli.main --auto --watch AAPL NVDA TSLA
```

**Flujo autónomo:**
```
┌─────────────────────────────────────────────────────────────┐
│  09:30 → Mercado abre → Agente inicia                       │
│            ↓                                                │
│  Durante el día:                                            │
│    🔍 Monitorea watchlist                                   │
│    🧠 Claude analiza oportunidades                          │
│    ⚡ Ejecuta trades AUTOMÁTICAMENTE                        │
│    📝 Log de todas las operaciones                          │
│            ↓                                                │
│  16:00 → Mercado cierra → Resumen del día:                  │
│    ┌────────────────────────────────────────┐               │
│    │ 📊 DAILY TRADING SUMMARY               │               │
│    │ Portfolio Value: $100,250.00           │               │
│    │ Daily P&L: +$250.00 (+0.25%)           │               │
│    │ Trades: 5 | Win Rate: 80%              │               │
│    │ Holdings: AAPL (10), NVDA (5)          │               │
│    └────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

**Características del modo autónomo:**
- ✅ Auto-ejecuta trades cuando Claude recomienda
- ✅ Genera resumen diario al cerrar mercado
- ✅ Muestra cada trade en tiempo real
- ✅ Espera automáticamente si mercado está cerrado
- ⚠️ Solo recomendado para paper trading

### 🔍 Stock Discovery (Descubrimiento Dinámico)

El agente **NO está limitado a un watchlist fijo**. Descubre automáticamente acciones interesantes basándose en:

**Fuentes de descubrimiento:**
- 📈 **Top Gainers**: Acciones con mayor subida del día
- 📉 **Top Losers**: Acciones con mayor caída (potencial rebote)
- 📊 **Volumen Inusual**: Acciones con volumen 2x+ sobre promedio
- 🔥 **Alpaca Movers**: Datos en tiempo real de la API de Alpaca

**Configuración (en `config/agent_config.py`):**
```python
@dataclass
class DiscoveryConfig:
    enabled: bool = True                # Activar descubrimiento
    scan_interval_minutes: int = 30     # Cada 30 min busca nuevas acciones
    min_price: float = 5.0              # Precio mínimo $5
    max_price: float = 500.0            # Precio máximo $500
    min_volume: int = 500_000           # Volumen mínimo 500K
    min_market_cap: float = 1e9         # Market cap mínimo $1B
    min_change_pct: float = 2.0         # Cambio mínimo ±2%
    max_discovered: int = 10            # Máximo 10 acciones descubiertas
    max_total_watchlist: int = 20       # Máximo 20 total (base + descubiertas)
```

**Flujo de descubrimiento:**
```
┌─────────────────────────────────────────────────────────────┐
│  Cada 30 min durante mercado abierto:                       │
│    1. Escanea top gainers/losers (Alpaca + yfinance)        │
│    2. Busca acciones con volumen inusual                    │
│    3. Aplica filtros (precio, volumen, market cap)          │
│    4. Agrega las más interesantes al watchlist dinámico     │
│    5. Se suscribe a sus quotes en tiempo real               │
│                                                             │
│  Resultado:                                                 │
│    Base watchlist:  AAPL, MSFT, NVDA... (10 fijas)          │
│    + Discovered:    COIN (+15%), PLTR (3x vol)... (hasta 10)│
│    = Watchlist dinámico de hasta 20 acciones                │
└─────────────────────────────────────────────────────────────┘
```

**Exclusiones automáticas:**
- ETFs de contexto: SPY, QQQ, IWM, DIA
- Productos de volatilidad: VXX, UVXY, SVXY
- Acciones ya en el watchlist base

### Cómo Funciona el Agente

```
┌─────────────────────────────────────────────────────────────────┐
│  1. MONITOREO (cada 60 seg)                                     │
│     El agente revisa tu watchlist via Alpaca WebSocket          │
│                           ↓                                     │
│  2. DETECCIÓN                                                   │
│     ¿Hay señal técnica interesante? (RSI, MACD, volumen)        │
│                           ↓                                     │
│     NO → No gasta créditos Claude (gratis)                      │
│     SÍ → Continúa al análisis                                   │
│                           ↓                                     │
│  3. ANÁLISIS CON CLAUDE (~$0.01)                                │
│     - Analiza técnicos + contexto mercado                       │
│     - Consulta memoria de trades pasados                        │
│     - Genera recomendación con confidence %                     │
│                           ↓                                     │
│  4. ALERTA                                                      │
│     ┌──────────────────────────────────────┐                    │
│     │ 🚨 BUY AAPL @ $182.50               │                    │
│     │ Confidence: 78% | R:R 2.5:1         │                    │
│     │ Target: $188 | Stop: $180.30        │                    │
│     │ [C]onfirm  [R]eject  [M]ore Info    │                    │
│     └──────────────────────────────────────┘                    │
│                           ↓                                     │
│  5. TÚ DECIDES                                                  │
│     [C] Confirmar → Ejecuta trade en Alpaca                     │
│     [R] Rechazar → Ignora la señal                              │
│     [M] Más info → Ver análisis completo de Claude              │
└─────────────────────────────────────────────────────────────────┘
```

### Costo Estimado de Claude API

El agente **NO llama a Claude constantemente**. Solo cuando hay señales técnicas interesantes.

| Escenario | Llamadas/día | Costo/día | $5 duran |
|-----------|--------------|-----------|----------|
| Mercado tranquilo | 5-10 | ~$0.05-0.10 | 50-100 días |
| Mercado activo | 20-50 | ~$0.20-0.50 | 10-25 días |
| Muy volátil | 50-100 | ~$0.50-1.00 | 5-10 días |

**Estimación típica**: $5 USD duran **2-4 semanas** de uso normal.

### Dashboard Preview

```
╔══════════════════════════════════════════════════════════════════╗
║              AI TRADING AGENT v1.0 | [RUNNING]                   ║
║              Market: OPEN | VIX: 18.5 (▼)                        ║
╠═══════════════════════════════╦══════════════════════════════════╣
║  📊 Portfolio                 ║  🌍 Market Context               ║
║  Buying Power: $100,000       ║  SPY: +0.45%                     ║
║  Positions: 0                 ║  VIX: 18.5                       ║
║  Unrealized P&L: $0.00        ║  Regime: NEUTRAL                 ║
╠═══════════════════════════════╩══════════════════════════════════╣
║  🔔 Alerts                                                       ║
║  Pending: 0 | Generated: 0 | Trades: 0                           ║
╠══════════════════════════════════════════════════════════════════╣
║  [C]onfirm  [R]eject  [P]ause  [Q]uit                            ║
╚══════════════════════════════════════════════════════════════════╝
```

### Architecture (v2.0)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLI DASHBOARD                                   │
│                    (Real-time monitoring + Manual override)                  │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────────────────┐
│                             TRADING AGENT                                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Momentum   │  │    Stock    │  │   Market    │  │   Reasoning Engine  │ │
│  │  Scanner    │  │  Discovery  │  │   Context   │  │   (Ollama/Claude)   │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         └────────────────┼────────────────┘                    │            │
│                          ▼                                     │            │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                    INTELLIGENCE LAYER                                  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │  ATR Stops   │ │   Periodic   │ │   Layered    │ │  Position    │  │  │
│  │  │  (Dynamic)   │ │  Reflection  │ │   Memory     │ │ Intelligence │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │    Trade     │ │    News      │ │   Analyst    │ │    Risk      │  │  │
│  │  │ Intelligence │ │  Sentiment   │ │   Ratings    │  │   Manager    │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                      │                                       │
│                                      ▼                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                      EXECUTION LAYER                                   │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │  │
│  │  │    Order     │ │   Position   │ │   Partial    │ │    Trade     │  │  │
│  │  │   Executor   │ │   Monitor    │ │   Profits    │ │    Logger    │  │  │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
┌─────────────────────────────────────▼───────────────────────────────────────┐
│                           ALPACA API                                         │
│              (REST + WebSocket - Paper/Live Trading)                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Intelligence Layer Details

#### 🎯 ATR Dynamic Stops (`atr_stops.py`)
Volatility-based stop-loss management that adapts to market conditions.

```
Volatility Regime → ATR Multiplier → Stop Distance
─────────────────────────────────────────────────
LOW (<1% ATR)      → 1.5x ATR      → Tight stops
NORMAL (1-2%)      → 2.0x ATR      → Standard stops
HIGH (2-3.5%)      → 2.5x ATR      → Wider stops
EXTREME (>3.5%)    → 3.0x ATR      → Very wide stops
```

#### 🔄 Periodic Reflection (`periodic_reflection.py`)
Learns from past trades every N executions.

```
Every 10 trades → Analyze Performance → Adjust Strategy
                        │
                        ├── Win Rate Analysis
                        ├── Confidence Calibration
                        ├── Setup Type Performance
                        └── Overconfidence Detection
```

#### 🧠 Layered Memory (`layered_memory.py`)
Three-tier hierarchical memory system (inspired by FinMem research).

```
┌─────────────────────────────────────────────────────────┐
│  WORKING MEMORY (0-4 hours)                             │
│  • Recent prices, news, trades                          │
│  • Weight: 0.5 (highest influence)                      │
├─────────────────────────────────────────────────────────┤
│  SHORT-TERM MEMORY (1-7 days)                           │
│  • Recent patterns, trade performance                   │
│  • Weight: 0.3                                          │
├─────────────────────────────────────────────────────────┤
│  DEEP MEMORY (1-6 months)                               │
│  • Earnings cycles, seasonal patterns                   │
│  • Weight: 0.2                                          │
└─────────────────────────────────────────────────────────┘
```

#### 📐 Position Intelligence (`position_intelligence.py`)
Advanced position sizing combining multiple factors.

```
Base Position (20%)
    │
    ├── × Kelly Criterion (optimal sizing based on win rate)
    ├── × Session Adjustment (time-of-day factor)
    ├── × Drawdown Adjustment (capital preservation)
    ├── × Sector Correlation (avoid concentrated risk)
    └── × Confidence Scaling
    │
    ▼
Final Position Size (0-25% max)
```

**Session Awareness:**
| Session | Time (ET) | Size Mult | Notes |
|---------|-----------|-----------|-------|
| Pre-Market | 4:00-9:30 | 0% | No trading |
| Opening Bell | 9:30-10:00 | 50% | High volatility |
| Morning | 10:00-11:30 | 100% | Best momentum |
| Midday | 11:30-2:00 | 70% | Choppy, avoid entries |
| Afternoon | 2:00-3:30 | 90% | Trend continuation |
| Power Hour | 3:30-4:00 | 60% | Close positions only |

**Drawdown Protection:**
| Drawdown | Action |
|----------|--------|
| <2% | Normal trading |
| 2-3% | 75% size (caution) |
| 3-5% | 50% size (defensive) |
| 5-8% | 25% size (critical) |
| >10% | **HALT TRADING** |

#### ⚔️ Trade Intelligence (`trade_intelligence.py`)
AI-powered trade analysis with debate mechanism.

```
Trade Opportunity
       │
       ├── Self-Reflection (learn from similar past trades)
       │         │
       │         └── "Last 5 similar setups: 3 wins, 2 losses"
       │
       └── Bull/Bear Debate
                 │
                 ├── 🐂 Bull Agent: "Strong momentum, buy!"
                 ├── 🐻 Bear Agent: "Overbought, risky!"
                 └── Consensus: "CAUTIOUS_BUY (60% confidence)"
```

### Project Structure (AI Agent v2.0)
```
agent/
├── core/
│   ├── agent.py              # 🎯 TradingAgent principal (orchestrator)
│   ├── reasoning.py          # 🧠 LLM integration (Ollama/Claude)
│   ├── memory.py             # 📝 Basic trade memory
│   ├── context.py            # 🌍 Market context (VIX, SPY, regime)
│   ├── discovery.py          # 🔍 Dynamic stock discovery
│   ├── summary.py            # 📊 Daily summary generation
│   ├── momentum.py           # 📈 Momentum scanner + setups
│   │
│   │   # === INTELLIGENCE LAYER (NEW) ===
│   ├── atr_stops.py          # 🎯 ATR-based dynamic stop-loss
│   ├── periodic_reflection.py # 🔄 Learn from past N trades
│   ├── layered_memory.py     # 🧠 3-tier memory system
│   ├── position_intelligence.py # 📐 Kelly + Drawdown + Sessions
│   ├── trade_intelligence.py # ⚔️ Bull/Bear debate + reflection
│   ├── news_sentiment.py     # 📰 Alpaca News + LLM analysis
│   ├── analyst_ratings.py    # 📊 Yahoo Finance ratings
│   ├── risk_manager.py       # 🛡️ Independent risk validation
│   └── trade_logger.py       # 📝 Detailed trade logging
│
├── prompts/
│   ├── analysis.py           # Analysis prompts
│   └── decision.py           # Decision prompts
│
└── strategies/
    └── day_trading.py        # Day trading strategy

alpaca/
├── client.py                 # REST API client
├── stream.py                 # WebSocket streaming (real-time quotes)
└── executor.py               # Order execution + position tracking

alerts/
├── manager.py                # Alert queue and dispatch
└── formatters.py             # Rich terminal formatting

cli/
├── main.py                   # Entry point
└── dashboard.py              # Terminal dashboard (Rich)

config/
├── settings.py               # General settings
└── agent_config.py           # Agent configuration (API keys, risk params)

data/
├── collectors/
│   ├── market_data.py        # Market data collection
│   └── news_collector.py     # News collection
└── processors/
    └── sentiment_analyzer.py # Sentiment analysis

logs/
└── trades/                   # Trade decision logs (JSON)
    └── *.json                # Individual trade logs

data/
└── memory/                   # Layered memory storage
    └── *.json                # Memory items by layer
```

### Key Files Reference

| File | Purpose | Key Methods |
|------|---------|-------------|
| `agent.py` | Main orchestrator | `run()`, `_generate_signals()`, `_momentum_setup_to_opportunity()` |
| `atr_stops.py` | Dynamic stops | `calculate_dynamic_levels()`, `get_atr()` |
| `periodic_reflection.py` | Trade learning | `record_trade()`, `run_reflection()`, `apply_adjustments_to_confidence()` |
| `layered_memory.py` | Memory system | `query()`, `add_memory()`, `record_trade()` |
| `position_intelligence.py` | Position sizing | `calculate_position()`, `get_current_session()`, `get_drawdown_multiplier()` |
| `trade_intelligence.py` | AI analysis | `full_analysis()`, `_run_debate()`, `_run_reflection()` |
| `risk_manager.py` | Risk validation | `validate_trade()`, `record_trade_result()` |

See `agent/core/` directory for full implementation.

---

## 🎯 What This System Does

This is a **prompt-based workflow** that uses Claude's capabilities to:
- 📈 Analyze stocks in real-time using web search
- 📰 Monitor news and sentiment for your holdings
- 💡 Provide buy/sell/hold recommendations
- 📊 Track your portfolio performance
- 🎯 Help you make informed trading decisions

**Key Difference**: Instead of running code, you interact with Claude through natural language prompts to get analysis and insights.

## 🚀 Quick Start

### 1. Initial Setup
No installation required! Just:
1. Read `STOCK_ANALYSIS_GUIDE.md` to understand the workflow
2. Update `HOLDINGS.md` with your initial portfolio (starts with $200)
3. Start asking Claude for analysis

### 2. Your Starting Portfolio
- **Initial Capital**: $200
- **Starting Position**: You decide (keep as cash or start with a stock)
- **File to Track**: `HOLDINGS.md`

### 3. No API Keys Needed
Claude can access real-time data through:
- Web search (built-in)
- Financial websites (Yahoo Finance, MarketWatch, etc.)
- News sources (Bloomberg, CNBC, Reuters, etc.)

## 💬 How to Use

### Daily Workflow with Claude

**Morning Analysis** (Before 9:30 AM EST):
```
"Analyze my holdings in HOLDINGS.md and provide pre-market insights.
Check news and technical indicators for each stock."
```

**Real-Time Analysis** (During Market Hours):
```
"Give me real-time analysis for TSLA. Include current price,
news sentiment, and technical indicators."
```

**Trading Decisions**:
```
"Based on current conditions, should I buy, sell, or hold NVDA?
Provide confidence level and reasoning."
```

**End of Day Review**:
```
"Review today's performance for my portfolio. Summarize gains/losses
and provide recommendations for tomorrow."
```

### Portfolio Management

**After Each Trade**:
```
"Update HOLDINGS.md with my BUY of 5 shares of AAPL at $180.00.
Calculate new position size and portfolio allocation."
```

**Weekly Review**:
```
"Review my trading performance this week. Show total return,
best/worst performers, and lessons learned."
```

## 📊 Analysis Types Available

### 📈 Technical Analysis
Claude can analyze:
- Moving averages (50-day, 200-day)
- Momentum indicators (RSI, MACD)
- Volume trends and patterns
- Support/resistance levels
- Chart patterns and breakouts

### 📰 News & Sentiment
Claude monitors:
- Latest news (last 24-48 hours)
- Sentiment analysis (positive/negative/neutral)
- Market-moving catalysts
- Analyst ratings and upgrades
- Sector trends

### 💡 Trading Signals
Claude provides:
- BUY/SELL/HOLD recommendations
- Confidence levels (High/Medium/Low)
- Entry/exit price targets
- Stop-loss suggestions
- Risk/reward analysis

### 📊 Portfolio Analytics
Claude tracks:
- Total return and P&L
- Position sizing and allocation
- Diversification analysis
- Win rate and trade statistics
- Performance vs benchmarks (SPY, QQQ)

## 🎯 How Claude Analyzes Stocks

Claude's analysis framework combines:

### Technical Indicators
- **Trend Analysis**: Moving averages, trend lines
- **Momentum**: RSI, MACD, Stochastic
- **Volume**: Trading activity vs historical average
- **Volatility**: Bollinger Bands, ATR

### Fundamental Data
- **Price Action**: Support/resistance levels
- **Market Cap**: Company size and liquidity
- **Recent Performance**: Short and long-term trends
- **Sector Context**: Industry trends and comparisons

### News & Sentiment
- **Recent Headlines**: Last 24-48 hours
- **Sentiment Scoring**: Positive/negative/neutral
- **Catalyst Identification**: Earnings, product launches, etc.
- **Market Impact**: Potential price movement

### Risk Assessment
- **Volatility**: Price fluctuation patterns
- **Position Sizing**: Portfolio percentage recommendations
- **Stop-Loss Levels**: Risk management points
- **Risk/Reward Ratios**: Expected return vs potential loss

## 📋 Recommendation Signals

### 🟢 Buy Signals
- **STRONG BUY**: High confidence + multiple positive indicators
- **BUY**: Clear buy signal with good risk/reward
- **WEAK BUY**: Positive bias but proceed with caution

### 🔴 Sell Signals
- **STRONG SELL**: High confidence + multiple negative indicators
- **SELL**: Clear sell signal to protect capital
- **WEAK SELL**: Negative bias, consider reducing position

### ⚖️ Position Adjustments
- **ADD**: Increase existing position (averaging up/down)
- **REDUCE**: Partial profit-taking or risk reduction
- **HOLD**: Maintain current position, no action needed

## 📊 Performance Metrics You Can Track

### Returns
- **Total Return**: Performance since inception
- **Period Returns**: Daily, weekly, monthly gains/losses
- **Benchmark Comparison**: Your portfolio vs SPY/QQQ

### Trading Statistics
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Total gains / Total losses ratio
- **Max Drawdown**: Largest peak-to-trough decline
- **Average Win/Loss**: Mean profit and loss per trade

### Risk Metrics
- **Portfolio Volatility**: Price fluctuation measure
- **Risk Level**: Low/Medium/High based on positions
- **Position Sizing**: Percentage allocation per stock
- **Diversification**: Sector and stock concentration

## ⚙️ Configuration & Settings

Edit `HOLDINGS.md` to customize:

### Portfolio Settings
- **Initial Capital**: $200 (default)
- **Starting Position**: Your choice of stocks or cash
- **Risk Management Rules**:
  - Max 15% position size per stock
  - 2% stop-loss on all positions
  - Max 5% daily loss limit

### Watchlist
Default stocks to monitor:
- AAPL (Apple)
- MSFT (Microsoft)
- GOOGL (Alphabet)
- AMZN (Amazon)
- NVDA (NVIDIA)
- META (Meta Platforms)

You can add/remove based on your interests and strategy.

## 📁 Project Structure

### Essential Files (Prompt-Based System)
```
📊 Stock Analysis System/
├── HOLDINGS.md                    # Your portfolio tracker (UPDATE DAILY)
├── STOCK_ANALYSIS_GUIDE.md        # How to use this system
├── README.md                      # This file
└── CODE_REMOVAL_GUIDE.md          # What code can be deleted
```

### Legacy Code (Can Be Removed)
```
⚠️ Not Needed for Prompt-Based Workflow:
├── backend/                       # Python backend
├── frontend/                      # React frontend
├── config/                        # Config files
├── data/                          # Data collectors
├── portfolio/                     # Portfolio management code
├── signals/                       # Signal generation code
├── analytics/                     # Analytics code
├── dashboard/                     # Web dashboard
├── main/                          # Scheduler
├── main.py                        # Entry point
├── requirements.txt               # Python dependencies
└── test_system.py                 # System tests
```

**See CODE_REMOVAL_GUIDE.md for details on what can be safely deleted.**

## 🕐 Recommended Analysis Schedule

### Pre-Market (8:30-9:30 AM EST)
Ask Claude:
- "Check overnight news for my holdings"
- "Analyze pre-market movers and sentiment"
- "What should I watch at market open?"

### Market Open (9:30-10:00 AM EST)
Ask Claude:
- "How are markets opening? Any significant moves?"
- "Review my watchlist for entry opportunities"

### Mid-Day Check (12:00-1:00 PM EST)
Ask Claude:
- "Mid-day update on my positions"
- "Any new developments or news?"

### Market Close (3:30-4:00 PM EST)
Ask Claude:
- "Should I hold positions overnight or close?"
- "Any after-hours catalysts to watch?"

### After-Hours (5:00-6:00 PM EST)
Ask Claude:
- "Summarize today's performance"
- "Prepare watchlist for tomorrow"
- "Update HOLDINGS.md with today's activity"

## 🎯 Trading Strategies You Can Use

### 1. News-Driven Momentum
Ask Claude to:
- Monitor breaking news for your watchlist
- Analyze sentiment and potential impact
- Recommend entry/exit on news catalysts
Target: 2-4% quick gains on positive news

### 2. Technical Breakout
Ask Claude to:
- Identify stocks breaking resistance levels
- Confirm with volume analysis
- Provide entry points on breakouts
Target: 5-10% gains on strong momentum

### 3. Mean Reversion
Ask Claude to:
- Find oversold quality stocks
- Analyze bounce potential
- Set tight stop-losses
Target: 1-3% quick scalps on bounces

## 📈 Example Daily Workflow

### 1. Morning Routine (9:00 AM)
Ask Claude:
```
"Analyze my holdings in HOLDINGS.md. Check overnight news,
pre-market prices, and provide today's game plan."
```

### 2. Market Open (9:30 AM)
Ask Claude:
```
"Review my watchlist. Any strong buy signals at market open?
Check AAPL, NVDA, and TSLA for entry opportunities."
```

### 3. Mid-Day Monitoring (12:00 PM)
Ask Claude:
```
"How are my positions performing? Any news or technical changes
that warrant action?"
```

### 4. Pre-Close Decision (3:30 PM)
Ask Claude:
```
"Should I hold my TSLA position overnight or take profits?
Check after-hours catalysts."
```

### 5. Evening Review (5:00 PM)
Ask Claude:
```
"Summarize today's trades. Update HOLDINGS.md with:
- Bought 10 AAPL @ $180.00
- Sold 5 NVDA @ $520.00
Calculate new portfolio value and P&L."
```

## 🎓 Learning & Improvement

### Ask Claude to Explain
- Technical indicators (RSI, MACD, etc.)
- Trading concepts (support/resistance, volume, etc.)
- Market mechanics (bid/ask, orders, etc.)
- Fundamental analysis (P/E ratios, earnings, etc.)

### Weekly Review with Claude
```
"Review my trading performance this week. Show:
- Total return vs SPY benchmark
- Win rate and best/worst trades
- Lessons learned and strategy adjustments needed"
```

### Monthly Deep Dive
```
"Comprehensive monthly analysis:
- Portfolio returns and risk metrics
- Strategy effectiveness review
- Sector allocation analysis
- Recommendations for next month"
```

## ⚠️ Important Disclaimers

- **Educational Purpose Only**: This system is for learning and practice
- **Not Financial Advice**: Claude provides analysis, not investment advice
- **DYOR**: Always do your own research before trading
- **Risk Management**: Never risk more than you can afford to lose
- **Paper Trading**: Consider practicing with paper trading first
- **Market Risks**: Past performance doesn't guarantee future results

## 🚀 Getting Started Right Now

1. **Read** `STOCK_ANALYSIS_GUIDE.md` for detailed instructions
2. **Update** `HOLDINGS.md` with your starting position
3. **Ask Claude**: "Analyze the current market. What stocks show promise today?"
4. **Start Small**: Begin with 1-2 positions to learn the system
5. **Track Everything**: Update HOLDINGS.md after every decision

## 📞 How to Get Help

**If you need analysis**:
- Be specific in your prompts
- Provide context (holdings, goals, timeframe)
- Ask follow-up questions
- Request different scenarios

**Common prompts**:
- "Explain [concept] in simple terms"
- "Should I buy/sell [ticker]? Why?"
- "Analyze [ticker] technical indicators"
- "Update my portfolio with [trade details]"

## 📚 Resources

Claude can access:
- Real-time market data
- Financial news (Bloomberg, Reuters, CNBC)
- Stock data (Yahoo Finance, MarketWatch)
- Technical analysis tools
- Fundamental data

## 🎯 Success Tips

✅ **DO**:
- Update HOLDINGS.md daily
- Ask Claude to verify from multiple sources
- Request confidence levels with recommendations
- Practice risk management (stop-losses, position sizing)
- Learn from both wins and losses

❌ **DON'T**:
- Make emotional decisions
- Ignore risk management rules
- Trade with money you can't afford to lose
- Follow recommendations blindly without understanding
- Forget to track your trades

---

**🚀 Ready to start? Ask Claude: "Help me analyze my first stock opportunity!"**

**📊 Happy Trading! Remember: Consistent, disciplined trading beats risky speculation.**
# 🚀 Trading Simulator

Un sistema completo de simulación de trading con análisis en tiempo real, inteligencia artificial y recomendaciones automáticas.

## 📋 Características

- 🎯 **Portfolio Simulado**: Comienza con $200 en acciones de Tesla
- 📊 **Datos en Tiempo Real**: APIs gratuitas (Yahoo Finance, Alpha Vantage, NewsAPI)
- 🤖 **Señales Automáticas**: Análisis técnico + sentiment de noticias
- 📰 **Análisis de Noticias**: Procesamiento de sentiment con IA
- 💡 **Recomendaciones Diarias**: Sugerencias de compra/venta
- 📈 **Dashboard Web**: Monitoreo en tiempo real
- 📊 **Tracking de Performance**: Métricas detalladas
- ⏰ **Ejecución Continua**: Actualiza automáticamente

## 🛠 Instalación

### 1. Requisitos
```bash
Python 3.8+
pip install -r requirements.txt
```

### 2. Setup Inicial
```bash
python main.py --setup
```

### 3. API Keys (Gratis)
Edita el archivo `.env` con tus API keys:

```bash
# Alpha Vantage (500 requests/día gratis)
ALPHA_VANTAGE_API_KEY=tu_key_aqui

# NewsAPI (1000 requests/día gratis)
NEWS_API_KEY=tu_key_aqui
```

**Obtener API Keys:**
- [Alpha Vantage](https://www.alphavantage.co/support/#api-key) - Datos de mercado
- [NewsAPI](https://newsapi.org/register) - Noticias financieras

## 🚀 Uso

### Dashboard Web (Recomendado)
```bash
python main.py --dashboard
```
Abre tu navegador en: `http://127.0.0.1:8050`

### Sistema Completo Automático
```bash
python main.py --scheduler
```
Ejecuta todo el sistema: recolección de datos, análisis, señales y dashboard.

### Comandos Rápidos

```bash
# Ver portfolio actual
python main.py --portfolio

# Ver recomendaciones del día
python main.py --recommendations

# Ver señales de trading
python main.py --signals

# Actualización manual
python main.py --update
```

## 📊 Dashboard Features

### 📈 Portfolio Overview
- Valor total del portfolio
- P&L diario y total
- Cash disponible
- Breakdown de posiciones

### 🎯 Trading Signals
- Señales de compra/venta automáticas
- Niveles de confianza
- Precios objetivo y stop loss
- Reasoning detallado

### 📰 News Sentiment
- Noticias recientes por stock
- Análisis de sentiment
- Impacto potencial en precios

### 📋 Trade History
- Historial completo de trades
- Performance por operación
- Comisiones y costos

## 🎯 Sistema de Recomendaciones

El sistema genera recomendaciones automáticas basadas en:

### Análisis Técnico (40%)
- RSI, MACD, Bollinger Bands
- Medias móviles
- Patrones de precio
- Análisis de volumen

### Sentiment de Noticias (35%)
- Análisis de noticias con IA
- Keywords financieras
- Impacto en el mercado
- Confianza del análisis

### Análisis de Volumen (15%)
- Volumen vs promedio
- Price-volume relationship
- Unusual activity

### Social Sentiment (10%)
- Sentiment en redes sociales
- Tendencias en trading communities

## 📋 Tipos de Recomendaciones

### 🟢 Señales de Compra
- **STRONG_BUY**: Alta confianza + múltiples indicadores positivos
- **BUY**: Señal clara de compra
- **WEAK_BUY**: Señal débil pero positiva

### 🔴 Señales de Venta
- **STRONG_SELL**: Alta confianza + múltiples indicadores negativos
- **SELL**: Señal clara de venta
- **WEAK_SELL**: Señal débil pero negativa

### ⚖️ Ajustes de Posición
- **ADD**: Añadir a posición existente
- **REDUCE**: Reducir posición parcialmente
- **HOLD**: Mantener posición actual

## 📊 Métricas de Performance

### Rendimiento
- **Total Return**: Rendimiento desde inicio
- **Annualized Return**: Rendimiento anualizado
- **Sharpe Ratio**: Retorno ajustado por riesgo

### Trading
- **Win Rate**: % de trades ganadores
- **Profit Factor**: Ganancias / Pérdidas
- **Max Drawdown**: Máxima pérdida desde peak
- **Average Win/Loss**: Promedio de ganancias/pérdidas

### Evaluación
- **Performance Grade**: A-F basado en métricas
- **Risk Level**: Low/Medium/High
- **Volatility**: Volatilidad del portfolio

## ⚙️ Configuración

Edita `config/settings.py` para personalizar:

```python
# Portfolio inicial
INITIAL_CAPITAL = 200.0
INITIAL_STOCK = 'TSLA'

# Risk Management
MAX_POSITION_SIZE = 0.15  # 15% máximo por trade
MAX_DAILY_LOSS = 0.05     # 5% pérdida máxima diaria
STOP_LOSS_PERCENT = 0.02  # 2% stop loss

# Watchlist de acciones
WATCHLIST = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META']
```

## 📁 Estructura del Proyecto

```
trading_simulator/
├── config/                 # Configuración
├── data/
│   ├── collectors/         # Recolectores de datos
│   └── processors/         # Procesadores (sentiment, etc)
├── portfolio/              # Gestión de portfolio
├── signals/                # Generación de señales
├── analytics/              # Análisis y recomendaciones
├── dashboard/              # Dashboard web
├── main/                   # Scheduler y orquestación
└── logs/                   # Logs del sistema
```

## 🔄 Horarios de Ejecución

### Pre-Market (8:30 AM EST)
- Recolección de noticias overnight
- Análisis de pre-market movers
- Generación de señales iniciales

### Market Hours (9:30 AM - 4:00 PM EST)
- Actualización de datos cada 5 minutos
- Monitoreo de stop loss/take profit
- Generación de señales continua

### After-Hours (5:30 PM EST)
- Análisis final del día
- Reporte de performance
- Preparación para día siguiente

## 🎯 Estrategias Implementadas

### 1. News-Driven Momentum
- Compra en noticias positivas
- Hold 2-4 horas máximo
- Target: 2-4% ganancia rápida

### 2. Technical Breakout
- Breakouts con alto volumen
- Confirmación en múltiples timeframes
- Hold overnight si momentum fuerte

### 3. Mean Reversion
- Oversold bounces en stocks de calidad
- Quick scalps 1-2%
- Stops estrictos

## 📈 Ejemplo de Uso Diario

1. **Morning Routine**:
   ```bash
   python main.py --recommendations
   ```
   - Revisa las recomendaciones de alta prioridad
   - Evalúa las razones y confianza

2. **Manual Trading**:
   - Ejecuta trades manualmente en Interactive Brokers
   - Basándote en las recomendaciones del sistema

3. **Monitoring**:
   ```bash
   python main.py --dashboard
   ```
   - Monitorea performance en tiempo real
   - Observa nuevas señales durante el día

4. **Evening Review**:
   ```bash
   python main.py --portfolio
   ```
   - Revisa performance del día
   - Planifica estrategia para mañana

## ⚠️ Disclaimer

- **Solo para fines educativos y de simulación**
- **No es consejo financiero**
- **Resultados pasados no garantizan resultados futuros**
- **Siempre haz tu propia investigación antes de invertir**

## 🤝 Soporte

Para problemas o preguntas:
1. Revisa los logs en `logs/trading_simulator.log`
2. Verifica que tengas las API keys configuradas
3. Asegúrate de tener conexión a internet para datos de mercado

## 📊 Próximas Features

- [ ] Integración con más brokers
- [ ] Machine Learning para predicciones
- [ ] Backtesting histórico avanzado
- [ ] Alertas por Telegram/Discord
- [ ] Portfolio optimization automático
- [ ] Options trading simulation

---

**Happy Trading! 📈💰**
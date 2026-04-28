"""
Aggressive Agent Backtest WITH AI Analysis (Groq Llama 3.3 70B)

Compares:
1. RULE-BASED: Original strategy (rules only)
2. AI-FILTERED: Rules + AI must confirm with 70%+ confidence

Tests if AI can filter out bad trades and improve performance.
"""

import asyncio
import logging
import json
import os
import httpx
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np
import yfinance as yf
import pandas as pd
import time

logging.basicConfig(level=logging.WARNING)

# Groq API config
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    trailing_stop_pct: float
    high_since_entry: float


@dataclass
class Trade:
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    pnl_pct: float
    exit_reason: str
    ai_confidence: float = 0.0
    ai_reasoning: str = ""


@dataclass
class AIAnalysis:
    action: str
    confidence: float
    risk_level: str
    reasoning: str


async def get_ai_analysis(
    symbol: str,
    current_price: float,
    prev_day_change: float,
    day_range: float,
    rsi: float,
    market_trend: str,
) -> AIAnalysis:
    """Get AI analysis from Groq"""

    prompt = f"""You are an aggressive day trading analyst. Analyze this setup.

SYMBOL: {symbol}
PRICE: ${current_price:.2f}
PREV DAY: {prev_day_change:+.1%} ({"RED" if prev_day_change < 0 else "GREEN"})
TODAY RANGE: {day_range:.1%}
RSI(14): {rsi:.1f}
MARKET: {market_trend}

STRATEGY: Buy dips after red days with high volatility and low RSI.
Exits: 2% stop, 2% trailing, 10% take profit.

Should we BUY this dip? Respond ONLY with JSON:
{{"action": "BUY" or "HOLD", "confidence": 0.0-1.0, "risk_level": "LOW/MEDIUM/HIGH", "reasoning": "brief"}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 150,
                }
            )

            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    data = json.loads(content[start:end])
                    return AIAnalysis(
                        action=data.get("action", "HOLD").upper(),
                        confidence=float(data.get("confidence", 0.5)),
                        risk_level=data.get("risk_level", "MEDIUM"),
                        reasoning=data.get("reasoning", ""),
                    )
            elif response.status_code == 429:
                # Rate limited - wait and retry
                await asyncio.sleep(2)
                return AIAnalysis("HOLD", 0.5, "MEDIUM", "Rate limited")

    except Exception as e:
        pass

    return AIAnalysis("HOLD", 0.5, "MEDIUM", "Error")


class AIBacktest:
    """Backtest with AI analysis filtering"""

    def __init__(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        use_ai: bool = False,
        ai_min_confidence: float = 0.7,
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date
        self.use_ai = use_ai
        self.ai_min_confidence = ai_min_confidence

        # Strategy config
        self.max_positions = 2
        self.position_size_pct = 0.50
        self.stop_loss_pct = 0.02
        self.take_profit_pct = 0.10
        self.trailing_stop_pct = 0.02
        self.min_prev_day_drop = -0.01
        self.min_day_range = 0.02
        self.max_rsi = 45.0

        # State
        self.initial_capital = 100_000.0
        self.cash = self.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.ai_calls = 0
        self.ai_rejections = 0

        # Data
        self.hourly_data: Dict[str, pd.DataFrame] = {}
        self.daily_data: Dict[str, pd.DataFrame] = {}

    def load_data(self):
        """Load data from yfinance"""
        for symbol in self.symbols:
            try:
                ticker = yf.Ticker(symbol)

                df_hourly = ticker.history(
                    start=self.start_date - timedelta(days=30),
                    end=self.end_date + timedelta(days=1),
                    interval='1h',
                )
                if not df_hourly.empty:
                    df_hourly.index = df_hourly.index.tz_convert('America/New_York')
                    self.hourly_data[symbol] = df_hourly

                df_daily = ticker.history(
                    start=self.start_date - timedelta(days=60),
                    end=self.end_date + timedelta(days=1),
                    interval='1d',
                )
                if not df_daily.empty:
                    df_daily.index = df_daily.index.tz_convert('America/New_York')
                    self.daily_data[symbol] = df_daily

            except Exception as e:
                print(f"Error loading {symbol}: {e}")

    def calculate_rsi(self, closes: pd.Series, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = closes.diff()
        gains = deltas.where(deltas > 0, 0)
        losses = (-deltas).where(deltas < 0, 0)
        avg_gain = gains.rolling(window=period).mean().iloc[-1]
        avg_loss = losses.rolling(window=period).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def was_prev_day_red(self, symbol: str, current_time) -> Tuple[bool, float]:
        if symbol not in self.daily_data:
            return False, 0
        df = self.daily_data[symbol]
        current_date = current_time.date()
        prev_bars = df[df.index.date < current_date]
        if len(prev_bars) < 2:
            return False, 0
        prev_day = prev_bars.iloc[-1]
        prev_return = (prev_day['Close'] - prev_day['Open']) / prev_day['Open']
        return prev_return < self.min_prev_day_drop, prev_return

    def get_day_range(self, symbol: str, current_time) -> float:
        if symbol not in self.hourly_data:
            return 0
        df = self.hourly_data[symbol]
        current_date = current_time.date()
        today_bars = df[df.index.date == current_date]
        if today_bars.empty:
            return 0
        high = today_bars['High'].max()
        low = today_bars['Low'].min()
        close = today_bars['Close'].iloc[-1]
        return (high - low) / close if close > 0 else 0

    async def run(self) -> Dict:
        """Run backtest"""
        self.load_data()

        if not self.hourly_data:
            return {'total_return': 0, 'trades': 0}

        all_hours = set()
        for df in self.hourly_data.values():
            start_tz = pd.Timestamp(self.start_date).tz_localize('America/New_York')
            end_tz = pd.Timestamp(self.end_date).tz_localize('America/New_York')
            mask = (df.index >= start_tz) & (df.index <= end_tz)
            all_hours.update(df[mask].index.tolist())

        all_hours = sorted(list(all_hours))

        for current_time in all_hours:
            if current_time.hour < 9 or current_time.hour >= 16:
                continue

            self._check_exits(current_time)

            # Entry only at close (15:00-16:00)
            if 15 <= current_time.hour < 16:
                await self._check_entries(current_time)

        # Close remaining
        if self.positions and all_hours:
            for symbol in list(self.positions.keys()):
                self._close_position(symbol, all_hours[-1], "backtest_end")

        return self._generate_results()

    def _check_exits(self, current_time: datetime):
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            if symbol not in self.hourly_data:
                continue
            df = self.hourly_data[symbol]
            if current_time not in df.index:
                continue

            bar = df.loc[current_time]
            high = bar['High']
            low = bar['Low']

            if high > pos.high_since_entry:
                pos.high_since_entry = high

            if low <= pos.stop_loss:
                self._close_position(symbol, current_time, "stop_loss", pos.stop_loss)
                continue

            if pos.high_since_entry > pos.entry_price:
                trailing_stop = pos.high_since_entry * (1 - pos.trailing_stop_pct)
                if low <= trailing_stop:
                    self._close_position(symbol, current_time, "trailing_stop", trailing_stop)
                    continue

            if high >= pos.take_profit:
                self._close_position(symbol, current_time, "take_profit", pos.take_profit)

    async def _check_entries(self, current_time: datetime):
        if len(self.positions) >= self.max_positions:
            return

        for symbol in self.symbols:
            if symbol in self.positions:
                continue
            if len(self.positions) >= self.max_positions:
                break
            if symbol not in self.hourly_data:
                continue

            df = self.hourly_data[symbol]
            if current_time not in df.index:
                continue

            # Rule-based checks
            was_red, prev_return = self.was_prev_day_red(symbol, current_time)
            if not was_red:
                continue

            day_range = self.get_day_range(symbol, current_time)
            if day_range < self.min_day_range:
                continue

            closes = df[df.index <= current_time]['Close'].tail(20)
            rsi = self.calculate_rsi(closes)
            if rsi > self.max_rsi:
                continue

            entry_price = df.loc[current_time, 'Close']
            ai_confidence = 1.0
            ai_reasoning = "Rule-based"

            # AI filter (if enabled)
            if self.use_ai:
                self.ai_calls += 1
                print(f"  🤖 AI call #{self.ai_calls}: {symbol} @ ${entry_price:.2f}...", end=" ", flush=True)
                analysis = await get_ai_analysis(
                    symbol=symbol,
                    current_price=entry_price,
                    prev_day_change=prev_return,
                    day_range=day_range,
                    rsi=rsi,
                    market_trend="NEUTRAL",
                )
                result = "✅ BUY" if (analysis.action == "BUY" and analysis.confidence >= self.ai_min_confidence) else "❌ SKIP"
                print(f"{result} ({analysis.confidence:.0%})")
                ai_confidence = analysis.confidence
                ai_reasoning = analysis.reasoning

                # Reject if AI not confident
                if analysis.action != "BUY" or analysis.confidence < self.ai_min_confidence:
                    self.ai_rejections += 1
                    # Rate limit protection even for rejections
                    await asyncio.sleep(2.5)
                    continue

                # Rate limit protection (30 RPM = 2s min between calls, using 2.5s for safety)
                await asyncio.sleep(2.5)

            # Open position
            self._open_position(symbol, current_time, entry_price, ai_confidence, ai_reasoning)

    def _open_position(self, symbol: str, entry_time: datetime, price: float,
                       ai_confidence: float = 1.0, ai_reasoning: str = ""):
        position_value = self.cash * self.position_size_pct
        if position_value < 100:
            return

        qty = position_value / price
        self.positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            entry_price=price,
            entry_time=entry_time,
            stop_loss=price * (1 - self.stop_loss_pct),
            take_profit=price * (1 + self.take_profit_pct),
            trailing_stop_pct=self.trailing_stop_pct,
            high_since_entry=price,
        )
        self.cash -= position_value

    def _close_position(self, symbol: str, exit_time: datetime, reason: str, price: float = None):
        pos = self.positions.get(symbol)
        if not pos:
            return

        if price is None:
            if symbol in self.hourly_data and exit_time in self.hourly_data[symbol].index:
                price = self.hourly_data[symbol].loc[exit_time, 'Close']
            else:
                price = pos.entry_price

        pnl_pct = (price - pos.entry_price) / pos.entry_price

        self.trades.append(Trade(
            symbol=symbol,
            entry_time=pos.entry_time,
            exit_time=exit_time,
            entry_price=pos.entry_price,
            exit_price=price,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        ))

        self.cash += pos.qty * price
        del self.positions[symbol]

    def _generate_results(self) -> Dict:
        final_equity = self.cash
        total_return = (final_equity - self.initial_capital) / self.initial_capital * 100

        winning = [t for t in self.trades if t.pnl_pct > 0]
        losing = [t for t in self.trades if t.pnl_pct <= 0]
        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0
        avg_win = np.mean([t.pnl_pct for t in winning]) * 100 if winning else 0
        avg_loss = np.mean([t.pnl_pct for t in losing]) * 100 if losing else 0

        return {
            'total_return': total_return,
            'trades': len(self.trades),
            'win_rate': win_rate,
            'winning': len(winning),
            'losing': len(losing),
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'ai_calls': self.ai_calls,
            'ai_rejections': self.ai_rejections,
        }


async def run_comparison(period_set: str = "q4_2025"):
    """Compare rule-based vs AI-filtered"""
    SYMBOLS = ['SOXL', 'SMCI', 'MARA', 'COIN', 'MU', 'AMD', 'NVDA', 'TSLA']

    # Define period sets
    if period_set == "q4_2025":
        periods = [
            (datetime(2025, 10, 1), datetime(2025, 10, 31), "Oct 2025"),
            (datetime(2025, 11, 1), datetime(2025, 11, 30), "Nov 2025"),
            (datetime(2025, 12, 1), datetime(2025, 12, 31), "Dec 2025"),
        ]
        period_label = "Q4 2025 (October - December)"
    elif period_set == "jan_feb_2026":
        periods = [
            (datetime(2026, 1, 1), datetime(2026, 1, 31), "Jan 2026"),
            (datetime(2026, 2, 1), datetime(2026, 2, 25), "Feb 2026"),
        ]
        period_label = "January - February 2026"
    else:
        raise ValueError(f"Unknown period set: {period_set}")

    print("=" * 80)
    print("BACKTEST COMPARISON: RULE-BASED vs AI-FILTERED")
    print("=" * 80)
    print(f"Period: {period_label}")
    print(f"Symbols: {SYMBOLS}")
    print(f"AI: Groq Llama 3.3 70B | Min confidence: 70%")
    print(f"Rate limit delay: 2.5s between AI calls (safe for 30 RPM)")
    print("=" * 80)

    print(f"\n{'Mode':<15} | {'Period':<10} | {'Return':>9} | {'Trades':>7} | {'Win%':>6} | {'AI Calls':>9} | {'Rejected':>9}")
    print("-" * 80)

    total_rules = 0
    total_ai = 0
    total_ai_calls = 0
    total_rejections = 0

    for start, end, label in periods:
        # Rule-based
        print(f"Loading {label}...")
        bt_rules = AIBacktest(SYMBOLS, start, end, use_ai=False)
        res_rules = await bt_rules.run()

        # AI-filtered
        print(f"Running AI analysis for {label}...")
        bt_ai = AIBacktest(SYMBOLS, start, end, use_ai=True, ai_min_confidence=0.7)
        res_ai = await bt_ai.run()

        total_rules += res_rules['total_return']
        total_ai += res_ai['total_return']
        total_ai_calls += res_ai['ai_calls']
        total_rejections += res_ai['ai_rejections']

        print(f"{'RULES':<15} | {label:<10} | {res_rules['total_return']:>+8.1f}% | {res_rules['trades']:>7} | {res_rules['win_rate']:>5.1f}% | {'-':>9} | {'-':>9}")
        print(f"{'AI-FILTERED':<15} | {label:<10} | {res_ai['total_return']:>+8.1f}% | {res_ai['trades']:>7} | {res_ai['win_rate']:>5.1f}% | {res_ai['ai_calls']:>9} | {res_ai['ai_rejections']:>9}")
        print("-" * 80)

    print(f"\n{'='*80}")
    print("TOTALS")
    print(f"{'='*80}")
    print(f"RULE-BASED:  {total_rules:>+.1f}%")
    print(f"AI-FILTERED: {total_ai:>+.1f}%")
    print(f"DIFFERENCE:  {total_ai - total_rules:>+.1f}%")
    print(f"\nAI calls: {total_ai_calls} | Rejections: {total_rejections} ({total_rejections/total_ai_calls*100:.0f}% filtered)")

    if total_ai > total_rules:
        print(f"\n✅ AI FILTERING IMPROVED returns by {total_ai - total_rules:+.1f}%")
    else:
        print(f"\n❌ AI FILTERING REDUCED returns by {total_ai - total_rules:+.1f}%")


if __name__ == "__main__":
    import sys
    period = sys.argv[1] if len(sys.argv) > 1 else "q4_2025"
    asyncio.run(run_comparison(period))

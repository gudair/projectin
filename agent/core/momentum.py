"""
Momentum Scanner - High-Probability Setup Detection

Identifies stocks with strong momentum for 2%+ daily gains.
Focuses on:
- Pre-market gaps with continuation potential
- VWAP breakouts and reclaims
- Volume spike detection
- Intraday breakouts
"""
import logging
import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import statistics


class SetupType(Enum):
    """Types of momentum setups"""
    GAP_UP = "gap_up"           # Pre-market gap up >3%
    GAP_DOWN = "gap_down"       # Pre-market gap down (short candidate)
    VWAP_RECLAIM = "vwap_reclaim"  # Price crosses above VWAP
    VOLUME_SPIKE = "volume_spike"   # 3x+ volume surge
    RANGE_BREAKOUT = "range_breakout"  # Breaking day's high
    MOMENTUM_CONTINUATION = "momentum_continuation"  # Already moving, continuing


@dataclass
class MomentumSetup:
    """A detected momentum setup"""
    symbol: str
    setup_type: SetupType
    score: float  # 0-10, higher = better
    current_price: float
    entry_price: float  # Suggested entry
    stop_loss: float    # Suggested stop (2% default)
    target_1: float     # First target (+1.5%)
    target_2: float     # Second target (+2.5%)
    target_3: float     # Third target (+4%)

    # Supporting data
    change_pct: float
    volume_ratio: float  # Current vs average
    vwap: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    premarket_high: Optional[float] = None

    reasoning: str = ""
    detected_at: datetime = field(default_factory=datetime.now)

    @property
    def risk_reward(self) -> float:
        """Calculate risk/reward ratio to first target"""
        risk = self.entry_price - self.stop_loss
        reward = self.target_1 - self.entry_price
        return reward / risk if risk > 0 else 0

    @property
    def potential_gain_pct(self) -> float:
        """Potential gain to first target"""
        return ((self.target_1 / self.entry_price) - 1) * 100


@dataclass
class MomentumConfig:
    """Configuration for momentum scanning"""
    # Scan frequency
    scan_interval_seconds: int = 60  # Scan every minute during market hours

    # Momentum thresholds
    min_gap_pct: float = 3.0        # Minimum gap % to consider
    min_change_pct: float = 2.0     # Minimum intraday change
    min_volume_ratio: float = 2.0   # Minimum volume vs average

    # Entry filters
    max_spread_pct: float = 0.5     # Maximum bid-ask spread
    max_already_moved_pct: float = 8.0  # Don't chase if already up >8%

    # Score thresholds (MODERADO strategy)
    # - Agent prefers score >= 6 (high quality)
    # - Falls back to score >= 4 (decent) if no premium setups
    min_score_to_trade: float = 4.0  # Minimum score to consider for fallback

    # Position sizing (sync with RiskConfig!)
    stop_loss_pct: float = 0.015    # 1.5% stop loss (tighter to reduce avg loss)
    target_1_pct: float = 0.012     # +1.2% first target (take profit earlier)
    target_2_pct: float = 0.02      # +2% second target
    target_3_pct: float = 0.035     # +3.5% third target

    # Trailing stop (after target 1)
    trailing_stop_pct: float = 0.01  # 1% trailing after first target hit

    # Partial profit taking
    partial_profit_1_pct: float = 0.35  # Sell 35% at target 1 (lock more gains)
    partial_profit_2_pct: float = 0.35  # Sell 35% at target 2
    # Remaining 30% uses trailing stop


class MomentumScanner:
    """
    Scans for high-momentum setups with strong profit potential.

    Scoring factors:
    - Volume ratio (higher = better confirmation)
    - Price action (clean breakout vs choppy)
    - Gap magnitude (3-6% sweet spot)
    - Time of day (morning momentum > afternoon)
    - Sector strength (leader in hot sector)
    """

    def __init__(self, config: Optional[MomentumConfig] = None, alpaca_client=None):
        self.config = config or MomentumConfig()
        self.alpaca = alpaca_client
        self.logger = logging.getLogger(__name__)

        # Cache for intraday data
        self._price_history: Dict[str, List[Tuple[datetime, float, int]]] = {}
        self._vwap_cache: Dict[str, float] = {}
        self._last_scan: Optional[datetime] = None
        self._active_setups: Dict[str, MomentumSetup] = {}

    async def scan(self, symbols: List[str], force: bool = False) -> List[MomentumSetup]:
        """
        Scan symbols for momentum setups.

        Returns list of setups sorted by score (best first).
        """
        now = datetime.now()

        # Rate limit scans
        if not force and self._last_scan:
            elapsed = (now - self._last_scan).total_seconds()
            if elapsed < self.config.scan_interval_seconds:
                return list(self._active_setups.values())

        # Get DYNAMIC movers from Alpaca screener (real-time top gainers/losers)
        dynamic_movers = await self._get_market_movers()

        # Combine: input symbols (from watchlist + discovery) + dynamic movers
        # No hardcoded fallback - rely entirely on dynamic discovery
        all_symbols = set(symbols)
        all_symbols.update(dynamic_movers)
        all_symbols = list(all_symbols)

        self.logger.info(f"🔍 Scanning {len(all_symbols)} symbols ({len(dynamic_movers)} from market movers)")
        setups = []

        # Check market hours
        market_phase = self._get_market_phase()

        # Scan in batches to avoid rate limits
        batch_size = 10
        for i in range(0, len(all_symbols), batch_size):
            batch = all_symbols[i:i + batch_size]
            batch_setups = await self._scan_batch(batch, market_phase)
            setups.extend(batch_setups)

            # Small delay between batches
            if i + batch_size < len(all_symbols):
                await asyncio.sleep(0.3)  # Faster scanning

        # Sort by score
        setups.sort(key=lambda s: s.score, reverse=True)

        # Update cache
        self._active_setups = {s.symbol: s for s in setups if s.score >= self.config.min_score_to_trade}
        self._last_scan = now

        # Log top setups
        if setups:
            self.logger.info(f"📊 Found {len(setups)} momentum setups:")
            for setup in setups[:5]:
                self.logger.info(
                    f"  {setup.symbol}: {setup.setup_type.value} | "
                    f"Score: {setup.score:.1f} | "
                    f"Change: {setup.change_pct:+.1f}% | "
                    f"Vol: {setup.volume_ratio:.1f}x"
                )
        else:
            self.logger.info("📭 No momentum setups found")

        return setups

    async def _get_market_movers(self) -> List[str]:
        """
        Get real-time market movers from Alpaca screener API.
        Returns top gainers and losers (stocks with momentum).
        """
        movers = []

        if not self.alpaca:
            return movers

        try:
            import aiohttp

            # Alpaca screener endpoint for market movers
            url = "https://data.alpaca.markets/v1beta1/screener/stocks/movers"
            headers = {
                'APCA-API-KEY-ID': self.alpaca._api_key,
                'APCA-API-SECRET-KEY': self.alpaca._secret_key,
            }
            params = {'top': 20}  # Get top 20 gainers and losers

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        # Get gainers (these have momentum UP)
                        gainers = data.get('gainers', [])
                        for g in gainers:
                            symbol = g.get('symbol', '')
                            change = g.get('percent_change', 0)
                            # Only include if moving significantly
                            if symbol and abs(change) >= 2:
                                movers.append(symbol)

                        # Get losers (potential bounce plays or shorts)
                        losers = data.get('losers', [])
                        for l in losers:
                            symbol = l.get('symbol', '')
                            change = l.get('percent_change', 0)
                            if symbol and abs(change) >= 2:
                                movers.append(symbol)

                        self.logger.info(f"📡 Alpaca movers: {len(movers)} stocks moving >2%")

                    else:
                        self.logger.debug(f"Alpaca screener returned {resp.status}")

        except Exception as e:
            self.logger.debug(f"Could not fetch market movers: {e}")

        return movers

    async def _scan_batch(self, symbols: List[str], market_phase: str) -> List[MomentumSetup]:
        """Scan a batch of symbols"""
        setups = []

        for symbol in symbols:
            try:
                setup = await self._analyze_symbol(symbol, market_phase)
                if setup and setup.score >= self.config.min_score_to_trade:
                    setups.append(setup)
            except Exception as e:
                self.logger.debug(f"Error analyzing {symbol}: {e}")

        return setups

    async def _analyze_symbol(self, symbol: str, market_phase: str) -> Optional[MomentumSetup]:
        """
        Analyze a single symbol for momentum setup.

        Returns MomentumSetup if criteria met, None otherwise.
        """
        if not self.alpaca:
            return None

        try:
            # Get current quote
            quote = await self.alpaca.get_quote(symbol)
            if not quote:
                return None

            current_price = (quote.get('bid', 0) + quote.get('ask', 0)) / 2
            if current_price <= 0:
                current_price = quote.get('last', 0)
            if current_price <= 0:
                return None

            # Get today's bars for VWAP and intraday data
            bars = await self.alpaca.get_bars(symbol, '5Min', limit=78)  # Full day of 5-min bars
            if not bars or len(bars) < 5:
                return None

            # Calculate metrics
            day_high = max(b.get('high', 0) for b in bars)
            day_low = min(b.get('low', 0) for b in bars)
            day_open = bars[0].get('open', current_price)
            total_volume = sum(b.get('volume', 0) for b in bars)

            # Calculate change from open
            change_pct = ((current_price - day_open) / day_open * 100) if day_open > 0 else 0

            # Get average volume (need historical data)
            avg_volume = await self._get_average_volume(symbol)
            volume_ratio = total_volume / avg_volume if avg_volume > 0 else 1.0

            # Calculate VWAP
            vwap = self._calculate_vwap(bars)

            # Check spread
            spread = quote.get('ask', 0) - quote.get('bid', 0)
            spread_pct = (spread / current_price * 100) if current_price > 0 else 999
            if spread_pct > self.config.max_spread_pct:
                return None  # Spread too wide

            # Detect setup type and calculate score
            setup_type, base_score, reasoning = self._detect_setup_type(
                symbol=symbol,
                current_price=current_price,
                day_open=day_open,
                day_high=day_high,
                day_low=day_low,
                change_pct=change_pct,
                volume_ratio=volume_ratio,
                vwap=vwap,
                market_phase=market_phase,
            )

            if setup_type is None or base_score < self.config.min_score_to_trade:
                return None

            # Check if already moved too much
            if abs(change_pct) > self.config.max_already_moved_pct:
                self.logger.debug(f"{symbol}: Already moved {change_pct:.1f}%, too late to enter")
                return None

            # Calculate entry, stop, targets
            entry_price = current_price

            # For long setups (most common)
            if change_pct > 0:
                stop_loss = entry_price * (1 - self.config.stop_loss_pct)
                target_1 = entry_price * (1 + self.config.target_1_pct)
                target_2 = entry_price * (1 + self.config.target_2_pct)
                target_3 = entry_price * (1 + self.config.target_3_pct)
            else:
                # Short setup (for gap downs) - inverted
                stop_loss = entry_price * (1 + self.config.stop_loss_pct)
                target_1 = entry_price * (1 - self.config.target_1_pct)
                target_2 = entry_price * (1 - self.config.target_2_pct)
                target_3 = entry_price * (1 - self.config.target_3_pct)

            return MomentumSetup(
                symbol=symbol,
                setup_type=setup_type,
                score=base_score,
                current_price=current_price,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target_1=target_1,
                target_2=target_2,
                target_3=target_3,
                change_pct=change_pct,
                volume_ratio=volume_ratio,
                vwap=vwap,
                day_high=day_high,
                day_low=day_low,
                reasoning=reasoning,
            )

        except Exception as e:
            self.logger.debug(f"Error analyzing {symbol}: {e}")
            return None

    def _detect_setup_type(
        self,
        symbol: str,
        current_price: float,
        day_open: float,
        day_high: float,
        day_low: float,
        change_pct: float,
        volume_ratio: float,
        vwap: Optional[float],
        market_phase: str,
    ) -> Tuple[Optional[SetupType], float, str]:
        """
        Detect the type of momentum setup and calculate score.

        Returns (setup_type, score, reasoning)
        """
        score = 0.0
        reasons = []
        setup_type = None

        # === GAP DETECTION (Pre-market/Early) ===
        if market_phase in ['premarket', 'early'] and abs(change_pct) >= self.config.min_gap_pct:
            if change_pct > 0:
                setup_type = SetupType.GAP_UP
                reasons.append(f"Gap up {change_pct:.1f}%")
                # Score based on gap size (3-6% is sweet spot)
                if 3 <= change_pct <= 6:
                    score += 4
                elif change_pct < 3:
                    score += 2
                else:
                    score += 3  # >6% can work but riskier
            else:
                setup_type = SetupType.GAP_DOWN
                reasons.append(f"Gap down {change_pct:.1f}%")
                score += 3  # Gap downs can bounce hard

        # === VWAP RECLAIM ===
        if vwap and current_price > vwap and (current_price - vwap) / vwap < 0.01:
            # Just crossed above VWAP
            if setup_type is None:
                setup_type = SetupType.VWAP_RECLAIM
            reasons.append("VWAP reclaim")
            score += 2

        # === RANGE BREAKOUT ===
        if current_price >= day_high * 0.998:  # Within 0.2% of day high
            if setup_type is None:
                setup_type = SetupType.RANGE_BREAKOUT
            reasons.append("Breaking day high")
            score += 2.5

        # === VOLUME CONFIRMATION ===
        if volume_ratio >= 3:
            reasons.append(f"Strong volume {volume_ratio:.1f}x")
            score += 3
        elif volume_ratio >= 2:
            reasons.append(f"Good volume {volume_ratio:.1f}x")
            score += 2
        elif volume_ratio >= 1.5:
            score += 1
        else:
            score -= 1  # Weak volume is a negative

        # === TIME OF DAY BONUS ===
        if market_phase == 'early':
            score += 1.5  # Best momentum in first hour
            reasons.append("Morning momentum")
        elif market_phase == 'power_hour':
            score += 1  # Last hour can have good moves
            reasons.append("Power hour")
        elif market_phase == 'midday':
            score -= 0.5  # Midday is often choppy

        # === MOMENTUM STRENGTH ===
        if abs(change_pct) >= 4:
            score += 1
        if abs(change_pct) >= 5:
            score += 0.5

        # === PRICE ACTION QUALITY ===
        # Near high of day is bullish
        if day_high > 0:
            high_ratio = current_price / day_high
            if high_ratio >= 0.98:
                score += 1
                reasons.append("Near day high")

        # If no setup type determined but has good score, call it momentum continuation
        if setup_type is None and score >= 5:
            setup_type = SetupType.MOMENTUM_CONTINUATION
            reasons.append("Strong momentum")

        # Minimum requirements
        if change_pct < self.config.min_change_pct and setup_type not in [SetupType.VWAP_RECLAIM]:
            return None, 0, ""

        if volume_ratio < self.config.min_volume_ratio:
            return None, 0, ""

        reasoning = " | ".join(reasons)
        return setup_type, min(score, 10), reasoning  # Cap at 10

    def _calculate_vwap(self, bars: List[Dict]) -> Optional[float]:
        """Calculate VWAP from intraday bars"""
        if not bars:
            return None

        total_volume = 0
        total_vp = 0  # Volume * Price

        for bar in bars:
            typical_price = (bar.get('high', 0) + bar.get('low', 0) + bar.get('close', 0)) / 3
            volume = bar.get('volume', 0)

            total_vp += typical_price * volume
            total_volume += volume

        return total_vp / total_volume if total_volume > 0 else None

    async def _get_average_volume(self, symbol: str) -> int:
        """Get 20-day average volume"""
        try:
            if self.alpaca:
                bars = await self.alpaca.get_bars(symbol, '1Day', limit=20)
                if bars:
                    volumes = [b.get('volume', 0) for b in bars]
                    return int(statistics.mean(volumes)) if volumes else 1_000_000
        except Exception:
            pass
        return 1_000_000  # Default

    def _get_market_phase(self) -> str:
        """Get current market phase"""
        now = datetime.now()
        current_time = now.time()

        # Convert to ET (approximate - should use proper timezone)
        # Assuming server is in ET or close to it

        market_open = time(9, 30)
        early_end = time(10, 30)  # First hour
        midday_start = time(11, 30)
        midday_end = time(14, 30)
        power_hour = time(15, 0)
        market_close = time(16, 0)

        if current_time < market_open:
            return 'premarket'
        elif current_time < early_end:
            return 'early'  # Best time for momentum
        elif current_time < midday_start:
            return 'late_morning'
        elif current_time < midday_end:
            return 'midday'  # Often choppy
        elif current_time < power_hour:
            return 'afternoon'
        elif current_time < market_close:
            return 'power_hour'  # Last hour
        else:
            return 'afterhours'

    def get_active_setups(self) -> List[MomentumSetup]:
        """Get currently active setups above minimum score"""
        return [s for s in self._active_setups.values() if s.score >= self.config.min_score_to_trade]

    def get_best_setup(self) -> Optional[MomentumSetup]:
        """Get the best current setup"""
        setups = self.get_active_setups()
        return setups[0] if setups else None


class PartialProfitManager:
    """
    Manages partial profit taking for positions.

    Strategy:
    - At target_1 (+1.5%): Sell 30%, move stop to breakeven
    - At target_2 (+2.5%): Sell 30% more, trail stop to +1%
    - At target_3 (+4%): Sell remaining or use tight trailing stop
    """

    def __init__(self, config: Optional[MomentumConfig] = None):
        self.config = config or MomentumConfig()
        self.logger = logging.getLogger(__name__)

        # Track partial exits per position
        # symbol -> {'original_qty': float, 'exits': [{'price': float, 'qty': float, 'target': int}]}
        self._position_exits: Dict[str, Dict] = {}

    def register_position(self, symbol: str, qty: float, entry_price: float, targets: Tuple[float, float, float]):
        """Register a new position for partial profit management"""
        self._position_exits[symbol] = {
            'original_qty': qty,
            'remaining_qty': qty,
            'entry_price': entry_price,
            'target_1': targets[0],
            'target_2': targets[1],
            'target_3': targets[2],
            'exits': [],
            'current_target': 1,
            'stop_price': entry_price * (1 - self.config.stop_loss_pct),
        }
        self.logger.info(
            f"📊 Registered {symbol} for partial profits: "
            f"T1=${targets[0]:.2f} T2=${targets[1]:.2f} T3=${targets[2]:.2f}"
        )

    def check_targets(self, symbol: str, current_price: float) -> Optional[Dict]:
        """
        Check if position has hit any targets.

        Returns dict with action to take, or None if no action needed.
        """
        if symbol not in self._position_exits:
            return None

        pos = self._position_exits[symbol]
        current_target = pos['current_target']
        remaining_qty = pos['remaining_qty']

        if remaining_qty <= 0:
            return None

        action = None

        # Check targets in order
        if current_target == 1 and current_price >= pos['target_1']:
            sell_qty = pos['original_qty'] * self.config.partial_profit_1_pct
            sell_qty = min(sell_qty, remaining_qty)

            action = {
                'action': 'PARTIAL_SELL',
                'symbol': symbol,
                'qty': sell_qty,
                'reason': f"Target 1 hit (+1.5%)",
                'new_stop': pos['entry_price'],  # Move stop to breakeven
            }

            pos['remaining_qty'] -= sell_qty
            pos['current_target'] = 2
            pos['stop_price'] = pos['entry_price']  # Breakeven stop
            pos['exits'].append({'price': current_price, 'qty': sell_qty, 'target': 1})

            self.logger.info(f"🎯 {symbol} HIT TARGET 1: Selling {sell_qty:.2f} shares, stop → breakeven")

        elif current_target == 2 and current_price >= pos['target_2']:
            sell_qty = pos['original_qty'] * self.config.partial_profit_2_pct
            sell_qty = min(sell_qty, remaining_qty)

            # Trail stop to +1%
            new_stop = pos['entry_price'] * 1.01

            action = {
                'action': 'PARTIAL_SELL',
                'symbol': symbol,
                'qty': sell_qty,
                'reason': f"Target 2 hit (+2.5%)",
                'new_stop': new_stop,
            }

            pos['remaining_qty'] -= sell_qty
            pos['current_target'] = 3
            pos['stop_price'] = new_stop
            pos['exits'].append({'price': current_price, 'qty': sell_qty, 'target': 2})

            self.logger.info(f"🎯 {symbol} HIT TARGET 2: Selling {sell_qty:.2f} shares, stop → +1%")

        elif current_target == 3 and current_price >= pos['target_3']:
            # Sell remaining
            sell_qty = remaining_qty

            action = {
                'action': 'CLOSE_POSITION',
                'symbol': symbol,
                'qty': sell_qty,
                'reason': f"Target 3 hit (+4%)",
                'new_stop': None,
            }

            pos['remaining_qty'] = 0
            pos['exits'].append({'price': current_price, 'qty': sell_qty, 'target': 3})

            self.logger.info(f"🎯 {symbol} HIT TARGET 3: Closing remaining {sell_qty:.2f} shares")

        return action

    def check_stop(self, symbol: str, current_price: float) -> Optional[Dict]:
        """Check if stop loss should be triggered"""
        if symbol not in self._position_exits:
            return None

        pos = self._position_exits[symbol]

        if current_price <= pos['stop_price'] and pos['remaining_qty'] > 0:
            return {
                'action': 'STOP_LOSS',
                'symbol': symbol,
                'qty': pos['remaining_qty'],
                'reason': f"Stop loss at ${pos['stop_price']:.2f}",
            }

        return None

    def update_trailing_stop(self, symbol: str, current_price: float, trail_pct: Optional[float] = None):
        """Update trailing stop if price moved up"""
        if symbol not in self._position_exits:
            return

        pos = self._position_exits[symbol]
        trail = trail_pct if trail_pct is not None else self.config.trailing_stop_pct

        # Only trail after first target hit
        if pos['current_target'] > 1:
            new_stop = current_price * (1 - trail)
            if new_stop > pos['stop_price']:
                old_stop = pos['stop_price']
                pos['stop_price'] = new_stop
                self.logger.debug(f"📈 {symbol} trailing stop: ${old_stop:.2f} → ${new_stop:.2f}")

    def get_position_status(self, symbol: str) -> Optional[Dict]:
        """Get status of a managed position"""
        return self._position_exits.get(symbol)

    def remove_position(self, symbol: str):
        """Remove position from management"""
        if symbol in self._position_exits:
            del self._position_exits[symbol]

"""
Daily Summary Generator

Generates end-of-day trading summaries for autonomous mode.
"""
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class TradeSummary:
    """Summary of a single trade"""
    symbol: str
    action: str
    price: float
    shares: float
    value: float
    confidence: float
    success: bool
    timestamp: datetime
    reasoning: str = ""
    error: Optional[str] = None


@dataclass
class DailySummaryData:
    """Daily summary data"""
    date: datetime
    total_trades: int
    successful_trades: int
    failed_trades: int
    buy_trades: int
    sell_trades: int
    total_volume: float
    trades: List[TradeSummary]
    portfolio_value: float
    buying_power: float
    positions: List[Dict]
    daily_pnl: float
    daily_pnl_pct: float
    win_rate: float


class DailySummary:
    """
    Generates comprehensive daily trading summaries.
    """

    def generate(self, trades: List[Dict], portfolio: Dict) -> DailySummaryData:
        """
        Generate daily summary from trades and portfolio state.

        Args:
            trades: List of trade records from the day
            portfolio: Current portfolio state

        Returns:
            DailySummaryData with all metrics
        """
        now = datetime.now()

        # Process trades
        trade_summaries = []
        successful = 0
        failed = 0
        buys = 0
        sells = 0
        total_volume = 0.0

        for trade in trades:
            ts = TradeSummary(
                symbol=trade.get('symbol', ''),
                action=trade.get('action', ''),
                price=trade.get('price', 0),
                shares=trade.get('shares', 0),
                value=trade.get('value', 0),
                confidence=trade.get('confidence', 0),
                success=trade.get('success', False),
                timestamp=trade.get('timestamp', now),
                reasoning=trade.get('reasoning', ''),
                error=trade.get('error'),
            )
            trade_summaries.append(ts)

            if ts.success:
                successful += 1
            else:
                failed += 1

            if ts.action.upper() == 'BUY':
                buys += 1
            elif ts.action.upper() == 'SELL':
                sells += 1

            total_volume += ts.value

        # Calculate win rate
        total = len(trades)
        win_rate = (successful / total * 100) if total > 0 else 0

        # Portfolio metrics
        portfolio_value = portfolio.get('equity', 0)
        buying_power = portfolio.get('buying_power', 0)
        positions_data = portfolio.get('positions', {})
        # Handle both dict (keyed by symbol) and list formats
        if isinstance(positions_data, dict):
            positions = list(positions_data.values())
        else:
            positions = positions_data
        daily_pnl = portfolio.get('total_unrealized_pl', 0)

        # Calculate daily P&L percentage
        if portfolio_value > 0:
            daily_pnl_pct = (daily_pnl / portfolio_value) * 100
        else:
            daily_pnl_pct = 0

        return DailySummaryData(
            date=now,
            total_trades=total,
            successful_trades=successful,
            failed_trades=failed,
            buy_trades=buys,
            sell_trades=sells,
            total_volume=total_volume,
            trades=trade_summaries,
            portfolio_value=portfolio_value,
            buying_power=buying_power,
            positions=positions,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            win_rate=win_rate,
        )

    def display_rich(self, summary: DailySummaryData, console):
        """Display summary using Rich formatting"""
        from rich.table import Table
        from rich.panel import Panel
        from rich.text import Text
        from rich.box import ROUNDED, DOUBLE

        # Header
        header = Text()
        header.append("📊 DAILY TRADING SUMMARY\n", style="bold white")
        header.append(f"{summary.date.strftime('%Y-%m-%d %H:%M:%S')}", style="dim")

        console.print(Panel(header, box=DOUBLE, style="blue"))

        # Performance Overview
        perf_table = Table(show_header=False, box=None, padding=(0, 2))
        perf_table.add_column(justify="left")
        perf_table.add_column(justify="right")

        pnl_style = "green" if summary.daily_pnl >= 0 else "red"
        pnl_sign = "+" if summary.daily_pnl >= 0 else ""

        perf_table.add_row(
            Text("Portfolio Value:", style="dim"),
            Text(f"${summary.portfolio_value:,.2f}", style="bold white")
        )
        perf_table.add_row(
            Text("Buying Power:", style="dim"),
            Text(f"${summary.buying_power:,.2f}", style="cyan")
        )
        perf_table.add_row(
            Text("Daily P&L:", style="dim"),
            Text(f"{pnl_sign}${summary.daily_pnl:,.2f} ({pnl_sign}{summary.daily_pnl_pct:.2f}%)", style=pnl_style)
        )

        console.print(Panel(perf_table, title="💰 Performance", box=ROUNDED))

        # Trading Activity
        activity_table = Table(show_header=False, box=None, padding=(0, 2))
        activity_table.add_column(justify="left")
        activity_table.add_column(justify="right")

        activity_table.add_row(
            Text("Total Trades:", style="dim"),
            Text(str(summary.total_trades), style="white")
        )
        activity_table.add_row(
            Text("Successful:", style="dim"),
            Text(str(summary.successful_trades), style="green")
        )
        activity_table.add_row(
            Text("Failed:", style="dim"),
            Text(str(summary.failed_trades), style="red" if summary.failed_trades > 0 else "dim")
        )
        activity_table.add_row(
            Text("Buy Orders:", style="dim"),
            Text(str(summary.buy_trades), style="cyan")
        )
        activity_table.add_row(
            Text("Sell Orders:", style="dim"),
            Text(str(summary.sell_trades), style="yellow")
        )
        activity_table.add_row(
            Text("Win Rate:", style="dim"),
            Text(f"{summary.win_rate:.1f}%", style="green" if summary.win_rate >= 50 else "yellow")
        )
        activity_table.add_row(
            Text("Total Volume:", style="dim"),
            Text(f"${summary.total_volume:,.2f}", style="white")
        )

        console.print(Panel(activity_table, title="📈 Trading Activity", box=ROUNDED))

        # Trades List
        if summary.trades:
            trades_table = Table(box=ROUNDED, show_header=True)
            trades_table.add_column("Time", style="dim")
            trades_table.add_column("Symbol", style="cyan")
            trades_table.add_column("Action")
            trades_table.add_column("Price", justify="right")
            trades_table.add_column("Shares", justify="right")
            trades_table.add_column("Value", justify="right")
            trades_table.add_column("Conf", justify="right")
            trades_table.add_column("Status")

            for trade in summary.trades:
                action_style = "green" if trade.action.upper() == 'BUY' else "red"
                status = "✅" if trade.success else "❌"
                status_style = "green" if trade.success else "red"

                trades_table.add_row(
                    trade.timestamp.strftime("%H:%M:%S"),
                    trade.symbol,
                    Text(trade.action, style=action_style),
                    f"${trade.price:.2f}",
                    f"{trade.shares:.2f}",
                    f"${trade.value:.2f}",
                    f"{trade.confidence*100:.0f}%",
                    Text(status, style=status_style),
                )

            console.print(Panel(trades_table, title="📝 Trades Executed", box=ROUNDED))

        # Current Holdings
        if summary.positions:
            holdings_table = Table(box=ROUNDED, show_header=True)
            holdings_table.add_column("Symbol", style="cyan")
            holdings_table.add_column("Qty", justify="right")
            holdings_table.add_column("Avg Cost", justify="right")
            holdings_table.add_column("Current", justify="right")
            holdings_table.add_column("Value", justify="right")
            holdings_table.add_column("P&L", justify="right")

            for pos in summary.positions:
                pnl = pos.get('unrealized_pl', 0)
                pnl_style = "green" if pnl >= 0 else "red"
                pnl_sign = "+" if pnl >= 0 else ""

                holdings_table.add_row(
                    pos.get('symbol', ''),
                    f"{pos.get('qty', 0):.2f}",
                    f"${pos.get('avg_entry_price', 0):.2f}",
                    f"${pos.get('current_price', 0):.2f}",
                    f"${pos.get('market_value', 0):.2f}",
                    Text(f"{pnl_sign}${pnl:.2f}", style=pnl_style),
                )

            console.print(Panel(holdings_table, title="📦 Current Holdings", box=ROUNDED))
        else:
            console.print(Panel(Text("No open positions", style="dim"), title="📦 Current Holdings", box=ROUNDED))

        # Footer
        console.print("\n" + "=" * 60)
        console.print(Text("End of Daily Summary", style="dim"))

    def display_simple(self, summary: DailySummaryData):
        """Display summary in simple text format"""
        print("\n" + "=" * 60)
        print("📊 DAILY TRADING SUMMARY")
        print(f"   {summary.date.strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

        pnl_sign = "+" if summary.daily_pnl >= 0 else ""

        print("\n💰 PERFORMANCE")
        print(f"   Portfolio Value: ${summary.portfolio_value:,.2f}")
        print(f"   Buying Power:    ${summary.buying_power:,.2f}")
        print(f"   Daily P&L:       {pnl_sign}${summary.daily_pnl:,.2f} ({pnl_sign}{summary.daily_pnl_pct:.2f}%)")

        print("\n📈 TRADING ACTIVITY")
        print(f"   Total Trades:  {summary.total_trades}")
        print(f"   Successful:    {summary.successful_trades}")
        print(f"   Failed:        {summary.failed_trades}")
        print(f"   Buy Orders:    {summary.buy_trades}")
        print(f"   Sell Orders:   {summary.sell_trades}")
        print(f"   Win Rate:      {summary.win_rate:.1f}%")
        print(f"   Total Volume:  ${summary.total_volume:,.2f}")

        if summary.trades:
            print("\n📝 TRADES EXECUTED")
            print("-" * 60)
            for trade in summary.trades:
                status = "✅" if trade.success else "❌"
                print(f"   {trade.timestamp.strftime('%H:%M:%S')} | {trade.action:4} {trade.symbol:5} | "
                      f"${trade.price:.2f} x {trade.shares:.2f} = ${trade.value:.2f} | {status}")

        if summary.positions:
            print("\n📦 CURRENT HOLDINGS")
            print("-" * 60)
            for pos in summary.positions:
                pnl = pos.get('unrealized_pl', 0)
                pnl_sign = "+" if pnl >= 0 else ""
                print(f"   {pos.get('symbol', ''):5} | Qty: {pos.get('qty', 0):>8.2f} | "
                      f"Value: ${pos.get('market_value', 0):>10.2f} | P&L: {pnl_sign}${pnl:.2f}")
        else:
            print("\n📦 CURRENT HOLDINGS")
            print("   No open positions")

        print("\n" + "=" * 60)
        print("End of Daily Summary\n")

    def save_to_file(self, summary: DailySummaryData, filepath: str):
        """Save summary to a file"""
        import json

        data = {
            'date': summary.date.isoformat(),
            'performance': {
                'portfolio_value': summary.portfolio_value,
                'buying_power': summary.buying_power,
                'daily_pnl': summary.daily_pnl,
                'daily_pnl_pct': summary.daily_pnl_pct,
            },
            'activity': {
                'total_trades': summary.total_trades,
                'successful_trades': summary.successful_trades,
                'failed_trades': summary.failed_trades,
                'buy_trades': summary.buy_trades,
                'sell_trades': summary.sell_trades,
                'win_rate': summary.win_rate,
                'total_volume': summary.total_volume,
            },
            'trades': [
                {
                    'timestamp': t.timestamp.isoformat(),
                    'symbol': t.symbol,
                    'action': t.action,
                    'price': t.price,
                    'shares': t.shares,
                    'value': t.value,
                    'confidence': t.confidence,
                    'success': t.success,
                    'reasoning': t.reasoning,
                    'error': t.error,
                }
                for t in summary.trades
            ],
            'positions': summary.positions,
        }

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

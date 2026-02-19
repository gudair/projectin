"""
Alert Formatters

Rich terminal formatting for trading alerts.
"""
from datetime import datetime
from typing import Dict, Optional
import sys

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    from rich.live import Live
    from rich.box import ROUNDED, DOUBLE, HEAVY
    from rich.style import Style
    from rich.align import Align
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from alerts.manager import Alert, AlertLevel, AlertAction


class AlertFormatter:
    """
    Formats alerts for rich terminal display.
    Falls back to basic formatting if Rich is not available.
    """

    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        if self.use_rich:
            self.console = Console()

    def format_alert(self, alert: Alert) -> str:
        """Format alert for display"""
        if self.use_rich:
            return self._format_rich(alert)
        return self._format_basic(alert)

    def display_alert(self, alert: Alert):
        """Display alert in terminal"""
        if self.use_rich:
            self._display_rich(alert)
        else:
            print(self._format_basic(alert))

    def _format_basic(self, alert: Alert) -> str:
        """Basic text formatting"""
        opp = alert.opportunity

        lines = [
            "=" * 60,
            f"  {'🚨 IMMEDIATE' if alert.level == AlertLevel.IMMEDIATE else '📊 STANDARD'} ALERT",
            "=" * 60,
            f"  {opp.action} {opp.symbol} @ ${opp.current_price:.2f}",
            f"  Confidence: {opp.confidence*100:.0f}% | R:R {opp.risk_reward_ratio:.1f}:1",
            f"  Target: ${opp.target_price:.2f} | Stop: ${opp.stop_loss:.2f}",
            f"  Size: ${opp.position_size:.2f} ({opp.shares:.4f} shares)",
            "-" * 60,
            f"  Reasoning: {opp.reasoning}",
        ]

        if opp.similar_trades_win_rate:
            lines.append(f"  Similar trades: {opp.similar_trades_win_rate*100:.0f}% win rate")

        if alert.expires_at:
            seconds_left = alert.time_until_expiry
            lines.append(f"  Expires in: {seconds_left}s")

        lines.extend([
            "=" * 60,
            "  [C]onfirm  [R]eject  [M]ore Info",
            "=" * 60,
        ])

        return "\n".join(lines)

    def _format_rich(self, alert: Alert) -> Panel:
        """Rich formatting with colors and panels"""
        opp = alert.opportunity

        # Determine colors based on action and level
        if opp.action == 'BUY':
            action_color = "green"
            action_emoji = "📈"
        else:
            action_color = "red"
            action_emoji = "📉"

        if alert.level == AlertLevel.IMMEDIATE:
            level_style = "bold red"
            level_text = "🚨 IMMEDIATE ALERT"
            box = DOUBLE
        else:
            level_style = "yellow"
            level_text = "📊 STANDARD ALERT"
            box = ROUNDED

        # Build content
        content = Table.grid(padding=(0, 2))
        content.add_column(justify="left")
        content.add_column(justify="right")

        # Main trade info
        trade_text = Text()
        trade_text.append(f"{action_emoji} {opp.action} ", style=f"bold {action_color}")
        trade_text.append(f"{opp.symbol}", style="bold white")
        trade_text.append(f" @ ", style="dim")
        trade_text.append(f"${opp.current_price:.2f}", style="bold cyan")

        confidence_text = Text()
        conf_color = "green" if opp.confidence >= 0.7 else "yellow" if opp.confidence >= 0.5 else "red"
        confidence_text.append(f"Confidence: ", style="dim")
        confidence_text.append(f"{opp.confidence*100:.0f}%", style=f"bold {conf_color}")
        confidence_text.append(f" | R:R ", style="dim")
        confidence_text.append(f"{opp.risk_reward_ratio:.1f}:1", style="bold")

        content.add_row(trade_text, confidence_text)

        # Targets
        targets_text = Text()
        targets_text.append("Target: ", style="dim")
        targets_text.append(f"${opp.target_price:.2f}", style="green")
        targets_text.append(" | Stop: ", style="dim")
        targets_text.append(f"${opp.stop_loss:.2f}", style="red")

        size_text = Text()
        size_text.append("Size: ", style="dim")
        size_text.append(f"${opp.position_size:.2f}", style="cyan")
        size_text.append(f" ({opp.shares:.4f} shares)", style="dim")

        content.add_row(targets_text, size_text)

        # Reasoning
        reason_text = Text()
        reason_text.append("\nReasoning: ", style="dim italic")
        reason_text.append(opp.reasoning, style="white")

        if opp.similar_trades_win_rate:
            reason_text.append(f"\nSimilar setups: ", style="dim")
            win_color = "green" if opp.similar_trades_win_rate >= 0.6 else "yellow"
            reason_text.append(f"{opp.similar_trades_win_rate*100:.0f}% win rate", style=f"bold {win_color}")

        content.add_row(reason_text, Text(""))

        # Timer
        if alert.expires_at:
            seconds_left = alert.time_until_expiry or 0
            timer_style = "bold red" if seconds_left < 30 else "yellow" if seconds_left < 60 else "dim"
            timer_text = Text(f"\n⏱️  Expires in: {seconds_left}s", style=timer_style)
            content.add_row(timer_text, Text(""))

        # Actions
        actions_text = Text("\n[C]onfirm  [R]eject  [M]ore Info", style="bold cyan")
        content.add_row(Align.center(actions_text), Text(""))

        return Panel(
            content,
            title=Text(level_text, style=level_style),
            subtitle=f"Alert ID: {alert.id}",
            box=box,
            border_style=action_color,
            padding=(1, 2),
        )

    def _display_rich(self, alert: Alert):
        """Display rich formatted alert"""
        panel = self._format_rich(alert)
        self.console.print()
        self.console.print(panel)
        self.console.print()

    def format_portfolio_summary(self, portfolio: Dict) -> str:
        """Format portfolio summary"""
        if self.use_rich:
            return self._format_portfolio_rich(portfolio)
        return self._format_portfolio_basic(portfolio)

    def _format_portfolio_basic(self, portfolio: Dict) -> str:
        """Basic portfolio formatting"""
        lines = [
            "PORTFOLIO SUMMARY",
            "-" * 40,
            f"Cash: ${portfolio.get('cash', 0):.2f}",
            f"Positions: {portfolio.get('positions_count', 0)}",
            f"Total Value: ${portfolio.get('total_value', 0):.2f}",
            f"Daily P&L: ${portfolio.get('daily_pnl', 0):.2f}",
        ]
        return "\n".join(lines)

    def _format_portfolio_rich(self, portfolio: Dict) -> Panel:
        """Rich portfolio formatting"""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(justify="left")
        table.add_column(justify="right")

        cash = portfolio.get('cash', 0)
        total = portfolio.get('total_value', 0)
        daily_pnl = portfolio.get('daily_pnl', 0)
        positions = portfolio.get('positions_count', 0)

        table.add_row(
            Text("Cash:", style="dim"),
            Text(f"${cash:.2f}", style="cyan")
        )
        table.add_row(
            Text("Positions:", style="dim"),
            Text(str(positions), style="white")
        )
        table.add_row(
            Text("Total Value:", style="dim"),
            Text(f"${total:.2f}", style="bold white")
        )

        pnl_color = "green" if daily_pnl >= 0 else "red"
        pnl_prefix = "+" if daily_pnl >= 0 else ""
        table.add_row(
            Text("Daily P&L:", style="dim"),
            Text(f"{pnl_prefix}${daily_pnl:.2f}", style=f"bold {pnl_color}")
        )

        return Panel(
            table,
            title="📊 Portfolio",
            box=ROUNDED,
            border_style="blue",
        )

    def format_market_context(self, context: Dict) -> str:
        """Format market context display"""
        if self.use_rich:
            return self._format_context_rich(context)
        return self._format_context_basic(context)

    def _format_context_basic(self, context: Dict) -> str:
        """Basic market context formatting"""
        spy = context.get('spy', {})
        vix = context.get('vix', {})
        regime = context.get('regime', 'UNKNOWN')

        lines = [
            "MARKET CONTEXT",
            "-" * 40,
            f"SPY: ${spy.get('price', 0):.2f} ({spy.get('change_pct', 0):+.2f}%)",
            f"VIX: {vix.get('value', 0):.1f} ({vix.get('change_pct', 0):+.2f}%)",
            f"Regime: {regime}",
        ]
        return "\n".join(lines)

    def _format_context_rich(self, context: Dict) -> Panel:
        """Rich market context formatting"""
        spy = context.get('spy', {})
        vix = context.get('vix', {})
        regime = context.get('regime', 'UNKNOWN')

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(justify="left")
        table.add_column(justify="right")

        # SPY
        spy_change = spy.get('change_pct', 0)
        spy_color = "green" if spy_change >= 0 else "red"
        spy_text = Text()
        spy_text.append(f"${spy.get('price', 0):.2f} ", style="white")
        spy_text.append(f"({spy_change:+.2f}%)", style=spy_color)
        table.add_row(Text("SPY:", style="dim"), spy_text)

        # VIX
        vix_value = vix.get('value', 0)
        vix_color = "red" if vix_value > 25 else "yellow" if vix_value > 18 else "green"
        vix_text = Text(f"{vix_value:.1f}", style=vix_color)
        table.add_row(Text("VIX:", style="dim"), vix_text)

        # Regime
        regime_colors = {
            'RISK_ON': 'green',
            'RISK_OFF': 'red',
            'NEUTRAL': 'yellow',
            'HIGH_VOLATILITY': 'bold red',
        }
        regime_color = regime_colors.get(regime, 'white')
        table.add_row(
            Text("Regime:", style="dim"),
            Text(regime, style=regime_color)
        )

        return Panel(
            table,
            title="🌍 Market",
            box=ROUNDED,
            border_style="cyan",
        )

    def format_confirmation(self, alert: Alert, action: AlertAction) -> str:
        """Format trade confirmation message"""
        opp = alert.opportunity

        if action == AlertAction.CONFIRM:
            if self.use_rich:
                text = Text()
                text.append("✅ CONFIRMED: ", style="bold green")
                text.append(f"{opp.action} {opp.symbol}", style="bold")
                text.append(f" @ ${opp.current_price:.2f}", style="cyan")
                self.console.print(text)
                return ""
            return f"✅ CONFIRMED: {opp.action} {opp.symbol} @ ${opp.current_price:.2f}"

        elif action == AlertAction.REJECT:
            if self.use_rich:
                text = Text()
                text.append("❌ REJECTED: ", style="bold red")
                text.append(f"{opp.action} {opp.symbol}", style="dim")
                self.console.print(text)
                return ""
            return f"❌ REJECTED: {opp.action} {opp.symbol}"

        return ""

    def print_status_line(self, status: Dict):
        """Print compact status line"""
        if not self.use_rich:
            print(f"[{status.get('time', '')}] Market: {status.get('market', 'CLOSED')} | Alerts: {status.get('pending', 0)}")
            return

        line = Text()
        line.append(f"[{status.get('time', '')}] ", style="dim")

        market = status.get('market', 'CLOSED')
        market_color = "green" if market == 'OPEN' else "red"
        line.append(f"Market: ", style="dim")
        line.append(f"{market}", style=market_color)

        line.append(" | ", style="dim")

        pending = status.get('pending', 0)
        pending_color = "yellow" if pending > 0 else "dim"
        line.append(f"Alerts: ", style="dim")
        line.append(f"{pending}", style=pending_color)

        self.console.print(line)

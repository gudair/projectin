"""
Terminal Dashboard

Rich terminal dashboard for the AI Trading Agent.
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich.box import ROUNDED, DOUBLE
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from agent.core.agent import TradingAgent, AgentState
from config.agent_config import MarketRegime, AlertLevel
from alerts.manager import Alert, AlertAction


class Dashboard:
    """
    Live terminal dashboard for the trading agent.

    Displays:
    - Agent status
    - Portfolio summary
    - Market context
    - Pending alerts
    - Recent trades
    """

    def __init__(self, agent: TradingAgent):
        self.agent = agent
        self.console = Console() if RICH_AVAILABLE else None
        self._current_alert: Optional[Alert] = None
        self._refresh_rate = 1.0  # seconds

    async def run(self, shutdown_event: asyncio.Event):
        """Run the live dashboard"""
        if not RICH_AVAILABLE:
            print("Rich library not available. Running in simple mode.")
            await self._run_simple(shutdown_event)
            return

        # Create layout
        layout = self._create_layout()

        with Live(layout, console=self.console, refresh_per_second=2, screen=True) as live:
            while not shutdown_event.is_set():
                # Update layout
                self._update_layout(layout)

                # Check for pending alerts
                alert = self.agent.alert_manager.get_pending_alert()
                if alert:
                    self._current_alert = alert
                    # Handle alert interactively
                    await self._handle_alert_in_dashboard(alert, live)
                    self._current_alert = None

                await asyncio.sleep(self._refresh_rate)

    async def _run_simple(self, shutdown_event: asyncio.Event):
        """Run in simple mode without Rich"""
        while not shutdown_event.is_set():
            status = self.agent.get_status()
            print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                  f"State: {status.state.value} | "
                  f"Signals: {status.signals_generated} | "
                  f"Alerts: {status.alerts_sent} | "
                  f"Trades: {status.trades_executed}",
                  end='', flush=True)
            await asyncio.sleep(1)

    def _create_layout(self) -> Layout:
        """Create dashboard layout"""
        layout = Layout()

        layout.split(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3),
        )

        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )

        layout["left"].split(
            Layout(name="portfolio", ratio=1),
            Layout(name="positions", ratio=1),
        )

        layout["right"].split(
            Layout(name="market", ratio=1),
            Layout(name="alerts", ratio=2),
        )

        return layout

    def _update_layout(self, layout: Layout):
        """Update all layout panels"""
        layout["header"].update(self._render_header())
        layout["portfolio"].update(self._render_portfolio())
        layout["positions"].update(self._render_positions())
        layout["market"].update(self._render_market_context())
        layout["alerts"].update(self._render_alerts())
        layout["footer"].update(self._render_footer())

    def _render_header(self) -> Panel:
        """Render header panel"""
        status = self.agent.get_status()

        state_colors = {
            AgentState.RUNNING: "green",
            AgentState.PAUSED: "yellow",
            AgentState.STOPPED: "red",
            AgentState.ERROR: "red",
            AgentState.STARTING: "yellow",
        }
        state_color = state_colors.get(status.state, "white")

        market_status = "🟢 OPEN" if status.market_open else "🔴 CLOSED"

        title = Text()
        title.append("AI TRADING AGENT", style="bold white")
        title.append(" v1.0 | ", style="dim")
        title.append(f"[{status.state.value.upper()}]", style=f"bold {state_color}")
        title.append(f" | Market: {market_status}", style="white")

        return Panel(
            Align.center(title),
            box=DOUBLE,
            style="blue",
        )

    def _render_portfolio(self) -> Panel:
        """Render portfolio panel"""
        try:
            portfolio = self.agent.get_portfolio_summary()
        except Exception:
            portfolio = {}

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(justify="left")
        table.add_column(justify="right")

        cash = portfolio.get('buying_power', 0)
        equity = portfolio.get('equity', 0)
        total_positions = portfolio.get('total_positions', 0)
        unrealized = portfolio.get('total_unrealized_pl', 0)

        table.add_row(
            Text("Buying Power:", style="dim"),
            Text(f"${cash:,.2f}", style="cyan")
        )
        table.add_row(
            Text("Equity:", style="dim"),
            Text(f"${equity:,.2f}", style="bold white")
        )
        table.add_row(
            Text("Positions:", style="dim"),
            Text(str(total_positions), style="white")
        )

        pnl_color = "green" if unrealized >= 0 else "red"
        table.add_row(
            Text("Unrealized P&L:", style="dim"),
            Text(f"${unrealized:+,.2f}", style=pnl_color)
        )

        return Panel(
            table,
            title="📊 Portfolio",
            box=ROUNDED,
            border_style="blue",
        )

    def _render_positions(self) -> Panel:
        """Render positions panel"""
        try:
            portfolio = self.agent.get_portfolio_summary()
            positions = portfolio.get('positions', [])
        except Exception:
            positions = []

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Symbol", style="cyan")
        table.add_column("Qty", justify="right")
        table.add_column("Value", justify="right")
        table.add_column("P&L", justify="right")

        if positions:
            for pos in positions[:5]:  # Show top 5
                pnl = pos.get('unrealized_pl', 0)
                pnl_color = "green" if pnl >= 0 else "red"

                table.add_row(
                    pos.get('symbol', ''),
                    f"{pos.get('qty', 0):.2f}",
                    f"${pos.get('market_value', 0):,.2f}",
                    Text(f"${pnl:+.2f}", style=pnl_color),
                )
        else:
            table.add_row("No positions", "", "", "")

        return Panel(
            table,
            title="📈 Positions",
            box=ROUNDED,
            border_style="blue",
        )

    def _render_market_context(self) -> Panel:
        """Render market context panel"""
        context_summary = self.agent.get_market_context_summary()

        if context_summary:
            content = Text(context_summary)
        else:
            content = Text("Loading market context...", style="dim")

        status = self.agent.get_status()
        regime = status.current_regime

        regime_colors = {
            MarketRegime.RISK_ON: "green",
            MarketRegime.NEUTRAL: "yellow",
            MarketRegime.RISK_OFF: "orange1",
            MarketRegime.HIGH_VOLATILITY: "red",
        }
        border_color = regime_colors.get(regime, "blue")

        return Panel(
            content,
            title="🌍 Market Context",
            box=ROUNDED,
            border_style=border_color,
        )

    def _render_alerts(self) -> Panel:
        """Render alerts panel"""
        status = self.agent.get_status()
        pending = self.agent.alert_manager.pending_count()

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Status", width=10)
        table.add_column("Stats", justify="right")

        table.add_row(
            Text("Pending:", style="yellow" if pending > 0 else "dim"),
            Text(str(pending), style="bold yellow" if pending > 0 else "dim"),
        )
        table.add_row(
            Text("Generated:", style="dim"),
            Text(str(status.signals_generated)),
        )
        table.add_row(
            Text("Sent:", style="dim"),
            Text(str(status.alerts_sent)),
        )
        table.add_row(
            Text("Trades:", style="dim"),
            Text(str(status.trades_executed), style="green"),
        )

        # Show current alert if any
        if self._current_alert:
            opp = self._current_alert.opportunity
            alert_text = Text()
            alert_text.append(f"\n🚨 {opp.action} {opp.symbol}\n", style="bold yellow")
            alert_text.append(f"@ ${opp.current_price:.2f} | ", style="white")
            alert_text.append(f"{opp.confidence*100:.0f}% conf", style="cyan")

            return Panel(
                Text.assemble(table, alert_text),
                title="🔔 Alerts",
                box=ROUNDED,
                border_style="yellow",
            )

        return Panel(
            table,
            title="🔔 Alerts",
            box=ROUNDED,
            border_style="blue",
        )

    def _render_footer(self) -> Panel:
        """Render footer panel"""
        commands = Text()
        commands.append("[C]", style="bold cyan")
        commands.append("onfirm  ", style="dim")
        commands.append("[R]", style="bold cyan")
        commands.append("eject  ", style="dim")
        commands.append("[P]", style="bold cyan")
        commands.append("ause  ", style="dim")
        commands.append("[Q]", style="bold cyan")
        commands.append("uit", style="dim")

        time_str = datetime.now().strftime("%H:%M:%S")
        commands.append(f"   |   {time_str}", style="dim")

        return Panel(
            Align.center(commands),
            box=ROUNDED,
            style="dim",
        )

    async def _handle_alert_in_dashboard(self, alert: Alert, live: Live):
        """Handle alert within the dashboard context"""
        from alerts.formatters import AlertFormatter

        # Pause live display
        live.stop()

        # Show full alert
        formatter = AlertFormatter(use_rich=True)
        formatter.display_alert(alert)

        # Get user input
        while True:
            try:
                response = input("Action [c]onfirm / [r]eject / [m]ore info: ").strip().lower()

                if response in ['c', 'confirm']:
                    result = await self.agent.handle_alert_response(alert, AlertAction.CONFIRM)
                    if result and result.is_success:
                        self.console.print("[bold green]Trade confirmed and executed![/]")
                    else:
                        error = result.error_message if result else 'Unknown error'
                        self.console.print(f"[bold red]Execution failed: {error}[/]")
                    break

                elif response in ['r', 'reject']:
                    self.agent.alert_manager.respond_to_alert(alert, AlertAction.REJECT)
                    self.console.print("[yellow]Alert rejected[/]")
                    break

                elif response in ['m', 'more']:
                    self._print_more_info(alert)

                else:
                    print("Invalid input. Enter 'c', 'r', or 'm'")

            except EOFError:
                self.agent.alert_manager.respond_to_alert(alert, AlertAction.SKIP)
                break

        # Resume live display
        live.start()

    def _print_more_info(self, alert: Alert):
        """Print detailed alert info"""
        opp = alert.opportunity

        table = Table(title="Detailed Analysis", box=ROUNDED)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Symbol", opp.symbol)
        table.add_row("Action", opp.action)
        table.add_row("Price", f"${opp.current_price:.2f}")
        table.add_row("Target", f"${opp.target_price:.2f}")
        table.add_row("Stop Loss", f"${opp.stop_loss:.2f}")
        table.add_row("Size", f"${opp.position_size:.2f}")
        table.add_row("Shares", f"{opp.shares:.4f}")
        table.add_row("Confidence", f"{opp.confidence*100:.1f}%")
        table.add_row("R:R Ratio", f"{opp.risk_reward_ratio:.2f}:1")

        if opp.similar_trades_win_rate:
            table.add_row("Historical Win Rate", f"{opp.similar_trades_win_rate*100:.1f}%")

        self.console.print(table)
        self.console.print(f"\n[bold]Reasoning:[/] {opp.reasoning}\n")

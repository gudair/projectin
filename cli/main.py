"""
CLI Main Entry Point

Main entry point for the AI Trading Agent CLI.
"""
import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

try:
    from rich.console import Console
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from config.agent_config import AgentConfig, TradingMode, LLMProvider, DEFAULT_CONFIG
from agent.core.agent import TradingAgent, AgentState
from agent.core.swing_agent import SwingTradingAgent, SwingAgentConfig
from agent.core.aggressive_agent import AggressiveTradingAgent, AggressiveAgentConfig
from agent.core.hindsight import HindsightAnalyzer, run_hindsight_analysis
from agent.core.trade_logger import TradeLogger
from cli.dashboard import Dashboard
from alerts.manager import AlertAction


def setup_logging(level: str = 'INFO', log_file: Optional[str] = None):
    """Configure logging"""
    import os

    handlers = []

    if RICH_AVAILABLE:
        handlers.append(RichHandler(
            rich_tracebacks=True,
            show_path=False,
        ))
    else:
        handlers.append(logging.StreamHandler())

    if log_file:
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        handlers.append(logging.FileHandler(log_file))
        print(f"📝 Logging to: {log_file}")

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )

    # Reduce noise from httpx (Alpaca client)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='AI Trading Agent - Day Trading Assistant',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.main --paper                    # Start in paper trading mode
  python -m cli.main --watch AAPL MSFT GOOGL   # Watch specific symbols
  python -m cli.main --dashboard               # Run with live dashboard
        """
    )

    parser.add_argument(
        '--paper',
        action='store_true',
        default=True,
        help='Use paper trading (default)'
    )

    parser.add_argument(
        '--live',
        action='store_true',
        help='Use live trading (requires confirmation)'
    )

    parser.add_argument(
        '--watch', '-w',
        nargs='+',
        help='Symbols to watch (overrides config)'
    )

    parser.add_argument(
        '--dashboard', '-d',
        action='store_true',
        help='Run with live terminal dashboard'
    )

    parser.add_argument(
        '--no-trade',
        action='store_true',
        help='Analysis only, no trade execution'
    )

    parser.add_argument(
        '--auto', '-a',
        action='store_true',
        help='Autonomous mode: auto-execute trades without confirmation, generate daily summary'
    )

    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level'
    )

    parser.add_argument(
        '--log-file',
        default='logs/agent.log',
        help='Log file path (default: logs/agent.log)'
    )

    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate configuration and exit'
    )

    parser.add_argument(
        '--claude',
        action='store_true',
        help='Use Claude API instead of local Ollama (costs money)'
    )

    parser.add_argument(
        '--ollama-model',
        default=None,
        help='Ollama model to use (default: llama3.1:8b)'
    )

    parser.add_argument(
        '--hindsight',
        action='store_true',
        help='Run hindsight analysis on yesterday\'s data and exit'
    )

    parser.add_argument(
        '--hindsight-days',
        type=int,
        default=1,
        help='Number of days back to analyze for hindsight (default: 1 = yesterday)'
    )

    parser.add_argument(
        '--swing',
        action='store_true',
        help='Use Swing Trading mode (mean reversion, multi-day holds) instead of day trading'
    )

    parser.add_argument(
        '--legacy',
        action='store_true',
        help='Use legacy day trading agent (NOT RECOMMENDED - use for testing only)'
    )

    return parser.parse_args()


async def run_agent(config: AgentConfig, use_dashboard: bool = False, analysis_only: bool = False, autonomous: bool = False):
    """Run the trading agent"""
    console = Console() if RICH_AVAILABLE else None
    agent = TradingAgent(config)
    dashboard = Dashboard(agent) if use_dashboard and not autonomous else None

    # Handle shutdown gracefully
    shutdown_event = asyncio.Event()

    def handle_shutdown(sig, frame):
        print("\nShutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Track trades for daily summary (autonomous mode)
    daily_trades = []

    try:
        # Start agent
        success = await agent.start()
        if not success:
            print("Failed to start agent. Check logs for details.")
            return

        mode_str = 'AUTONOMOUS PAPER' if autonomous else ('PAPER' if config.mode == TradingMode.PAPER else 'LIVE')
        print(f"Agent started in {mode_str} mode")

        # Show LLM provider status (compact)
        provider_info = agent.reasoning.get_provider_info()
        if provider_info['available']:
            print(f"🧠 {provider_info['provider']}: {provider_info['model']} ✅")
        else:
            print(f"🧠 {provider_info['provider']}: ❌ Not available")

        # Show account balance and holdings at startup
        try:
            account = await agent.alpaca_client.get_account()
            positions = await agent.alpaca_client.get_positions()

            print(f"\n💰 Account Summary:")
            print(f"   Equity:       ${account.equity:,.2f}")
            print(f"   Buying Power: ${account.buying_power:,.2f}")
            print(f"   Cash:         ${account.cash:,.2f}")

            if positions:
                total_value = sum(p.market_value for p in positions)
                total_pnl = sum(p.unrealized_pl for p in positions)
                pnl_sign = "+" if total_pnl >= 0 else ""
                print(f"\n📦 Current Holdings ({len(positions)} positions):")
                for p in positions:
                    pnl = p.unrealized_pl
                    pnl_pct = p.unrealized_plpc * 100
                    sign = "+" if pnl >= 0 else ""
                    print(f"   • {p.symbol}: {p.qty:.2f} shares @ ${p.current_price:.2f} ({sign}${pnl:.2f} / {sign}{pnl_pct:.1f}%)")
                print(f"   Total Value: ${total_value:,.2f} | Unrealized P&L: {pnl_sign}${total_pnl:.2f}")
            else:
                print(f"\n📦 No current holdings")
        except Exception as e:
            logging.warning(f"Could not fetch account info: {e}")

        print("")  # Empty line

        if config.watchlist:
            print(f"📋 Base watchlist: {', '.join(config.watchlist[:5])}{'...' if len(config.watchlist) > 5 else ''} ({len(config.watchlist)} stocks)")
        else:
            print("🚀 100% DYNAMIC MODE: No fixed watchlist - agent discovers ALL opportunities")

        if config.discovery.enabled:
            print(f"🔍 Discovery: scans every {config.discovery.scan_interval_minutes} min")
            print(f"   → Top gainers/losers, unusual volume, momentum stocks")
            print(f"   → Quality threshold: score ≥ {config.discovery.min_score}")
            print(f"   → No hard limit - includes all quality opportunities")

        if autonomous:
            print("🤖 AUTONOMOUS MODE: Trades will execute automatically")
            print("📊 Daily summary will be generated when market closes or on exit")

        # Run initial discovery scan to show user what we found
        if config.discovery.enabled:
            print("\n🔍 Running initial discovery scan...")
            try:
                discovered = await agent.discovery.discover(force=True)
                if discovered:
                    print(f"   Found {len(discovered)} interesting stocks:")
                    for stock in discovered[:5]:
                        print(f"   • {stock.symbol}: {stock.reason} ({stock.change_pct:+.1f}%)")
                    if len(discovered) > 5:
                        print(f"   ... and {len(discovered) - 5} more")

                    # Show dynamic watchlist
                    dynamic_watchlist = agent.get_dynamic_watchlist()
                    print(f"\n📋 Active watchlist: {len(dynamic_watchlist)} stocks")
                    print(f"   {', '.join(dynamic_watchlist)}")
                else:
                    print("   No additional stocks discovered (market may be closed)")
            except Exception as e:
                print(f"   Discovery scan failed: {e}")

        print("\nPress Ctrl+C to stop\n")

        if autonomous:
            # Autonomous mode - auto-execute trades
            await run_autonomous_loop(agent, shutdown_event, daily_trades, console, use_dashboard)
        else:
            # Manual mode
            agent.on_alert(lambda alert: handle_alert(alert, agent, console, analysis_only))

            if dashboard:
                await dashboard.run(shutdown_event)
            else:
                while not shutdown_event.is_set():
                    alert = agent.alert_manager.get_pending_alert()
                    if alert:
                        await handle_alert_interactive(alert, agent, console, analysis_only)
                    await asyncio.sleep(0.5)

    finally:
        # Generate daily summary if autonomous mode
        if autonomous and daily_trades:
            await generate_daily_summary(agent, daily_trades, console)

        # Show cost optimization stats
        try:
            cost_stats = agent.reasoning.get_cost_stats()
            print(f"\n📊 Session Stats:")

            # Ollama stats (local, free)
            if 'ollama_requests' in cost_stats and cost_stats['ollama_requests'] > 0:
                print(f"   🦙 Ollama: {cost_stats['ollama_requests']} requests, {cost_stats['ollama_tokens']} tokens")
                print(f"   ⏱️  Avg response: {cost_stats['ollama_avg_response_time']:.1f}s")
            else:
                print(f"   API calls: {cost_stats['api_calls_made']}")
        except Exception:
            pass

        await agent.stop()
        print("\nAgent stopped.")


async def run_autonomous_loop(agent: TradingAgent, shutdown_event: asyncio.Event, daily_trades: list, console, use_dashboard: bool):
    """Run agent in autonomous mode - auto-execute all trades"""
    from agent.core.summary import DailySummary

    summary_generator = DailySummary()
    last_market_check = None
    market_was_open = False
    last_discovery_count = len(agent.discovery._discovered)

    while not shutdown_event.is_set():
        try:
            # Check market status
            is_open = await agent.alpaca_client.is_market_open()

            # Market just closed - generate summary
            if market_was_open and not is_open:
                print("\n🔔 Market closed. Generating daily summary...")
                await generate_daily_summary(agent, daily_trades, console)
                daily_trades.clear()  # Reset for next day

            market_was_open = is_open

            if not is_open:
                # Wait and check again
                if console:
                    console.print("[dim]Market closed. Waiting...[/dim]", end="\r")
                await asyncio.sleep(60)
                continue

            # Check if discovery found new stocks
            current_discovery_count = len(agent.discovery._discovered)
            if current_discovery_count > last_discovery_count:
                new_count = current_discovery_count - last_discovery_count
                if console:
                    console.print(f"\n🔍 [cyan]Discovery found {new_count} new stocks![/]")
                    for stock in list(agent.discovery._discovered.values())[-new_count:]:
                        console.print(f"   • {stock.symbol}: {stock.reason} ({stock.change_pct:+.1f}%)")
                else:
                    print(f"\n🔍 Discovery found {new_count} new stocks!")
                last_discovery_count = current_discovery_count

            # Check for pending alerts
            alert = agent.alert_manager.get_pending_alert()
            if alert:
                # Auto-execute the trade
                opp = alert.opportunity

                if console:
                    console.print(f"\n🤖 [bold cyan]AUTO-EXECUTING:[/] {opp.action} {opp.symbol} @ ${opp.current_price:.2f}")
                    console.print(f"   Confidence: {opp.confidence*100:.0f}% | R:R {opp.risk_reward_ratio:.1f}:1")
                else:
                    print(f"\n🤖 AUTO-EXECUTING: {opp.action} {opp.symbol} @ ${opp.current_price:.2f}")

                # Execute trade
                result = await agent.handle_alert_response(alert, AlertAction.CONFIRM)

                trade_record = {
                    'timestamp': datetime.now(),
                    'symbol': opp.symbol,
                    'action': opp.action,
                    'price': opp.current_price,
                    'shares': opp.shares,
                    'value': opp.position_size,
                    'confidence': opp.confidence,
                    'reasoning': opp.reasoning,
                    'success': result.is_success if result else False,
                    'error': result.error_message if result and not result.is_success else None
                }
                daily_trades.append(trade_record)

                if result and result.is_success:
                    if console:
                        console.print(f"   ✅ [green]Trade executed successfully[/]")
                    else:
                        print(f"   ✅ Trade executed successfully")
                else:
                    error_msg = result.error_message if result else 'Unknown error'
                    if console:
                        console.print(f"   ❌ [red]Trade failed: {error_msg}[/]")
                    else:
                        print(f"   ❌ Trade failed: {error_msg}")

            await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Error in autonomous loop: {e}")
            await asyncio.sleep(5)


async def generate_daily_summary(agent: TradingAgent, daily_trades: list, console):
    """Generate and display daily summary"""
    from agent.core.summary import DailySummary

    summary_gen = DailySummary()

    # Get portfolio state - use async method directly since we're in async context
    try:
        portfolio = await agent.executor.get_position_summary()
    except Exception as e:
        logging.warning(f"Could not get portfolio for summary: {e}")
        portfolio = {}

    summary = summary_gen.generate(daily_trades, portfolio)

    if console and RICH_AVAILABLE:
        summary_gen.display_rich(summary, console)
    else:
        summary_gen.display_simple(summary)


async def handle_alert_interactive(alert, agent, console, analysis_only: bool):
    """Handle alert with interactive user input"""
    from alerts.formatters import AlertFormatter

    formatter = AlertFormatter(use_rich=RICH_AVAILABLE)
    formatter.display_alert(alert)

    if analysis_only:
        print("[Analysis Only Mode - Skipping trade execution]")
        agent.alert_manager.respond_to_alert(alert, AlertAction.SKIP, "Analysis only mode")
        return

    # Get user input
    while True:
        try:
            response = input("Action [c]onfirm / [r]eject / [m]ore info: ").strip().lower()

            if response in ['c', 'confirm']:
                result = await agent.handle_alert_response(alert, AlertAction.CONFIRM)
                if result and result.is_success:
                    formatter.format_confirmation(alert, AlertAction.CONFIRM)
                else:
                    print(f"Trade execution failed: {result.error_message if result else 'Unknown error'}")
                break

            elif response in ['r', 'reject']:
                agent.alert_manager.respond_to_alert(alert, AlertAction.REJECT)
                formatter.format_confirmation(alert, AlertAction.REJECT)
                break

            elif response in ['m', 'more']:
                print_more_info(alert)

            else:
                print("Invalid input. Enter 'c', 'r', or 'm'")

        except EOFError:
            agent.alert_manager.respond_to_alert(alert, AlertAction.SKIP, "EOF")
            break


def handle_alert(alert, agent, console, analysis_only: bool):
    """Callback handler for new alerts (non-interactive)"""
    if console:
        console.print(f"\n[bold yellow]New Alert:[/] {alert.opportunity.action} {alert.opportunity.symbol}")
    else:
        print(f"\nNew Alert: {alert.opportunity.action} {alert.opportunity.symbol}")


def print_more_info(alert):
    """Print detailed alert information"""
    opp = alert.opportunity

    print("\n" + "=" * 60)
    print("DETAILED ANALYSIS")
    print("=" * 60)

    print(f"\nSymbol: {opp.symbol}")
    print(f"Action: {opp.action}")
    print(f"Current Price: ${opp.current_price:.2f}")
    print(f"Target Price: ${opp.target_price:.2f}")
    print(f"Stop Loss: ${opp.stop_loss:.2f}")
    print(f"Position Size: ${opp.position_size:.2f} ({opp.shares:.4f} shares)")
    print(f"Confidence: {opp.confidence*100:.1f}%")
    print(f"Risk/Reward: {opp.risk_reward_ratio:.2f}:1")

    print(f"\nReasoning:")
    print(f"  {opp.reasoning}")

    if opp.similar_trades_win_rate:
        print(f"\nHistorical Similar Trades:")
        print(f"  Win Rate: {opp.similar_trades_win_rate*100:.1f}%")

    if opp.technical_signals:
        print(f"\nTechnical Signals:")
        for key, value in opp.technical_signals.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")

    if opp.market_context:
        print(f"\nMarket Context: {opp.market_context}")

    print("\n" + "=" * 60 + "\n")


async def run_hindsight_cli(days_back: int = 1):
    """
    Run hindsight analysis from CLI.
    Analyzes the specified number of days and prints a detailed report.
    """
    from alpaca.client import AlpacaClient
    from agent.core.layered_memory import LayeredMemorySystem

    print("\n" + "=" * 70)
    print("📊 HINDSIGHT ANALYSIS - Learn from Optimal Trading Scenarios")
    print("=" * 70 + "\n")

    # Initialize components
    client = AlpacaClient()
    analyzer = HindsightAnalyzer(client=client)
    trade_logger = TradeLogger(log_dir="logs/trades")
    memory_system = LayeredMemorySystem(memory_dir="data/memory")

    try:
        for i in range(days_back):
            date = datetime.now() - timedelta(days=i+1)
            print(f"\n🔍 Analyzing {date.strftime('%Y-%m-%d')}...\n")

            # Get agent's trades for that day
            agent_trades = trade_logger.get_trades_for_date(date)

            # Run analysis
            report = await analyzer.run_and_learn(
                memory_system=memory_system,
                date=date,
                agent_trades=agent_trades,
            )

            # Print formatted report
            print(analyzer.format_report(report))

        print("\n✅ Hindsight analysis complete!")
        print("   Patterns have been stored in memory for future learning.\n")

    except Exception as e:
        logging.error(f"Hindsight analysis failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")

    finally:
        await client.close()


def validate_config(config: AgentConfig) -> bool:
    """Validate configuration"""
    print("Validating configuration...")

    is_valid, errors = config.validate()

    if is_valid:
        print("[OK] Configuration is valid")
        print(f"  - Trading Mode: {'Paper' if config.mode == TradingMode.PAPER else 'Live'}")
        print(f"  - Watchlist: {len(config.watchlist)} symbols")
        print(f"  - Alpaca API: {'Configured' if config.alpaca.api_key else 'Not configured'}")
        print(f"  - LLM Provider: {config.llm_provider.value}")
        if config.llm_provider == LLMProvider.OLLAMA:
            print(f"    Model: {config.ollama.model}")
            print(f"    Cost: Free (local)")
        else:
            print(f"    Model: {config.claude.model}")
            print(f"    API: {'Configured' if config.claude.api_key else 'Not configured'}")
            print(f"    Cost: Paid (cloud)")
        return True
    else:
        print("[ERROR] Configuration errors:")
        for error in errors:
            print(f"  - {error}")
        return False


def run_cli():
    """Main entry point"""
    args = parse_args()

    # Setup logging
    setup_logging(args.log_level, args.log_file)

    # Build config
    config = AgentConfig()

    if args.live:
        # Require explicit confirmation for live trading
        confirm = input("WARNING: Live trading mode. Type 'CONFIRM' to proceed: ")
        if confirm != 'CONFIRM':
            print("Aborted.")
            sys.exit(1)
        config.mode = TradingMode.LIVE
    else:
        config.mode = TradingMode.PAPER

    if args.watch:
        config.watchlist = args.watch

    # LLM provider selection (quiet - will show status after agent starts)
    if args.claude:
        config.llm_provider = LLMProvider.CLAUDE
    else:
        config.llm_provider = LLMProvider.OLLAMA
        if args.ollama_model:
            config.ollama.model = args.ollama_model

    # Validate only?
    if args.validate:
        success = validate_config(config)
        sys.exit(0 if success else 1)

    # Run hindsight analysis?
    if args.hindsight:
        try:
            asyncio.run(run_hindsight_cli(args.hindsight_days))
        except KeyboardInterrupt:
            print("\nInterrupted")
        sys.exit(0)

    # Run swing trading agent?
    if args.swing:
        print("=" * 60)
        print("🔄 SWING TRADING MODE")
        print("=" * 60)
        print("Strategy: Mean Reversion (RSI + Bollinger Bands)")
        print("Hold time: 1-5 days")
        print("Entry: End of day analysis")
        print("Exit: Intraday stop loss / take profit monitoring")
        print("=" * 60)

        try:
            swing_agent = SwingTradingAgent(config)
            asyncio.run(swing_agent.start())
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
        sys.exit(0)

    # Run legacy day trading agent (only if explicitly requested)
    if args.legacy:
        print("⚠️  WARNING: Running LEGACY agent (not optimized)")
        print("   Consider using default aggressive agent instead")
        print("=" * 60)
        try:
            asyncio.run(run_agent(
                config,
                use_dashboard=args.dashboard,
                analysis_only=args.no_trade,
                autonomous=args.auto,
            ))
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        except Exception as e:
            logging.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)
        sys.exit(0)

    # Run aggressive dip buyer agent (DEFAULT)
    # Create agent first to get config
    print("📝 Initializing Aggressive Trading Agent...")
    aggressive_agent = AggressiveTradingAgent(config)
    print("✅ Agent object created")
    agent_cfg = aggressive_agent.agent_config

    print("=" * 60)
    print("🚀 AGGRESSIVE DIP BUYER (Optimized Strategy)")
    print("=" * 60)
    print("Performance: +199.9% (12-month backtest) | +16.7% monthly avg")
    print(f"Symbols: {', '.join(agent_cfg.symbols)}")
    print(f"Position size: {agent_cfg.position_size_pct:.0%} per trade | Max positions: {agent_cfg.max_positions}")
    print(f"Stop loss: {agent_cfg.stop_loss_pct:.0%} | Trailing: {agent_cfg.trailing_stop_pct:.0%} | Take profit: {agent_cfg.take_profit_pct:.0%}")
    print(f"Entry: Daily at {agent_cfg.entry_check_time} ET (after red day + volatility)")
    if agent_cfg.use_ai_filter and aggressive_agent.groq_client:
        print(f"🤖 AI Filter: ON (Groq {aggressive_agent.groq_client.MODEL}, min confidence: {agent_cfg.ai_min_confidence:.0%})")
    else:
        print("🤖 AI Filter: OFF (rule-based only)")
    print("=" * 60)
    print("🚀 Starting agent event loop...")

    try:
        import os
        port = int(os.getenv("PORT", 0))
        if port:
            # Running on a platform that exposes HTTP (Render Web Service).
            # Start a minimal health server alongside the agent so the platform
            # doesn't consider the process idle and spin it down.
            asyncio.run(_run_with_health_server(aggressive_agent, port))
        else:
            asyncio.run(aggressive_agent.start())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


async def _run_with_health_server(agent, port: int):
    """Run the trading agent alongside a minimal HTTP server.

    Serves the log viewer frontend at / and a health endpoint at /health.
    Supabase credentials are injected from env vars so the HTML doesn't need
    to be edited manually before deploy.

    Used on platforms like Render Web Service where PORT is injected.
    UptimeRobot pings /health every 5 min to prevent the free tier from sleeping.
    """
    import os
    from pathlib import Path
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse

    health_app = FastAPI(docs_url=None, redoc_url=None)

    # Read frontend/index.html once at startup and inject credentials from env.
    # Placeholders in the HTML: 'https://YOUR_PROJECT_ID.supabase.co' and 'YOUR_ANON_KEY'
    _html: str | None = None
    _frontend = Path(__file__).parent.parent / "frontend" / "index.html"
    try:
        raw = _frontend.read_text()
        _url  = os.getenv("SUPABASE_URL", "")
        _anon = os.getenv("SUPABASE_ANON_KEY", "")
        _html = (
            raw
            .replace("'https://YOUR_PROJECT_ID.supabase.co'", f"'{_url}'")
            .replace("'YOUR_ANON_KEY'", f"'{_anon}'")
        )
    except Exception as exc:
        logging.warning(f"Could not load frontend/index.html: {exc}")

    @health_app.get("/health")
    async def health():
        return {"status": "ok"}

    @health_app.head("/health")
    async def health_head():
        from fastapi.responses import Response
        return Response()

    @health_app.get("/")
    async def root():
        if _html:
            return HTMLResponse(_html)
        return HTMLResponse("<h1>projectin agent running</h1>")

    server_config = uvicorn.Config(
        health_app,
        host="0.0.0.0",
        port=port,
        log_level="error",
    )
    server = uvicorn.Server(server_config)

    print(f"🌐 Server listening on port {port} (frontend + /health)")
    await asyncio.gather(server.serve(), agent.start())


if __name__ == '__main__':
    run_cli()

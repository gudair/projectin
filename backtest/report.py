"""
Report Generator for Backtesting

Generates detailed reports comparing agent performance vs optimal.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from backtest.portfolio_tracker import PortfolioTracker

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates comprehensive backtest reports.
    """

    def __init__(
        self,
        results: Dict[str, Any],
        portfolio: PortfolioTracker,
        decisions: List[Dict],
        output_dir: str = "backtest/reports",
    ):
        self.results = results
        self.portfolio = portfolio
        self.decisions = decisions
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_summary(self) -> str:
        """Generate a text summary of the backtest"""
        r = self.results
        agent = r.get('agent_performance', {})
        optimal = r.get('optimal_performance', {})
        period = r.get('period', {})
        config = r.get('config', {})
        ollama_stats = r.get('ollama_stats')

        lines = [
            "=" * 70,
            "BACKTEST REPORT",
            "=" * 70,
            "",
            "CONFIGURATION",
            "-" * 40,
            f"Period: {period.get('start', 'N/A')} to {period.get('end', 'N/A')}",
            f"Trading Days: {period.get('trading_days', 0)}",
            f"Initial Capital: ${config.get('initial_capital', 0):,.2f}",
            f"Ollama Analysis: {'Enabled' if config.get('use_ollama') else 'Disabled'}",
            "",
            "AGENT PERFORMANCE",
            "-" * 40,
            f"Final Equity: ${agent.get('final_equity', 0):,.2f}",
            f"Total Return: ${agent.get('total_return', 0):+,.2f} ({agent.get('total_return_pct', 0):+.2f}%)",
            f"Total Trades: {agent.get('total_trades', 0)}",
            f"Winning Trades: {agent.get('winning_trades', 0)}",
            f"Losing Trades: {agent.get('losing_trades', 0)}",
            f"Win Rate: {agent.get('win_rate', 0):.1f}%",
            f"Profit Factor: {agent.get('profit_factor', 0):.2f}",
            f"Max Drawdown: {agent.get('max_drawdown_pct', 0):.2f}%",
            f"Avg Daily P&L: ${agent.get('avg_daily_pnl', 0):+,.2f}",
            f"Avg Hold Duration: {agent.get('avg_hold_duration_minutes', 0):.0f} min",
        ]

        # Add Ollama stats if enabled
        if ollama_stats:
            lines.extend([
                "",
                "OLLAMA ANALYSIS BREAKDOWN",
                "-" * 40,
                f"Total Momentum Signals: {ollama_stats.get('total_signals', 0)}",
                f"Ollama Calls Made: {ollama_stats.get('ollama_calls', 0)}",
                f"Ollama No Response: {ollama_stats.get('ollama_no_response', 0)}",
                f"Rejected - HOLD: {ollama_stats.get('ollama_hold', 0)}",
                f"Rejected - SELL/SKIP: {ollama_stats.get('ollama_sell', 0)}",
                f"Rejected - BUY Low Conf (<70%): {ollama_stats.get('ollama_buy_low_conf', 0)}",
                f"APPROVED - BUY (conf>=70%): {ollama_stats.get('ollama_buy_approved', 0)}",
            ])

            # Show sample rejection reasons
            rejected_reasons = ollama_stats.get('rejected_reasons', [])
            if rejected_reasons:
                lines.extend([
                    "",
                    "SAMPLE REJECTION REASONS (first 10):",
                ])
                for i, reason in enumerate(rejected_reasons[:10], 1):
                    lines.append(f"  {i}. {reason}")

        lines.extend([
            "",
            "OPTIMAL BENCHMARK (Hindsight)",
            "-" * 40,
            f"Realistic Return: ${optimal.get('total_return', 0):+,.2f} ({optimal.get('realistic_return_pct', 0):+.2f}%)",
            f"Theoretical Max Trades: {optimal.get('theoretical_max_trades', 0)}",
            f"Avg Gain per Optimal Trade: {optimal.get('avg_gain_per_optimal_trade', 0):.2f}%",
            "",
            "EFFICIENCY",
            "-" * 40,
            f"Agent vs Optimal: {r.get('efficiency_pct', 0):.1f}%",
            "",
            "TRADE BREAKDOWN",
            "-" * 40,
        ])

        # Add trade breakdown by symbol
        symbol_stats = self._get_symbol_stats()
        for symbol, stats in sorted(symbol_stats.items(), key=lambda x: x[1]['pnl'], reverse=True)[:10]:
            lines.append(
                f"  {symbol}: {stats['trades']} trades, ${stats['pnl']:+,.2f} "
                f"({stats['win_rate']:.0f}% win rate)"
            )

        lines.extend([
            "",
            "DAILY PERFORMANCE",
            "-" * 40,
        ])

        # Add daily stats summary
        best_day = max(self.portfolio.daily_stats, key=lambda x: x.pnl, default=None)
        worst_day = min(self.portfolio.daily_stats, key=lambda x: x.pnl, default=None)

        if best_day:
            lines.append(f"  Best Day: {best_day.date.date()} (${best_day.pnl:+,.2f})")
        if worst_day:
            lines.append(f"  Worst Day: {worst_day.date.date()} (${worst_day.pnl:+,.2f})")

        profitable_days = sum(1 for d in self.portfolio.daily_stats if d.pnl > 0)
        total_days = len(self.portfolio.daily_stats)
        if total_days > 0:
            lines.append(f"  Profitable Days: {profitable_days}/{total_days} ({profitable_days/total_days*100:.0f}%)")

        lines.extend([
            "",
            "=" * 70,
            f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "=" * 70,
        ])

        return "\n".join(lines)

    def _get_symbol_stats(self) -> Dict[str, Dict]:
        """Get performance breakdown by symbol"""
        symbol_stats = {}

        for trade in self.portfolio.trades:
            if trade.side != 'sell':
                continue

            symbol = trade.symbol
            if symbol not in symbol_stats:
                symbol_stats[symbol] = {
                    'trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'pnl': 0,
                    'total_volume': 0,
                }

            symbol_stats[symbol]['trades'] += 1
            symbol_stats[symbol]['pnl'] += trade.pnl
            symbol_stats[symbol]['total_volume'] += trade.value

            if trade.pnl > 0:
                symbol_stats[symbol]['wins'] += 1
            else:
                symbol_stats[symbol]['losses'] += 1

        # Calculate win rates
        for symbol in symbol_stats:
            total = symbol_stats[symbol]['trades']
            wins = symbol_stats[symbol]['wins']
            symbol_stats[symbol]['win_rate'] = wins / total * 100 if total > 0 else 0

        return symbol_stats

    def generate_detailed_report(self) -> Dict[str, Any]:
        """Generate a detailed JSON report"""
        return {
            'summary': self.results,
            'daily_stats': [
                {
                    'date': d.date.isoformat(),
                    'starting_equity': d.starting_equity,
                    'ending_equity': d.ending_equity,
                    'pnl': d.pnl,
                    'pnl_pct': d.pnl_pct,
                    'trades': d.trades_count,
                    'winning_trades': d.winning_trades,
                    'losing_trades': d.losing_trades,
                    'max_drawdown': d.max_drawdown,
                }
                for d in self.portfolio.daily_stats
            ],
            'trades': self.portfolio.get_trade_log(),
            'decisions': self.decisions,
            'symbol_breakdown': self._get_symbol_stats(),
        }

    def save_report(self) -> str:
        """Save reports to files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Save text summary
        summary_path = self.output_dir / f"backtest_summary_{timestamp}.txt"
        with open(summary_path, 'w') as f:
            f.write(self.generate_summary())

        # Save detailed JSON report
        json_path = self.output_dir / f"backtest_detailed_{timestamp}.json"
        with open(json_path, 'w') as f:
            json.dump(self.generate_detailed_report(), f, indent=2, default=str)

        logger.info(f"Reports saved to {self.output_dir}")
        logger.info(f"  Summary: {summary_path.name}")
        logger.info(f"  Detailed: {json_path.name}")

        # Print summary to console
        print("\n" + self.generate_summary())

        return str(summary_path)

    def print_summary(self):
        """Print summary to console"""
        print(self.generate_summary())

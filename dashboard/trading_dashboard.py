import dash
from dash import dcc, html, Input, Output, State, dash_table
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

# Add parent directory to path to import our modules
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from portfolio.portfolio_manager import PortfolioManager
from signals.signal_generator import SignalGenerator
from data.collectors.market_data import MarketDataCollector
from data.collectors.news_collector import NewsCollector
from config.settings import DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_DEBUG

class TradingDashboard:
    def __init__(self):
        self.app = dash.Dash(__name__)
        self.portfolio_manager = PortfolioManager()
        self.signal_generator = SignalGenerator()
        self.market_data = MarketDataCollector()
        self.news_collector = NewsCollector()
        self.logger = logging.getLogger(__name__)

        # Setup layout
        self.setup_layout()
        self.setup_callbacks()

    def setup_layout(self):
        """Setup the dashboard layout"""
        self.app.layout = html.Div([
            # Header
            html.Div([
                html.H1("🚀 Trading Simulator Dashboard", className="text-center mb-4"),
                html.P("Real-time portfolio monitoring and trading recommendations",
                       className="text-center text-muted"),
                html.Hr()
            ], className="container-fluid"),

            # Auto-refresh component
            dcc.Interval(
                id='interval-component',
                interval=30*1000,  # Update every 30 seconds
                n_intervals=0
            ),

            # Main content
            html.Div([
                # Portfolio Overview Row
                html.Div([
                    html.H3("📊 Portfolio Overview"),
                    html.Div(id="portfolio-overview", children=[]),
                ], className="mb-4"),

                # Charts Row
                html.Div([
                    html.Div([
                        html.H4("Portfolio Performance"),
                        dcc.Graph(id="portfolio-chart")
                    ], className="col-md-6"),

                    html.Div([
                        html.H4("Position Breakdown"),
                        dcc.Graph(id="positions-chart")
                    ], className="col-md-6"),
                ], className="row mb-4"),

                # Trading Signals Row
                html.Div([
                    html.H3("🎯 Trading Signals & Recommendations"),
                    html.Div(id="trading-signals", children=[]),
                ], className="mb-4"),

                # Recent News Row
                html.Div([
                    html.H3("📰 Market News & Sentiment"),
                    html.Div(id="recent-news", children=[]),
                ], className="mb-4"),

                # Trade History Row
                html.Div([
                    html.H3("📈 Trade History"),
                    html.Div(id="trade-history", children=[]),
                ], className="mb-4"),

            ], className="container-fluid"),

            # Footer
            html.Div([
                html.Hr(),
                html.P("Trading Simulator - Educational Purposes Only",
                       className="text-center text-muted small"),
                html.P(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                       className="text-center text-muted small"),
            ], className="container-fluid mt-4")

        ], style={'backgroundColor': '#f8f9fa'})

    def setup_callbacks(self):
        """Setup dashboard callbacks for interactivity"""

        @self.app.callback(
            [Output('portfolio-overview', 'children'),
             Output('portfolio-chart', 'figure'),
             Output('positions-chart', 'figure'),
             Output('trading-signals', 'children'),
             Output('recent-news', 'children'),
             Output('trade-history', 'children')],
            [Input('interval-component', 'n_intervals')]
        )
        def update_dashboard(n):
            try:
                # Get portfolio data
                portfolio_summary = self.portfolio_manager.get_portfolio_summary()

                # Update portfolio with current prices
                market_snapshot = self.market_data.get_market_snapshot()
                self.portfolio_manager.update_positions(market_snapshot)
                self.portfolio_manager.update_daily_pnl()

                # Generate signals
                signals = self.signal_generator.generate_watchlist_signals()
                top_opportunities = self.signal_generator.get_top_opportunities(signals, limit=5)

                # Get news
                news_articles = []
                for symbol in list(portfolio_summary['positions'].keys())[:3]:  # Top 3 positions
                    symbol_news = self.news_collector.get_stock_news(symbol, hours_back=12)
                    news_articles.extend(symbol_news[:5])  # Top 5 per symbol

                # Generate components
                portfolio_overview = self._create_portfolio_overview(portfolio_summary)
                portfolio_chart = self._create_portfolio_chart()
                positions_chart = self._create_positions_chart(portfolio_summary)
                signals_component = self._create_signals_component(top_opportunities)
                news_component = self._create_news_component(news_articles)
                history_component = self._create_trade_history_component()

                return (portfolio_overview, portfolio_chart, positions_chart,
                       signals_component, news_component, history_component)

            except Exception as e:
                self.logger.error(f"Error updating dashboard: {e}")
                error_msg = html.Div([
                    html.H4("Error updating dashboard", className="text-danger"),
                    html.P(f"Error: {str(e)}", className="text-muted")
                ])
                empty_fig = go.Figure()
                return error_msg, empty_fig, empty_fig, error_msg, error_msg, error_msg

    def _create_portfolio_overview(self, summary: dict) -> html.Div:
        """Create portfolio overview cards"""
        return html.Div([
            html.Div([
                # Portfolio Value Card
                html.Div([
                    html.Div([
                        html.H4(f"${summary['total_value']:.2f}", className="card-title text-primary"),
                        html.P("Total Portfolio Value", className="card-text"),
                    ], className="card-body")
                ], className="card"),
            ], className="col-md-3"),

            html.Div([
                # Daily P&L Card
                pnl_class = "text-success" if summary['daily_pnl'] >= 0 else "text-danger"
                pnl_icon = "📈" if summary['daily_pnl'] >= 0 else "📉"
                html.Div([
                    html.Div([
                        html.H4(f"{pnl_icon} ${summary['daily_pnl']:.2f}", className=f"card-title {pnl_class}"),
                        html.P("Daily P&L", className="card-text"),
                    ], className="card-body")
                ], className="card"),
            ], className="col-md-3"),

            html.Div([
                # Total Return Card
                return_class = "text-success" if summary['total_return_percent'] >= 0 else "text-danger"
                html.Div([
                    html.Div([
                        html.H4(f"{summary['total_return_percent']:.2f}%", className=f"card-title {return_class}"),
                        html.P("Total Return", className="card-text"),
                    ], className="card-body")
                ], className="card"),
            ], className="col-md-3"),

            html.Div([
                # Cash Available Card
                html.Div([
                    html.Div([
                        html.H4(f"${summary['cash']:.2f}", className="card-title text-info"),
                        html.P("Cash Available", className="card-text"),
                    ], className="card-body")
                ], className="card"),
            ], className="col-md-3"),

        ], className="row")

    def _create_portfolio_chart(self) -> go.Figure:
        """Create portfolio performance chart"""
        try:
            # Get daily P&L history
            daily_history = self.portfolio_manager.daily_pnl_history

            if not daily_history:
                # Create dummy data if no history
                fig = go.Figure()
                fig.add_annotation(
                    text="No historical data available yet",
                    x=0.5, y=0.5,
                    xref="paper", yref="paper",
                    showarrow=False
                )
                return fig

            # Convert to DataFrame
            df = pd.DataFrame(daily_history)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')

            # Calculate cumulative returns
            df['cumulative_return'] = ((df['portfolio_value'] / 200) - 1) * 100

            # Create chart
            fig = go.Figure()

            # Portfolio value line
            fig.add_trace(go.Scatter(
                x=df['date'],
                y=df['portfolio_value'],
                mode='lines+markers',
                name='Portfolio Value',
                line=dict(color='#2E86C1', width=3),
                hovertemplate='Date: %{x}<br>Value: $%{y:.2f}<extra></extra>'
            ))

            # Add benchmark line (initial value)
            fig.add_hline(
                y=200,
                line_dash="dash",
                line_color="gray",
                annotation_text="Initial Value ($200)"
            )

            fig.update_layout(
                title="Portfolio Performance Over Time",
                xaxis_title="Date",
                yaxis_title="Portfolio Value ($)",
                hovermode='x unified',
                showlegend=True,
                height=400
            )

            return fig

        except Exception as e:
            self.logger.error(f"Error creating portfolio chart: {e}")
            return go.Figure()

    def _create_positions_chart(self, summary: dict) -> go.Figure:
        """Create positions breakdown pie chart"""
        try:
            positions = summary['positions']

            if not positions:
                fig = go.Figure()
                fig.add_annotation(
                    text="No positions available",
                    x=0.5, y=0.5,
                    xref="paper", yref="paper",
                    showarrow=False
                )
                return fig

            # Prepare data
            symbols = list(positions.keys())
            values = [pos['current_value'] for pos in positions.values()]

            # Add cash if available
            if summary['cash'] > 0:
                symbols.append('CASH')
                values.append(summary['cash'])

            # Create pie chart
            fig = go.Figure(data=[go.Pie(
                labels=symbols,
                values=values,
                hovertemplate='%{label}<br>Value: $%{value:.2f}<br>Percentage: %{percent}<extra></extra>',
                textinfo='label+percent',
                textposition='inside'
            )])

            fig.update_layout(
                title="Portfolio Allocation",
                height=400,
                showlegend=True
            )

            return fig

        except Exception as e:
            self.logger.error(f"Error creating positions chart: {e}")
            return go.Figure()

    def _create_signals_component(self, opportunities: list) -> html.Div:
        """Create trading signals component"""
        if not opportunities:
            return html.Div([
                html.P("No trading opportunities found at this time.", className="text-muted")
            ])

        signal_cards = []
        for opp in opportunities:
            # Determine card color based on signal
            if 'buy' in opp.signal_type.value.lower():
                card_class = "border-success"
                header_class = "bg-success text-white"
                signal_icon = "📈"
            elif 'sell' in opp.signal_type.value.lower():
                card_class = "border-danger"
                header_class = "bg-danger text-white"
                signal_icon = "📉"
            else:
                card_class = "border-warning"
                header_class = "bg-warning"
                signal_icon = "⚠️"

            card = html.Div([
                html.Div([
                    html.H5(f"{signal_icon} {opp.symbol}", className="mb-0")
                ], className=f"card-header {header_class}"),

                html.Div([
                    html.P([
                        html.Strong("Signal: "), opp.signal_type.value.replace('_', ' ').title()
                    ], className="mb-1"),
                    html.P([
                        html.Strong("Confidence: "), f"{opp.confidence:.1%}"
                    ], className="mb-1"),
                    html.P([
                        html.Strong("Strength: "), f"{opp.strength:.2f}/1.0"
                    ], className="mb-1"),
                    html.P([
                        html.Strong("Target: "), f"${opp.target_price:.2f}" if opp.target_price else "N/A"
                    ], className="mb-1"),
                    html.P([
                        html.Strong("Stop Loss: "), f"${opp.stop_loss:.2f}" if opp.stop_loss else "N/A"
                    ], className="mb-2"),
                    html.P([
                        html.Strong("Reasoning: "),
                        html.Small(opp.reasoning, className="text-muted")
                    ], className="mb-0"),
                ], className="card-body")
            ], className=f"card {card_class} mb-2")

            signal_cards.append(html.Div(card, className="col-md-6 col-lg-4"))

        return html.Div(signal_cards, className="row")

    def _create_news_component(self, news_articles: list) -> html.Div:
        """Create news component"""
        if not news_articles:
            return html.Div([
                html.P("No recent news available.", className="text-muted")
            ])

        news_items = []
        for article in news_articles[:10]:  # Show top 10
            news_item = html.Div([
                html.H6([
                    html.A(article['title'], href=article['url'], target="_blank", className="text-decoration-none"),
                    html.Small(f" - {article['source']}", className="text-muted ms-2")
                ], className="mb-1"),
                html.P(article['description'][:200] + "..." if len(article['description']) > 200 else article['description'],
                       className="mb-1 text-muted small"),
                html.P([
                    html.Small([
                        html.Strong(f"{article['symbol']} "),
                        f"• {article['published_at'].strftime('%Y-%m-%d %H:%M')}"
                    ], className="text-muted")
                ], className="mb-2"),
                html.Hr()
            ])
            news_items.append(news_item)

        return html.Div(news_items)

    def _create_trade_history_component(self) -> html.Div:
        """Create trade history component"""
        trade_history = self.portfolio_manager.trade_history[-20:]  # Last 20 trades

        if not trade_history:
            return html.Div([
                html.P("No trades executed yet.", className="text-muted")
            ])

        # Convert to DataFrame for table
        trades_data = []
        for trade in reversed(trade_history):  # Most recent first
            trades_data.append({
                'Date': trade.timestamp.strftime('%Y-%m-%d %H:%M'),
                'Symbol': trade.symbol,
                'Side': trade.side.upper(),
                'Shares': f"{trade.shares:.6f}",
                'Price': f"${trade.price:.2f}",
                'Value': f"${trade.shares * trade.price:.2f}",
                'Commission': f"${trade.commission:.2f}",
                'Reason': trade.reason
            })

        if not trades_data:
            return html.Div([
                html.P("No trades available.", className="text-muted")
            ])

        # Create table
        table = dash_table.DataTable(
            data=trades_data,
            columns=[{"name": col, "id": col} for col in trades_data[0].keys()],
            style_cell={'textAlign': 'left', 'fontSize': '12px'},
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Side} = BUY'},
                    'backgroundColor': '#d4edda',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Side} = SELL'},
                    'backgroundColor': '#f8d7da',
                    'color': 'black',
                }
            ],
            style_header={'backgroundColor': '#343a40', 'color': 'white', 'fontWeight': 'bold'},
            page_size=10
        )

        return html.Div([table])

    def run(self):
        """Run the dashboard"""
        self.logger.info(f"Starting dashboard on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        self.app.run_server(
            host=DASHBOARD_HOST,
            port=DASHBOARD_PORT,
            debug=DASHBOARD_DEBUG
        )

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and run dashboard
    dashboard = TradingDashboard()
    dashboard.run()
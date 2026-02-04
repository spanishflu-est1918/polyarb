#!/usr/bin/env python3
"""
Backtesting Engine
No bullshit metrics. Realistic assumptions. Tail risk awareness.
"""

import sqlite3
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


@dataclass
class Trade:
    """Single trade record."""
    timestamp: str
    market_id: str
    side: str  # 'buy_yes', 'buy_no', 'sell_yes', 'sell_no'
    price: float
    size: float
    fees: float = 0.0
    slippage: float = 0.0
    
    @property
    def cost(self) -> float:
        return (self.price * self.size) + self.fees + self.slippage
    
    @property
    def effective_price(self) -> float:
        return (self.cost) / self.size if self.size > 0 else self.price


@dataclass 
class Position:
    """Open position."""
    market_id: str
    side: str  # 'yes' or 'no'
    size: float
    avg_price: float
    opened_at: str


@dataclass
class BacktestResult:
    """Complete backtest results with bullshit detection."""
    
    # Basic metrics
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    
    # Risk metrics (the important stuff)
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: int  # in periods
    calmar_ratio: float
    
    # Tail risk (CRITICAL)
    var_95: float  # Value at Risk 95%
    cvar_95: float  # Conditional VaR (Expected Shortfall)
    worst_trade: float
    worst_day: float
    
    # Reality checks
    avg_trade_duration: float
    profit_factor: float
    win_rate: float
    avg_win: float
    avg_loss: float
    
    # Bullshit detection
    is_curve_fitted: bool  # Too good to be true?
    pennies_steamroller: bool  # Small wins, huge losses?
    sufficient_trades: bool  # Statistically significant?
    
    trades: List[Trade]
    equity_curve: pd.Series
    
    def __str__(self):
        status = "✅ VALID" if self.is_valid() else "❌ BULLSHIT"
        
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║  BACKTEST RESULTS - {status}
╠══════════════════════════════════════════════════════════════════╣
║  RETURNS
║  ├─ Total Return: {self.total_return*100:+.2f}%
║  ├─ Sharpe Ratio: {self.sharpe_ratio:.2f}
║  ├─ Sortino Ratio: {self.sortino_ratio:.2f}
║  └─ Calmar Ratio: {self.calmar_ratio:.2f}
╠══════════════════════════════════════════════════════════════════╣
║  RISK (THIS IS WHAT MATTERS)
║  ├─ Max Drawdown: {self.max_drawdown*100:.2f}%
║  ├─ Max DD Duration: {self.max_drawdown_duration} periods
║  ├─ VaR 95%: {self.var_95*100:.2f}%
║  ├─ CVaR 95%: {self.cvar_95*100:.2f}%
║  ├─ Worst Trade: {self.worst_trade*100:.2f}%
║  └─ Worst Day: {self.worst_day*100:.2f}%
╠══════════════════════════════════════════════════════════════════╣
║  TRADE STATS
║  ├─ Total Trades: {self.total_trades}
║  ├─ Win Rate: {self.win_rate*100:.1f}%
║  ├─ Profit Factor: {self.profit_factor:.2f}
║  ├─ Avg Win: {self.avg_win*100:+.2f}%
║  └─ Avg Loss: {self.avg_loss*100:.2f}%
╠══════════════════════════════════════════════════════════════════╣
║  BULLSHIT DETECTION
║  ├─ Curve Fitted: {"⚠️ YES" if self.is_curve_fitted else "✓ NO"}
║  ├─ Pennies/Steamroller: {"⚠️ YES" if self.pennies_steamroller else "✓ NO"}
║  └─ Sufficient Trades: {"✓ YES" if self.sufficient_trades else "⚠️ NO"}
╚══════════════════════════════════════════════════════════════════╝
"""
    
    def is_valid(self) -> bool:
        """Is this strategy actually tradeable?"""
        return (
            not self.is_curve_fitted and
            not self.pennies_steamroller and
            self.sufficient_trades and
            self.sharpe_ratio > 0.5 and
            self.max_drawdown > -0.50 and  # Not losing more than 50%
            self.profit_factor > 1.0
        )


class BacktestEngine:
    """
    Realistic backtesting with proper assumptions.
    
    Key principles:
    - Include realistic slippage
    - Include fees
    - No lookahead bias
    - Proper position sizing
    - Tail risk awareness
    """
    
    def __init__(
        self,
        initial_capital: float = 10000,
        fee_rate: float = 0.01,  # 1% Polymarket fee
        slippage_rate: float = 0.005,  # 0.5% slippage assumption
        max_position_pct: float = 0.1  # Max 10% of capital per position
    ):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.max_position_pct = max_position_pct
        
        self.capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_history: List[float] = [initial_capital]
        
    def load_data(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """Load price data from database."""
        conn = sqlite3.connect(DB_PATH)
        
        query = "SELECT * FROM price_snapshots"
        conditions = []
        
        if start_date:
            conditions.append(f"timestamp >= '{start_date}'")
        if end_date:
            conditions.append(f"timestamp <= '{end_date}'")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp"
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def execute_trade(
        self, 
        timestamp: str,
        market_id: str,
        side: str,
        price: float,
        size_usd: float
    ) -> Optional[Trade]:
        """Execute a trade with realistic costs."""
        
        # Apply slippage (worse price)
        if 'buy' in side:
            effective_price = price * (1 + self.slippage_rate)
        else:
            effective_price = price * (1 - self.slippage_rate)
        
        # Calculate fees
        fees = size_usd * self.fee_rate
        
        # Check capital
        total_cost = size_usd + fees
        if total_cost > self.capital:
            return None  # Insufficient capital
        
        # Create trade
        shares = size_usd / effective_price
        trade = Trade(
            timestamp=timestamp,
            market_id=market_id,
            side=side,
            price=price,
            size=shares,
            fees=fees,
            slippage=abs(effective_price - price) * shares
        )
        
        # Update capital
        if 'buy' in side:
            self.capital -= total_cost
        else:
            self.capital += size_usd - fees
        
        self.trades.append(trade)
        self.equity_history.append(self.capital)
        
        return trade
    
    def calculate_results(self) -> BacktestResult:
        """Calculate comprehensive backtest results."""
        
        if len(self.trades) == 0:
            return self._empty_result()
        
        equity = pd.Series(self.equity_history)
        returns = equity.pct_change().dropna()
        
        # Basic metrics
        total_return = (equity.iloc[-1] / equity.iloc[0]) - 1
        
        # Trade P&L
        trade_returns = []
        for i, trade in enumerate(self.trades):
            if i > 0:
                pnl = (self.equity_history[i+1] - self.equity_history[i]) / self.equity_history[i]
                trade_returns.append(pnl)
        
        trade_returns = pd.Series(trade_returns) if trade_returns else pd.Series([0])
        
        winning = trade_returns[trade_returns > 0]
        losing = trade_returns[trade_returns < 0]
        
        # Risk metrics
        sharpe = self._sharpe_ratio(returns)
        sortino = self._sortino_ratio(returns)
        max_dd, max_dd_duration = self._max_drawdown(equity)
        calmar = total_return / abs(max_dd) if max_dd != 0 else 0
        
        # Tail risk
        var_95 = self._var(returns, 0.95)
        cvar_95 = self._cvar(returns, 0.95)
        worst_trade = trade_returns.min() if len(trade_returns) > 0 else 0
        
        daily_returns = returns.resample('D').sum() if hasattr(returns.index, 'freq') else returns
        worst_day = daily_returns.min() if len(daily_returns) > 0 else 0
        
        # Win/loss metrics
        win_rate = len(winning) / len(trade_returns) if len(trade_returns) > 0 else 0
        avg_win = winning.mean() if len(winning) > 0 else 0
        avg_loss = losing.mean() if len(losing) > 0 else 0
        
        gross_profit = winning.sum() if len(winning) > 0 else 0
        gross_loss = abs(losing.sum()) if len(losing) > 0 else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # BULLSHIT DETECTION
        
        # 1. Curve fitting detection (Sharpe > 3 is suspicious)
        is_curve_fitted = sharpe > 3.0 or (win_rate > 0.8 and len(self.trades) < 100)
        
        # 2. Pennies in front of steamroller
        # High win rate but avg_loss >> avg_win
        if avg_win != 0:
            loss_to_win_ratio = abs(avg_loss / avg_win)
            pennies_steamroller = win_rate > 0.7 and loss_to_win_ratio > 5
        else:
            pennies_steamroller = False
        
        # 3. Sufficient trades for statistical significance
        sufficient_trades = len(self.trades) >= 30
        
        return BacktestResult(
            total_return=total_return,
            total_trades=len(self.trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_duration,
            calmar_ratio=calmar,
            var_95=var_95,
            cvar_95=cvar_95,
            worst_trade=worst_trade,
            worst_day=worst_day,
            avg_trade_duration=0,  # TODO
            profit_factor=profit_factor,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            is_curve_fitted=is_curve_fitted,
            pennies_steamroller=pennies_steamroller,
            sufficient_trades=sufficient_trades,
            trades=self.trades,
            equity_curve=equity
        )
    
    def _sharpe_ratio(self, returns: pd.Series, risk_free: float = 0.04) -> float:
        """Annualized Sharpe ratio."""
        if len(returns) < 2 or returns.std() == 0:
            return 0
        excess_returns = returns - (risk_free / 252)  # Daily risk-free
        return np.sqrt(252) * excess_returns.mean() / returns.std()
    
    def _sortino_ratio(self, returns: pd.Series, risk_free: float = 0.04) -> float:
        """Sortino ratio (penalizes downside only)."""
        if len(returns) < 2:
            return 0
        excess_returns = returns - (risk_free / 252)
        downside = returns[returns < 0]
        if len(downside) == 0 or downside.std() == 0:
            return 0
        return np.sqrt(252) * excess_returns.mean() / downside.std()
    
    def _max_drawdown(self, equity: pd.Series) -> tuple:
        """Max drawdown and duration."""
        peak = equity.expanding().max()
        drawdown = (equity - peak) / peak
        max_dd = drawdown.min()
        
        # Duration (simplified)
        in_drawdown = drawdown < 0
        if in_drawdown.any():
            dd_periods = in_drawdown.astype(int).groupby((~in_drawdown).cumsum()).sum()
            max_duration = dd_periods.max() if len(dd_periods) > 0 else 0
        else:
            max_duration = 0
        
        return max_dd, max_duration
    
    def _var(self, returns: pd.Series, confidence: float) -> float:
        """Value at Risk."""
        if len(returns) < 2:
            return 0
        return np.percentile(returns, (1 - confidence) * 100)
    
    def _cvar(self, returns: pd.Series, confidence: float) -> float:
        """Conditional VaR (Expected Shortfall)."""
        var = self._var(returns, confidence)
        return returns[returns <= var].mean() if len(returns[returns <= var]) > 0 else var
    
    def _empty_result(self) -> BacktestResult:
        """Return empty result when no trades."""
        return BacktestResult(
            total_return=0, total_trades=0, winning_trades=0, losing_trades=0,
            sharpe_ratio=0, sortino_ratio=0, max_drawdown=0, max_drawdown_duration=0,
            calmar_ratio=0, var_95=0, cvar_95=0, worst_trade=0, worst_day=0,
            avg_trade_duration=0, profit_factor=0, win_rate=0, avg_win=0, avg_loss=0,
            is_curve_fitted=False, pennies_steamroller=False, sufficient_trades=False,
            trades=[], equity_curve=pd.Series([self.initial_capital])
        )


def run_strategy(
    strategy_fn: Callable,
    start_date: str = None,
    end_date: str = None,
    initial_capital: float = 10000
) -> BacktestResult:
    """
    Run a strategy through backtesting.
    
    strategy_fn should accept (engine, row, data) and return trade signals.
    """
    engine = BacktestEngine(initial_capital=initial_capital)
    data = engine.load_data(start_date, end_date)
    
    if len(data) == 0:
        print("⚠️  No data available. Run the collector first.")
        return engine._empty_result()
    
    print(f"Backtesting on {len(data)} data points...")
    
    for idx, row in data.iterrows():
        # Call strategy
        signals = strategy_fn(engine, row, data.loc[:idx])
        
        # Execute signals
        for signal in signals:
            engine.execute_trade(**signal)
    
    return engine.calculate_results()

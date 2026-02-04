#!/usr/bin/env python3
"""
BOT FADE BACKTEST
Test the strategy: fade extreme prices with low volume backing.

Hypothesis: When price is extreme (<20% or >80%) but volume is low,
bots have manipulated the price without conviction. Fade it.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Tuple

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


@dataclass
class Trade:
    timestamp: datetime
    market_id: str
    side: str  # 'buy_yes', 'buy_no', 'sell_yes', 'sell_no'
    price: float
    size_usd: float
    pnl: float = 0.0


@dataclass 
class Position:
    market_id: str
    side: str  # 'yes' or 'no'
    entry_price: float
    size_usd: float
    entry_time: datetime


class BotFadeBacktest:
    """
    Backtest the bot fade strategy.
    
    Entry: Price extreme (<15% or >85%) + volume below average
    Exit: Price reverts toward center OR stop loss
    """
    
    def __init__(self, capital: float = 10000, max_position_pct: float = 0.02):
        self.initial_capital = capital
        self.capital = capital
        self.max_position_pct = max_position_pct
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        
        # Costs
        self.fee_rate = 0.01  # 1% fee
        self.slippage = 0.005  # 0.5% slippage
    
    def load_data(self) -> pd.DataFrame:
        """Load price snapshots from database."""
        conn = sqlite3.connect(DB_PATH)
        
        # Get all snapshots with market info
        query = """
        SELECT 
            ps.timestamp,
            ps.market_id,
            ps.yes_price,
            ps.no_price,
            ps.volume_24h,
            m.question
        FROM price_snapshots ps
        JOIN markets m ON ps.market_id = m.id
        ORDER BY ps.timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def calculate_volume_ratio(self, df: pd.DataFrame, market_id: str, 
                                current_idx: int, lookback: int = 10) -> float:
        """Calculate volume ratio vs overall market average."""
        current_vol = df.loc[current_idx, 'volume_24h']
        
        if current_vol is None or pd.isna(current_vol):
            return 1.0
        
        # Compare to overall average (since per-market history is sparse)
        if not hasattr(self, '_global_avg_vol'):
            self._global_avg_vol = df['volume_24h'].mean()
        
        if self._global_avg_vol == 0:
            return 1.0
        
        return current_vol / self._global_avg_vol
    
    def should_enter(self, row: pd.Series, vol_ratio: float) -> Tuple[bool, str]:
        """
        Check if we should enter a fade position.
        
        Returns: (should_enter, side)
        """
        yes_price = row['yes_price']
        
        if yes_price is None or pd.isna(yes_price):
            return False, ''
        
        # Entry conditions:
        # 1. Price is extreme
        # 2. Volume is below average (bots, not real flow)
        
        is_extreme_low = yes_price < 0.10  # Very cheap
        is_extreme_high = yes_price > 0.90  # Very expensive
        is_low_volume = vol_ratio < 1.0  # Below average volume
        
        if is_extreme_low and is_low_volume:
            return True, 'yes'  # Fade the low price, buy YES
        elif is_extreme_high and is_low_volume:
            return True, 'no'  # Fade the high price, buy NO
        
        return False, ''
    
    def should_exit(self, position: Position, current_price: float) -> Tuple[bool, str]:
        """
        Check if we should exit.
        
        Exit conditions:
        1. Price reverted toward center (profit)
        2. Stop loss hit (5% adverse move)
        3. Position held too long (20 periods)
        """
        if position.side == 'yes':
            # We bought YES expecting price to rise
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            
            # Take profit: 5% gain
            if pnl_pct > 0.05:
                return True, 'profit'
            
            # Stop loss: 5% loss
            if pnl_pct < -0.05:
                return True, 'stop'
        else:
            # We bought NO expecting YES price to fall
            # NO price = 1 - YES price
            entry_no_price = 1 - position.entry_price
            current_no_price = 1 - current_price
            pnl_pct = (current_no_price - entry_no_price) / entry_no_price if entry_no_price > 0 else 0
            
            if pnl_pct > 0.05:
                return True, 'profit'
            if pnl_pct < -0.05:
                return True, 'stop'
        
        return False, ''
    
    def run(self) -> Dict:
        """Run the backtest."""
        print("Loading data...")
        df = self.load_data()
        
        if df.empty:
            return {'error': 'No data available'}
        
        print(f"Backtesting on {len(df)} data points...")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"Markets: {df['market_id'].nunique()}")
        
        # Track periods for each position
        position_periods: Dict[str, int] = {}
        
        for idx, row in df.iterrows():
            timestamp = row['timestamp']
            market_id = row['market_id']
            yes_price = row['yes_price']
            
            if yes_price is None or pd.isna(yes_price):
                continue
            
            # Update equity curve
            self.equity_curve.append((timestamp, self.capital))
            
            # Check existing positions for exit
            if market_id in self.positions:
                pos = self.positions[market_id]
                position_periods[market_id] = position_periods.get(market_id, 0) + 1
                
                should_exit, reason = self.should_exit(pos, yes_price)
                
                # Also exit if held too long
                if position_periods.get(market_id, 0) > 8:  # Faster timeout
                    should_exit = True
                    reason = 'timeout'
                
                if should_exit:
                    # Calculate PnL
                    if pos.side == 'yes':
                        exit_price = yes_price * (1 - self.slippage)  # Slippage on exit
                        pnl = pos.size_usd * ((exit_price / pos.entry_price) - 1)
                    else:
                        entry_no = 1 - pos.entry_price
                        exit_no = (1 - yes_price) * (1 - self.slippage)
                        pnl = pos.size_usd * ((exit_no / entry_no) - 1) if entry_no > 0 else 0
                    
                    # Apply fees
                    pnl -= pos.size_usd * self.fee_rate
                    
                    self.capital += pnl
                    
                    trade = Trade(
                        timestamp=timestamp,
                        market_id=market_id,
                        side=f'sell_{pos.side}',
                        price=yes_price,
                        size_usd=pos.size_usd,
                        pnl=pnl
                    )
                    self.trades.append(trade)
                    
                    del self.positions[market_id]
                    if market_id in position_periods:
                        del position_periods[market_id]
            
            # Check for new entry
            elif len(self.positions) < 10:  # Max 10 concurrent positions
                vol_ratio = self.calculate_volume_ratio(df, market_id, idx)
                should_enter, side = self.should_enter(row, vol_ratio)
                
                if should_enter:
                    size = self.capital * self.max_position_pct
                    entry_price = yes_price * (1 + self.slippage)  # Slippage on entry
                    
                    self.positions[market_id] = Position(
                        market_id=market_id,
                        side=side,
                        entry_price=entry_price,
                        size_usd=size,
                        entry_time=timestamp
                    )
                    
                    # Entry fee
                    self.capital -= size * self.fee_rate
                    
                    trade = Trade(
                        timestamp=timestamp,
                        market_id=market_id,
                        side=f'buy_{side}',
                        price=entry_price,
                        size_usd=size
                    )
                    self.trades.append(trade)
        
        # Calculate results
        return self.calculate_results()
    
    def calculate_results(self) -> Dict:
        """Calculate backtest metrics."""
        if not self.trades:
            return {
                'total_return': 0,
                'total_trades': 0,
                'entries': 0,
                'win_rate': 0,
                'wins': 0,
                'losses': 0,
                'sharpe': 0,
                'max_drawdown': 0,
                'profit_factor': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'final_capital': self.capital,
                'gross_profit': 0,
                'gross_loss': 0,
                'open_positions': len(self.positions),
                'message': 'No trades executed'
            }
        
        # Separate entries and exits
        exits = [t for t in self.trades if t.side.startswith('sell')]
        entries = [t for t in self.trades if t.side.startswith('buy')]
        
        # Win rate
        wins = [t for t in exits if t.pnl > 0]
        losses = [t for t in exits if t.pnl <= 0]
        win_rate = len(wins) / len(exits) if exits else 0
        
        # Total return
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        
        # Calculate drawdown from equity curve
        if self.equity_curve:
            equities = [e[1] for e in self.equity_curve]
            peak = equities[0]
            max_dd = 0
            for eq in equities:
                if eq > peak:
                    peak = eq
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd
        else:
            max_dd = 0
        
        # Returns for Sharpe
        if len(exits) > 1:
            returns = [t.pnl / self.initial_capital for t in exits]
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe = 0
        
        # Profit factor
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Average trade
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        
        return {
            'total_return': total_return,
            'total_trades': len(exits),
            'entries': len(entries),
            'win_rate': win_rate,
            'wins': len(wins),
            'losses': len(losses),
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'final_capital': self.capital,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'open_positions': len(self.positions)
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗  ██████╗ ████████╗    ███████╗ █████╗ ██████╗ ███████╗            ║
║   ██╔══██╗██╔═══██╗╚══██╔══╝    ██╔════╝██╔══██╗██╔══██╗██╔════╝            ║
║   ██████╔╝██║   ██║   ██║       █████╗  ███████║██║  ██║█████╗              ║
║   ██╔══██╗██║   ██║   ██║       ██╔══╝  ██╔══██║██║  ██║██╔══╝              ║
║   ██████╔╝╚██████╔╝   ██║       ██║     ██║  ██║██████╔╝███████╗            ║
║   ╚═════╝  ╚═════╝    ╚═╝       ╚═╝     ╚═╝  ╚═╝╚═════╝ ╚══════╝            ║
║                                                                              ║
║   BACKTEST                                                                   ║
║   Strategy: Fade extreme prices with low volume                              ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    bt = BotFadeBacktest(capital=10000, max_position_pct=0.02)
    results = bt.run()
    
    if 'error' in results:
        print(f"❌ {results['error']}")
        return
    
    print("\n" + "═"*70)
    print("  BACKTEST RESULTS")
    print("═"*70)
    
    # Determine if valid
    is_profitable = results['total_return'] > 0
    has_enough_trades = results['total_trades'] >= 30
    good_sharpe = results['sharpe'] > 0.5
    reasonable_dd = results['max_drawdown'] < 0.20
    
    status = "✅ PROMISING" if (is_profitable and has_enough_trades) else "❌ NOT VIABLE"
    if results['total_trades'] < 10:
        status = "⚠️ INSUFFICIENT DATA"
    
    print(f"""
   Status: {status}
   
   RETURNS
   ├─ Total Return:     {results['total_return']*100:+.2f}%
   ├─ Final Capital:    ${results['final_capital']:,.2f}
   ├─ Sharpe Ratio:     {results['sharpe']:.2f}
   └─ Profit Factor:    {results['profit_factor']:.2f}
   
   RISK
   ├─ Max Drawdown:     {results['max_drawdown']*100:.2f}%
   └─ Open Positions:   {results['open_positions']}
   
   TRADES
   ├─ Total Trades:     {results['total_trades']} completed
   ├─ Entries:          {results['entries']}
   ├─ Win Rate:         {results['win_rate']*100:.1f}%
   ├─ Wins/Losses:      {results['wins']}/{results['losses']}
   ├─ Avg Win:          ${results['avg_win']:.2f}
   └─ Avg Loss:         ${results['avg_loss']:.2f}
    """)
    
    # Show recent trades
    if bt.trades:
        print("─"*70)
        print("  RECENT TRADES")
        print("─"*70)
        
        for trade in bt.trades[-10:]:
            pnl_str = f"${trade.pnl:+.2f}" if trade.pnl != 0 else ""
            print(f"   {trade.timestamp} | {trade.side:10} | ${trade.price:.3f} | {pnl_str}")
    
    print("\n" + "═"*70)
    
    # Verdict
    if results['total_trades'] < 30:
        print("""
   ⚠️  NEED MORE DATA
   
   Only {trades} trades executed. Need 30+ for statistical significance.
   
   Run collector longer:
   $ nohup python main.py collect > /dev/null 2>&1 &
   
   Then re-run this backtest.
        """.format(trades=results['total_trades']))
    elif is_profitable and has_enough_trades:
        print("""
   ✅ STRATEGY SHOWS PROMISE
   
   Next steps:
   1. Paper trade for 1 week
   2. If results hold, start with small capital
   3. Monitor for edge decay (bots adapt)
        """)
    else:
        print("""
   ❌ STRATEGY NOT VIABLE
   
   The bot fade hypothesis doesn't hold in this data.
   Possible reasons:
   - Bots aren't actually coordinating
   - Volume/price divergence isn't predictive
   - Market is genuinely efficient
        """)
    
    return results


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
HISTORICAL BACKTEST
Test FADE vs FOLLOW on 30 days of historical data.
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
    side: str
    price: float
    size_usd: float
    pnl: float = 0.0


@dataclass 
class Position:
    market_id: str
    side: str
    entry_price: float
    size_usd: float
    entry_time: datetime
    periods_held: int = 0


class HistoricalBacktest:
    """Backtest on 30 days of historical data."""
    
    def __init__(self, strategy: str = 'fade', capital: float = 10000):
        self.strategy = strategy  # 'fade' or 'follow'
        self.initial_capital = capital
        self.capital = capital
        self.max_position_pct = 0.02
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.fee_rate = 0.01
        self.slippage = 0.005
    
    def load_data(self) -> pd.DataFrame:
        """Load historical price data."""
        conn = sqlite3.connect(DB_PATH)
        
        query = """
        SELECT 
            market_id,
            timestamp,
            yes_price
        FROM historical_prices
        ORDER BY timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        return df
    
    def should_enter(self, price: float, vol_ratio: float = 0.5) -> Tuple[bool, str]:
        """
        Entry logic depends on strategy.
        
        FADE: extreme price → bet on reversion
        FOLLOW: extreme price → bet on continuation
        """
        is_extreme_low = price < 0.10
        is_extreme_high = price > 0.90
        
        if self.strategy == 'fade':
            # Fade = bet against the extreme
            if is_extreme_low:
                return True, 'yes'  # Buy YES, expect bounce
            elif is_extreme_high:
                return True, 'no'  # Buy NO, expect drop
        else:  # follow
            # Follow = bet with the extreme
            if is_extreme_low:
                return True, 'no'  # Buy NO, trust the low price
            elif is_extreme_high:
                return True, 'yes'  # Buy YES, trust the high price
        
        return False, ''
    
    def should_exit(self, pos: Position, current_price: float) -> Tuple[bool, str, float]:
        """Check exit conditions and calculate PnL."""
        if pos.side == 'yes':
            pnl_pct = (current_price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
        else:
            entry_no = 1 - pos.entry_price
            current_no = 1 - current_price
            pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
        
        # Exit conditions
        if pnl_pct > 0.05:  # 5% profit
            return True, 'profit', pnl_pct
        if pnl_pct < -0.05:  # 5% stop
            return True, 'stop', pnl_pct
        if pos.periods_held > 24:  # 24 hours timeout
            return True, 'timeout', pnl_pct
        
        return False, '', pnl_pct
    
    def run(self) -> Dict:
        """Run backtest."""
        print(f"Loading historical data...")
        df = self.load_data()
        
        if df.empty:
            return {'error': 'No data'}
        
        print(f"Data points: {len(df):,}")
        print(f"Markets: {df['market_id'].nunique()}")
        print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
        print(f"Strategy: {self.strategy.upper()}")
        print()
        
        # Group by timestamp for time-series simulation
        timestamps = df['timestamp'].unique()
        timestamps.sort()
        
        for ts in timestamps:
            current_time = datetime.fromtimestamp(ts)
            current_data = df[df['timestamp'] == ts]
            
            self.equity_curve.append((current_time, self.capital))
            
            # Process each market at this timestamp
            for _, row in current_data.iterrows():
                market_id = row['market_id']
                price = row['yes_price']
                
                if price is None or pd.isna(price):
                    continue
                
                # Check existing position
                if market_id in self.positions:
                    pos = self.positions[market_id]
                    pos.periods_held += 1
                    
                    should_exit, reason, pnl_pct = self.should_exit(pos, price)
                    
                    if should_exit:
                        # Calculate PnL
                        pnl = pos.size_usd * pnl_pct
                        pnl -= pos.size_usd * self.fee_rate  # Exit fee
                        
                        self.capital += pos.size_usd + pnl  # Return capital + PnL
                        
                        self.trades.append(Trade(
                            timestamp=current_time,
                            market_id=market_id,
                            side=f'sell_{pos.side}',
                            price=price,
                            size_usd=pos.size_usd,
                            pnl=pnl
                        ))
                        
                        del self.positions[market_id]
                
                # Check for new entry
                elif len(self.positions) < 10:  # Max 10 positions
                    should_enter, side = self.should_enter(price)
                    
                    if should_enter:
                        size = min(self.capital * self.max_position_pct, self.capital * 0.1)
                        
                        if size > 10:  # Minimum $10 position
                            self.capital -= size  # Lock up capital
                            self.capital -= size * self.fee_rate  # Entry fee
                            
                            self.positions[market_id] = Position(
                                market_id=market_id,
                                side=side,
                                entry_price=price,
                                size_usd=size,
                                entry_time=current_time
                            )
                            
                            self.trades.append(Trade(
                                timestamp=current_time,
                                market_id=market_id,
                                side=f'buy_{side}',
                                price=price,
                                size_usd=size
                            ))
        
        return self.calculate_results()
    
    def calculate_results(self) -> Dict:
        """Calculate final metrics."""
        # Add back value of open positions at last price
        final_capital = self.capital
        for pos in self.positions.values():
            final_capital += pos.size_usd  # Approximate
        
        exits = [t for t in self.trades if t.side.startswith('sell')]
        entries = [t for t in self.trades if t.side.startswith('buy')]
        
        wins = [t for t in exits if t.pnl > 0]
        losses = [t for t in exits if t.pnl <= 0]
        
        total_return = (final_capital - self.initial_capital) / self.initial_capital
        win_rate = len(wins) / len(exits) if exits else 0
        
        # Drawdown
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
        
        # Sharpe
        if len(exits) > 1:
            returns = [t.pnl / self.initial_capital for t in exits]
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0
        
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return {
            'strategy': self.strategy,
            'total_return': total_return,
            'final_capital': final_capital,
            'total_trades': len(exits),
            'entries': len(entries),
            'win_rate': win_rate,
            'wins': len(wins),
            'losses': len(losses),
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'profit_factor': profit_factor,
            'avg_win': np.mean([t.pnl for t in wins]) if wins else 0,
            'avg_loss': np.mean([t.pnl for t in losses]) if losses else 0,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'open_positions': len(self.positions)
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██╗  ██╗██╗███████╗████████╗ ██████╗ ██████╗ ██╗ ██████╗ █████╗ ██╗       ║
║   ██║  ██║██║██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗██║██╔════╝██╔══██╗██║       ║
║   ███████║██║███████╗   ██║   ██║   ██║██████╔╝██║██║     ███████║██║       ║
║   ██╔══██║██║╚════██║   ██║   ██║   ██║██╔══██╗██║██║     ██╔══██║██║       ║
║   ██║  ██║██║███████║   ██║   ╚██████╔╝██║  ██║██║╚██████╗██║  ██║███████╗  ║
║   ╚═╝  ╚═╝╚═╝╚══════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝  ║
║                                                                              ║
║   30-DAY BACKTEST: FADE vs FOLLOW                                            ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Run FADE
    print("=" * 70)
    print("  STRATEGY 1: FADE")
    print("=" * 70)
    fade_bt = HistoricalBacktest(strategy='fade', capital=10000)
    fade = fade_bt.run()
    
    # Run FOLLOW  
    print("\n" + "=" * 70)
    print("  STRATEGY 2: FOLLOW")
    print("=" * 70)
    follow_bt = HistoricalBacktest(strategy='follow', capital=10000)
    follow = follow_bt.run()
    
    # Comparison
    print("\n" + "═" * 70)
    print("  30-DAY HEAD TO HEAD")
    print("═" * 70)
    
    print(f"""
    ┌────────────────────┬─────────────────┬─────────────────┐
    │  Metric            │  FADE           │  FOLLOW         │
    ├────────────────────┼─────────────────┼─────────────────┤
    │  Total Return      │  {fade['total_return']*100:>+12.2f}%  │  {follow['total_return']*100:>+12.2f}%  │
    │  Final Capital     │  ${fade['final_capital']:>11,.0f}  │  ${follow['final_capital']:>11,.0f}  │
    │  Win Rate          │  {fade['win_rate']*100:>12.1f}%  │  {follow['win_rate']*100:>12.1f}%  │
    │  Trades            │  {fade['total_trades']:>13}  │  {follow['total_trades']:>13}  │
    │  Wins/Losses       │  {fade['wins']:>6}/{fade['losses']:<6}  │  {follow['wins']:>6}/{follow['losses']:<6}  │
    │  Profit Factor     │  {fade['profit_factor']:>13.2f}  │  {follow['profit_factor']:>13.2f}  │
    │  Max Drawdown      │  {fade['max_drawdown']*100:>12.2f}%  │  {follow['max_drawdown']*100:>12.2f}%  │
    │  Sharpe            │  {fade['sharpe']:>13.2f}  │  {follow['sharpe']:>13.2f}  │
    │  Avg Win           │  ${fade['avg_win']:>12.2f}  │  ${follow['avg_win']:>12.2f}  │
    │  Avg Loss          │  ${fade['avg_loss']:>12.2f}  │  ${follow['avg_loss']:>12.2f}  │
    └────────────────────┴─────────────────┴─────────────────┘
    """)
    
    # Verdict
    print("═" * 70)
    print("  VERDICT")
    print("═" * 70)
    
    fade_better = fade['total_return'] > follow['total_return']
    
    if fade['total_return'] > 0 and follow['total_return'] > 0:
        winner = 'FADE' if fade_better else 'FOLLOW'
        print(f"\n    ✅ BOTH PROFITABLE! {winner} wins by {abs(fade['total_return'] - follow['total_return'])*100:.2f}%")
    elif fade['total_return'] > 0:
        print(f"\n    ✅ FADE is profitable: +{fade['total_return']*100:.2f}%")
        print(f"    ❌ FOLLOW loses: {follow['total_return']*100:.2f}%")
    elif follow['total_return'] > 0:
        print(f"\n    ❌ FADE loses: {fade['total_return']*100:.2f}%")
        print(f"    ✅ FOLLOW is profitable: +{follow['total_return']*100:.2f}%")
    else:
        loser = 'FOLLOW' if fade_better else 'FADE'
        print(f"\n    ❌ Both strategies lose")
        print(f"    {loser} loses MORE ({min(fade['total_return'], follow['total_return'])*100:.2f}%)")
        
        if abs(fade['total_return'] - follow['total_return']) > 0.02:
            better = 'FADE' if fade_better else 'FOLLOW'
            print(f"    → {better} loses LESS - might be edge with refinement")
    
    print()
    
    return {'fade': fade, 'follow': follow}


if __name__ == "__main__":
    main()

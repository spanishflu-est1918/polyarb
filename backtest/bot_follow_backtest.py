#!/usr/bin/env python3
"""
BOT FOLLOW BACKTEST
The INVERSE of bot fade - if fading loses, following should win.

Thesis: If bots push prices to extremes and our fade loses,
then the bots are RIGHT. Follow them instead.

Original (FADE): Extreme low + low vol → buy YES (expect reversion)
Inverse (FOLLOW): Extreme low + low vol → buy NO (trust the bots)
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


class BotFollowBacktest:
    """
    INVERSE of fade strategy.
    If bots are pushing prices to extremes, JOIN them.
    """
    
    def __init__(self, capital: float = 10000, max_position_pct: float = 0.02):
        self.initial_capital = capital
        self.capital = capital
        self.max_position_pct = max_position_pct
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.fee_rate = 0.01
        self.slippage = 0.005
        self._global_avg_vol = None
    
    def load_data(self) -> pd.DataFrame:
        conn = sqlite3.connect(DB_PATH)
        query = """
        SELECT 
            ps.timestamp, ps.market_id, ps.yes_price, ps.no_price,
            ps.volume_24h, m.question
        FROM price_snapshots ps
        JOIN markets m ON ps.market_id = m.id
        ORDER BY ps.timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    
    def calculate_volume_ratio(self, df: pd.DataFrame, current_idx: int) -> float:
        current_vol = df.loc[current_idx, 'volume_24h']
        if current_vol is None or pd.isna(current_vol):
            return 1.0
        if self._global_avg_vol is None:
            self._global_avg_vol = df['volume_24h'].mean()
        if self._global_avg_vol == 0:
            return 1.0
        return current_vol / self._global_avg_vol
    
    def should_enter(self, row: pd.Series, vol_ratio: float) -> Tuple[bool, str]:
        """
        INVERSE LOGIC:
        - Extreme low price + low vol → bots are SHORT → WE GO SHORT (buy NO)
        - Extreme high price + low vol → bots are LONG → WE GO LONG (buy YES)
        """
        yes_price = row['yes_price']
        
        if yes_price is None or pd.isna(yes_price):
            return False, ''
        
        is_extreme_low = yes_price < 0.10
        is_extreme_high = yes_price > 0.90
        is_low_volume = vol_ratio < 1.0
        
        if is_extreme_low and is_low_volume:
            # Bots pushed it low, FOLLOW them - buy NO (bet it stays low/goes lower)
            return True, 'no'
        elif is_extreme_high and is_low_volume:
            # Bots pushed it high, FOLLOW them - buy YES (bet it stays high)
            return True, 'yes'
        
        return False, ''
    
    def should_exit(self, position: Position, current_price: float) -> Tuple[bool, str]:
        """Exit on profit or stop."""
        if position.side == 'yes':
            # Bought YES at high price, profit if it goes higher
            pnl_pct = (current_price - position.entry_price) / position.entry_price
            if pnl_pct > 0.02:  # 2% profit (tighter)
                return True, 'profit'
            if pnl_pct < -0.03:  # 3% stop (tighter)
                return True, 'stop'
        else:  # NO position
            # Bought NO (price was low), profit if YES stays low or goes lower
            # NO price goes UP when YES goes DOWN
            entry_no = 1 - position.entry_price
            current_no = 1 - current_price
            pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
            if pnl_pct > 0.02:
                return True, 'profit'
            if pnl_pct < -0.03:
                return True, 'stop'
        
        return False, ''
    
    def run(self) -> Dict:
        print("Loading data...")
        df = self.load_data()
        
        if df.empty:
            return {'error': 'No data'}
        
        print(f"Backtesting on {len(df)} data points...")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        position_periods: Dict[str, int] = {}
        
        for idx, row in df.iterrows():
            timestamp = row['timestamp']
            market_id = row['market_id']
            yes_price = row['yes_price']
            
            if yes_price is None or pd.isna(yes_price):
                continue
            
            self.equity_curve.append((timestamp, self.capital))
            
            # Check exits
            if market_id in self.positions:
                pos = self.positions[market_id]
                position_periods[market_id] = position_periods.get(market_id, 0) + 1
                
                should_exit, reason = self.should_exit(pos, yes_price)
                
                if position_periods.get(market_id, 0) > 8:  # Faster timeout
                    should_exit = True
                    reason = 'timeout'
                
                if should_exit:
                    if pos.side == 'yes':
                        exit_price = yes_price * (1 - self.slippage)
                        pnl = pos.size_usd * ((exit_price / pos.entry_price) - 1)
                    else:
                        entry_no = 1 - pos.entry_price
                        exit_no = (1 - yes_price) * (1 - self.slippage)
                        pnl = pos.size_usd * ((exit_no / entry_no) - 1) if entry_no > 0 else 0
                    
                    pnl -= pos.size_usd * self.fee_rate
                    self.capital += pnl
                    
                    self.trades.append(Trade(
                        timestamp=timestamp, market_id=market_id,
                        side=f'sell_{pos.side}', price=yes_price,
                        size_usd=pos.size_usd, pnl=pnl
                    ))
                    
                    del self.positions[market_id]
                    if market_id in position_periods:
                        del position_periods[market_id]
            
            # Check entries
            elif len(self.positions) < 10:
                vol_ratio = self.calculate_volume_ratio(df, idx)
                should_enter, side = self.should_enter(row, vol_ratio)
                
                if should_enter:
                    size = self.capital * self.max_position_pct
                    entry_price = yes_price * (1 + self.slippage)
                    
                    self.positions[market_id] = Position(
                        market_id=market_id, side=side,
                        entry_price=entry_price, size_usd=size,
                        entry_time=timestamp
                    )
                    
                    self.capital -= size * self.fee_rate
                    
                    self.trades.append(Trade(
                        timestamp=timestamp, market_id=market_id,
                        side=f'buy_{side}', price=entry_price, size_usd=size
                    ))
        
        return self.calculate_results()
    
    def calculate_results(self) -> Dict:
        if not self.trades:
            return {
                'total_return': 0, 'total_trades': 0, 'entries': 0,
                'win_rate': 0, 'wins': 0, 'losses': 0, 'sharpe': 0,
                'max_drawdown': 0, 'profit_factor': 0, 'avg_win': 0,
                'avg_loss': 0, 'final_capital': self.capital,
                'gross_profit': 0, 'gross_loss': 0,
                'open_positions': len(self.positions)
            }
        
        exits = [t for t in self.trades if t.side.startswith('sell')]
        entries = [t for t in self.trades if t.side.startswith('buy')]
        
        wins = [t for t in exits if t.pnl > 0]
        losses = [t for t in exits if t.pnl <= 0]
        win_rate = len(wins) / len(exits) if exits else 0
        
        total_return = (self.capital - self.initial_capital) / self.initial_capital
        
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
        
        if len(exits) > 1:
            returns = [t.pnl / self.initial_capital for t in exits]
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            sharpe = 0
        
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        avg_win = np.mean([t.pnl for t in wins]) if wins else 0
        avg_loss = np.mean([t.pnl for t in losses]) if losses else 0
        
        return {
            'total_return': total_return, 'total_trades': len(exits),
            'entries': len(entries), 'win_rate': win_rate,
            'wins': len(wins), 'losses': len(losses), 'sharpe': sharpe,
            'max_drawdown': max_dd, 'profit_factor': profit_factor,
            'avg_win': avg_win, 'avg_loss': avg_loss,
            'final_capital': self.capital, 'gross_profit': gross_profit,
            'gross_loss': gross_loss, 'open_positions': len(self.positions)
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗  ██████╗ ████████╗    ███████╗ ██████╗ ██╗     ██╗      ██████╗   ║
║   ██╔══██╗██╔═══██╗╚══██╔══╝    ██╔════╝██╔═══██╗██║     ██║     ██╔═══██╗  ║
║   ██████╔╝██║   ██║   ██║       █████╗  ██║   ██║██║     ██║     ██║   ██║  ║
║   ██╔══██╗██║   ██║   ██║       ██╔══╝  ██║   ██║██║     ██║     ██║   ██║  ║
║   ██████╔╝╚██████╔╝   ██║       ██║     ╚██████╔╝███████╗███████╗╚██████╔╝  ║
║   ╚═════╝  ╚═════╝    ╚═╝       ╚═╝      ╚═════╝ ╚══════╝╚══════╝ ╚═════╝   ║
║                                                                              ║
║   INVERSE STRATEGY: If fading loses, FOLLOW the bots instead                 ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Run BOTH strategies for comparison
    from bot_fade_backtest import BotFadeBacktest
    
    print("=" * 70)
    print("  STRATEGY 1: FADE (original)")
    print("=" * 70)
    fade = BotFadeBacktest(capital=10000, max_position_pct=0.02)
    fade_results = fade.run()
    
    print("\n" + "=" * 70)
    print("  STRATEGY 2: FOLLOW (inverse)")
    print("=" * 70)
    follow = BotFollowBacktest(capital=10000, max_position_pct=0.02)
    follow_results = follow.run()
    
    # Comparison
    print("\n" + "═" * 70)
    print("  HEAD TO HEAD COMPARISON")
    print("═" * 70)
    
    print(f"""
    ┌────────────────────┬─────────────────┬─────────────────┐
    │  Metric            │  FADE (orig)    │  FOLLOW (inv)   │
    ├────────────────────┼─────────────────┼─────────────────┤
    │  Total Return      │  {fade_results['total_return']*100:>+12.2f}%  │  {follow_results['total_return']*100:>+12.2f}%  │
    │  Win Rate          │  {fade_results['win_rate']*100:>12.1f}%  │  {follow_results['win_rate']*100:>12.1f}%  │
    │  Trades            │  {fade_results['total_trades']:>13}  │  {follow_results['total_trades']:>13}  │
    │  Profit Factor     │  {fade_results['profit_factor']:>13.2f}  │  {follow_results['profit_factor']:>13.2f}  │
    │  Max Drawdown      │  {fade_results['max_drawdown']*100:>12.2f}%  │  {follow_results['max_drawdown']*100:>12.2f}%  │
    │  Sharpe            │  {fade_results['sharpe']:>13.2f}  │  {follow_results['sharpe']:>13.2f}  │
    │  Avg Win           │  ${fade_results['avg_win']:>12.2f}  │  ${follow_results['avg_win']:>12.2f}  │
    │  Avg Loss          │  ${fade_results['avg_loss']:>12.2f}  │  ${follow_results['avg_loss']:>12.2f}  │
    └────────────────────┴─────────────────┴─────────────────┘
    """)
    
    # Verdict
    fade_better = fade_results['total_return'] > follow_results['total_return']
    follow_better = follow_results['total_return'] > fade_results['total_return']
    
    if follow_better and follow_results['total_return'] > 0:
        print("    ✅ FOLLOW wins! Being consistently wrong = edge when inverted")
    elif fade_better and fade_results['total_return'] > 0:
        print("    ✅ FADE wins! Original thesis holds")
    elif follow_results['total_return'] > fade_results['total_return']:
        print("    ⚠️  FOLLOW loses less - might be edge with more data")
    else:
        print("    ❌ Both strategies losing - need more data or different thesis")
    
    print("\n    Open positions (still running):")
    print(f"    • FADE: {fade_results['open_positions']}")
    print(f"    • FOLLOW: {follow_results['open_positions']}")
    
    return {'fade': fade_results, 'follow': follow_results}


if __name__ == "__main__":
    main()

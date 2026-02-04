#!/usr/bin/env python3
"""
EXPANDED BACKTEST
Test multiple FADE variations to find optimal parameters.

Variations:
1. Entry thresholds (how extreme?)
2. Exit targets (take profit levels)
3. Stop losses
4. Hold periods
5. Position sizing
6. Combined signals (price + volume)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor
import itertools

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


@dataclass
class StrategyConfig:
    """Strategy parameters to test."""
    name: str
    entry_low: float = 0.10  # Buy YES when price below this
    entry_high: float = 0.90  # Buy NO when price above this
    take_profit: float = 0.05  # Exit at 5% profit
    stop_loss: float = 0.05  # Exit at 5% loss
    max_hold: int = 24  # Max hours to hold
    position_size: float = 0.02  # % of capital per trade
    require_low_volume: bool = False  # Require below-avg volume
    volume_threshold: float = 1.0  # Volume ratio threshold


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


def load_data() -> pd.DataFrame:
    """Load historical data once."""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT market_id, timestamp, yes_price
        FROM historical_prices
        ORDER BY timestamp ASC
    """, conn)
    conn.close()
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    return df


def run_strategy(df: pd.DataFrame, config: StrategyConfig) -> Dict:
    """Run a single strategy configuration."""
    capital = 10000
    initial_capital = capital
    positions: Dict[str, Position] = {}
    trades: List[Trade] = []
    equity_curve = []
    fee_rate = 0.01
    
    # Calculate volume stats if needed
    if config.require_low_volume:
        vol_by_market = df.groupby('market_id')['yes_price'].std()
    
    timestamps = df['timestamp'].unique()
    timestamps.sort()
    
    for ts in timestamps:
        current_time = datetime.fromtimestamp(ts)
        current_data = df[df['timestamp'] == ts]
        equity_curve.append(capital)
        
        for _, row in current_data.iterrows():
            market_id = row['market_id']
            price = row['yes_price']
            
            if price is None or pd.isna(price):
                continue
            
            # Check existing position
            if market_id in positions:
                pos = positions[market_id]
                pos.periods_held += 1
                
                # Calculate current PnL
                if pos.side == 'yes':
                    pnl_pct = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else 0
                else:
                    entry_no = 1 - pos.entry_price
                    current_no = 1 - price
                    pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
                
                # Exit conditions
                should_exit = False
                if pnl_pct > config.take_profit:
                    should_exit = True
                elif pnl_pct < -config.stop_loss:
                    should_exit = True
                elif pos.periods_held > config.max_hold:
                    should_exit = True
                
                if should_exit:
                    pnl = pos.size_usd * pnl_pct - pos.size_usd * fee_rate
                    capital += pos.size_usd + pnl
                    trades.append(Trade(current_time, market_id, f'sell_{pos.side}', price, pos.size_usd, pnl))
                    del positions[market_id]
            
            # Check for entry
            elif len(positions) < 10:
                should_enter = False
                side = ''
                
                # Entry logic
                if price < config.entry_low:
                    should_enter = True
                    side = 'yes'
                elif price > config.entry_high:
                    should_enter = True
                    side = 'no'
                
                if should_enter:
                    size = min(capital * config.position_size, capital * 0.1)
                    if size > 10:
                        capital -= size + size * fee_rate
                        positions[market_id] = Position(market_id, side, price, size, current_time)
                        trades.append(Trade(current_time, market_id, f'buy_{side}', price, size))
    
    # Calculate results
    final_capital = capital + sum(p.size_usd for p in positions.values())
    exits = [t for t in trades if t.side.startswith('sell')]
    wins = [t for t in exits if t.pnl > 0]
    losses = [t for t in exits if t.pnl <= 0]
    
    total_return = (final_capital - initial_capital) / initial_capital
    win_rate = len(wins) / len(exits) if exits else 0
    
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    # Max drawdown
    if equity_curve:
        peak = equity_curve[0]
        max_dd = 0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak
            if dd > max_dd:
                max_dd = dd
    else:
        max_dd = 0
    
    # Sharpe
    if len(exits) > 1:
        returns = [t.pnl / initial_capital for t in exits]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
    else:
        sharpe = 0
    
    return {
        'name': config.name,
        'config': config,
        'total_return': total_return,
        'final_capital': final_capital,
        'trades': len(exits),
        'win_rate': win_rate,
        'wins': len(wins),
        'losses': len(losses),
        'profit_factor': profit_factor,
        'max_drawdown': max_dd,
        'sharpe': sharpe,
        'avg_win': np.mean([t.pnl for t in wins]) if wins else 0,
        'avg_loss': np.mean([t.pnl for t in losses]) if losses else 0,
    }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ███████╗██╗  ██╗██████╗  █████╗ ███╗   ██╗██████╗ ███████╗██████╗         ║
║   ██╔════╝╚██╗██╔╝██╔══██╗██╔══██╗████╗  ██║██╔══██╗██╔════╝██╔══██╗        ║
║   █████╗   ╚███╔╝ ██████╔╝███████║██╔██╗ ██║██║  ██║█████╗  ██║  ██║        ║
║   ██╔══╝   ██╔██╗ ██╔═══╝ ██╔══██║██║╚██╗██║██║  ██║██╔══╝  ██║  ██║        ║
║   ███████╗██╔╝ ██╗██║     ██║  ██║██║ ╚████║██████╔╝███████╗██████╔╝        ║
║   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚═════╝ ╚══════╝╚═════╝         ║
║                                                                              ║
║   Testing multiple FADE variations to find optimal parameters                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    print("Loading data...")
    df = load_data()
    print(f"Data points: {len(df):,}")
    print(f"Markets: {df['market_id'].nunique()}")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    print()
    
    # Define strategy variations
    strategies = [
        # Original
        StrategyConfig("baseline", 0.10, 0.90, 0.05, 0.05, 24, 0.02),
        
        # Entry threshold variations
        StrategyConfig("tight_entry", 0.05, 0.95, 0.05, 0.05, 24, 0.02),
        StrategyConfig("loose_entry", 0.15, 0.85, 0.05, 0.05, 24, 0.02),
        StrategyConfig("very_loose", 0.20, 0.80, 0.05, 0.05, 24, 0.02),
        
        # Take profit variations
        StrategyConfig("quick_profit", 0.10, 0.90, 0.03, 0.05, 24, 0.02),
        StrategyConfig("patient_profit", 0.10, 0.90, 0.10, 0.05, 24, 0.02),
        StrategyConfig("greedy", 0.10, 0.90, 0.15, 0.05, 48, 0.02),
        
        # Stop loss variations  
        StrategyConfig("tight_stop", 0.10, 0.90, 0.05, 0.03, 24, 0.02),
        StrategyConfig("loose_stop", 0.10, 0.90, 0.05, 0.10, 24, 0.02),
        StrategyConfig("no_stop", 0.10, 0.90, 0.05, 0.50, 48, 0.02),
        
        # Hold period variations
        StrategyConfig("scalper", 0.10, 0.90, 0.03, 0.03, 6, 0.02),
        StrategyConfig("swing", 0.10, 0.90, 0.08, 0.08, 72, 0.02),
        StrategyConfig("holder", 0.10, 0.90, 0.15, 0.10, 168, 0.02),
        
        # Position size variations
        StrategyConfig("small_size", 0.10, 0.90, 0.05, 0.05, 24, 0.01),
        StrategyConfig("large_size", 0.10, 0.90, 0.05, 0.05, 24, 0.05),
        
        # Asymmetric strategies
        StrategyConfig("favor_yes", 0.15, 0.95, 0.05, 0.05, 24, 0.02),  # More YES trades
        StrategyConfig("favor_no", 0.05, 0.85, 0.05, 0.05, 24, 0.02),   # More NO trades
        
        # Combined optimal guesses
        StrategyConfig("aggressive", 0.15, 0.85, 0.08, 0.03, 12, 0.03),
        StrategyConfig("conservative", 0.08, 0.92, 0.04, 0.04, 48, 0.015),
        StrategyConfig("balanced", 0.12, 0.88, 0.06, 0.06, 36, 0.025),
    ]
    
    print(f"Testing {len(strategies)} strategy variations...\n")
    
    results = []
    for i, config in enumerate(strategies, 1):
        print(f"[{i}/{len(strategies)}] {config.name}...", end=" ", flush=True)
        result = run_strategy(df, config)
        results.append(result)
        print(f"{result['total_return']*100:+.2f}% ({result['trades']} trades)")
    
    # Sort by return
    results.sort(key=lambda x: x['total_return'], reverse=True)
    
    # Display results
    print("\n" + "═" * 90)
    print("  STRATEGY COMPARISON (sorted by return)")
    print("═" * 90)
    print(f"{'Strategy':<18} {'Return':>10} {'Trades':>8} {'WinRate':>8} {'PF':>8} {'Sharpe':>8} {'MaxDD':>8}")
    print("─" * 90)
    
    for r in results:
        pf_str = f"{r['profit_factor']:.2f}" if r['profit_factor'] < 100 else "∞"
        sharpe_str = f"{r['sharpe']:.2f}" if abs(r['sharpe']) < 100 else "N/A"
        print(f"{r['name']:<18} {r['total_return']*100:>+9.2f}% {r['trades']:>8} {r['win_rate']*100:>7.1f}% {pf_str:>8} {sharpe_str:>8} {r['max_drawdown']*100:>7.2f}%")
    
    # Top 3 analysis
    print("\n" + "═" * 90)
    print("  TOP 3 STRATEGIES")
    print("═" * 90)
    
    for i, r in enumerate(results[:3], 1):
        c = r['config']
        print(f"""
    #{i} {r['name']}
    ├─ Return:        {r['total_return']*100:+.2f}%
    ├─ Final Capital: ${r['final_capital']:,.0f}
    ├─ Trades:        {r['trades']} ({r['wins']}W/{r['losses']}L)
    ├─ Win Rate:      {r['win_rate']*100:.1f}%
    ├─ Profit Factor: {r['profit_factor']:.2f}
    ├─ Max Drawdown:  {r['max_drawdown']*100:.2f}%
    ├─ Avg Win:       ${r['avg_win']:.2f}
    ├─ Avg Loss:      ${r['avg_loss']:.2f}
    │
    └─ Parameters:
       Entry: <{c.entry_low:.0%} or >{c.entry_high:.0%}
       TP/SL: {c.take_profit:.0%}/{c.stop_loss:.0%}
       Hold:  {c.max_hold}h | Size: {c.position_size:.0%}
    """)
    
    # Risk-adjusted best (Sharpe)
    best_sharpe = max(results, key=lambda x: x['sharpe'] if x['sharpe'] > -50 else -999)
    if best_sharpe['name'] != results[0]['name']:
        print(f"    Best Risk-Adjusted: {best_sharpe['name']} (Sharpe: {best_sharpe['sharpe']:.2f})")
    
    print("\n" + "═" * 90)
    print("  INSIGHTS")
    print("═" * 90)
    
    # Analyze patterns
    profitable = [r for r in results if r['total_return'] > 0]
    losing = [r for r in results if r['total_return'] <= 0]
    
    print(f"""
    Profitable strategies: {len(profitable)}/{len(results)}
    
    Patterns in winning strategies:
    """)
    
    if profitable:
        avg_entry_low = np.mean([r['config'].entry_low for r in profitable])
        avg_entry_high = np.mean([r['config'].entry_high for r in profitable])
        avg_tp = np.mean([r['config'].take_profit for r in profitable])
        avg_sl = np.mean([r['config'].stop_loss for r in profitable])
        avg_hold = np.mean([r['config'].max_hold for r in profitable])
        
        print(f"    Avg entry thresholds: <{avg_entry_low:.0%} or >{avg_entry_high:.0%}")
        print(f"    Avg take profit: {avg_tp:.0%}")
        print(f"    Avg stop loss: {avg_sl:.0%}")
        print(f"    Avg hold period: {avg_hold:.0f}h")
    
    return results


if __name__ == "__main__":
    main()

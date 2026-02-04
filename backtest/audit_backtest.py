#!/usr/bin/env python3
"""
AUDIT BACKTEST
Show EXACT trades with full transparency.
No bullshit - every entry and exit with reasoning.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


def load_data():
    """Load historical data with market names."""
    conn = sqlite3.connect(DB_PATH)
    
    # Get historical prices
    prices = pd.read_sql_query("""
        SELECT market_id, timestamp, yes_price
        FROM historical_prices
        ORDER BY timestamp ASC
    """, conn)
    
    # Get market names
    markets = pd.read_sql_query("""
        SELECT id, question FROM markets
    """, conn)
    
    conn.close()
    
    prices['datetime'] = pd.to_datetime(prices['timestamp'], unit='s')
    
    # Merge names
    prices = prices.merge(markets, left_on='market_id', right_on='id', how='left')
    
    return prices


def run_audit():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  AUDIT BACKTEST - FULL TRANSPARENCY                                          ║
║  Showing every trade with exact reasoning                                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    df = load_data()
    
    print(f"Data loaded: {len(df):,} price points")
    print(f"Markets: {df['market_id'].nunique()}")
    print(f"Date range: {df['datetime'].min()} to {df['datetime'].max()}")
    
    # Strategy parameters (baseline FADE)
    ENTRY_LOW = 0.10   # Buy YES when price < 10%
    ENTRY_HIGH = 0.90  # Buy NO when price > 90%
    TAKE_PROFIT = 0.05 # Exit at 5% profit
    STOP_LOSS = 0.05   # Exit at 5% loss
    MAX_HOLD = 24      # Max 24 periods
    POSITION_SIZE = 0.02  # 2% per trade
    FEE = 0.01         # 1% fee
    
    print(f"""
STRATEGY RULES:
---------------
1. ENTRY: Buy YES when price < {ENTRY_LOW:.0%}
          Buy NO when price > {ENTRY_HIGH:.0%}
2. EXIT:  Take profit at {TAKE_PROFIT:.0%} gain
          Stop loss at {STOP_LOSS:.0%} loss
          Force exit after {MAX_HOLD} periods
3. FEES:  {FEE:.0%} per trade (entry + exit)
4. SIZE:  {POSITION_SIZE:.0%} of capital per trade
5. MAX:   10 concurrent positions

WHY THIS SHOULD WORK:
- Extreme prices (<10% or >90%) often revert toward center
- We're betting on mean reversion, not prediction
- Small wins (5%) with controlled losses (5%)
    """)
    
    # Run backtest with full logging
    capital = 10000
    initial_capital = capital
    positions = {}
    all_trades = []
    
    timestamps = sorted(df['timestamp'].unique())
    
    print("\n" + "="*80)
    print("TRADE LOG (showing first 30 trades)")
    print("="*80)
    
    trade_count = 0
    shown_trades = 0
    
    for ts in timestamps:
        current_time = datetime.fromtimestamp(ts)
        current_data = df[df['timestamp'] == ts]
        
        for _, row in current_data.iterrows():
            market_id = row['market_id']
            price = row['yes_price']
            name = row['question'][:50] if row['question'] else 'Unknown'
            
            if price is None or pd.isna(price):
                continue
            
            # Check existing position for exit
            if market_id in positions:
                pos = positions[market_id]
                pos['periods'] += 1
                
                # Calculate PnL
                if pos['side'] == 'yes':
                    pnl_pct = (price - pos['entry']) / pos['entry'] if pos['entry'] > 0 else 0
                else:
                    entry_no = 1 - pos['entry']
                    current_no = 1 - price
                    pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
                
                # Check exit conditions
                exit_reason = None
                if pnl_pct > TAKE_PROFIT:
                    exit_reason = 'PROFIT'
                elif pnl_pct < -STOP_LOSS:
                    exit_reason = 'STOP'
                elif pos['periods'] > MAX_HOLD:
                    exit_reason = 'TIMEOUT'
                
                if exit_reason:
                    pnl_usd = pos['size'] * pnl_pct - pos['size'] * FEE
                    capital += pos['size'] + pnl_usd
                    
                    trade = {
                        'time': current_time,
                        'market': name,
                        'side': pos['side'],
                        'entry_price': pos['entry'],
                        'exit_price': price,
                        'pnl_pct': pnl_pct,
                        'pnl_usd': pnl_usd,
                        'reason': exit_reason,
                        'periods_held': pos['periods']
                    }
                    all_trades.append(trade)
                    trade_count += 1
                    
                    # Show trade details
                    if shown_trades < 30:
                        shown_trades += 1
                        win_loss = "WIN" if pnl_usd > 0 else "LOSS"
                        print(f"""
Trade #{trade_count}: {win_loss}
  Market:  {name}
  Side:    {pos['side'].upper()}
  Entry:   {pos['entry']:.4f} ({pos['entry']*100:.1f}%)
  Exit:    {price:.4f} ({price*100:.1f}%)
  Held:    {pos['periods']} periods
  Reason:  {exit_reason}
  PnL:     {pnl_pct*100:+.2f}% = ${pnl_usd:+.2f}
  Capital: ${capital:,.2f}
""")
                    
                    del positions[market_id]
            
            # Check for new entry
            elif len(positions) < 10:
                should_enter = False
                side = ''
                reason = ''
                
                if price < ENTRY_LOW:
                    should_enter = True
                    side = 'yes'
                    reason = f'Price {price:.1%} < {ENTRY_LOW:.0%} threshold'
                elif price > ENTRY_HIGH:
                    should_enter = True
                    side = 'no'
                    reason = f'Price {price:.1%} > {ENTRY_HIGH:.0%} threshold'
                
                if should_enter:
                    size = capital * POSITION_SIZE
                    if size > 10:
                        capital -= size + size * FEE
                        positions[market_id] = {
                            'side': side,
                            'entry': price,
                            'size': size,
                            'time': current_time,
                            'periods': 0,
                            'name': name,
                            'reason': reason
                        }
    
    # Final stats
    print("\n" + "="*80)
    print("FINAL RESULTS")
    print("="*80)
    
    if not all_trades:
        print("NO TRADES COMPLETED")
        return
    
    wins = [t for t in all_trades if t['pnl_usd'] > 0]
    losses = [t for t in all_trades if t['pnl_usd'] <= 0]
    
    total_return = (capital - initial_capital) / initial_capital
    
    print(f"""
SUMMARY:
--------
Starting Capital: ${initial_capital:,.2f}
Final Capital:    ${capital:,.2f}
Total Return:     {total_return*100:+.2f}%

Trades:           {len(all_trades)}
Wins:             {len(wins)} ({len(wins)/len(all_trades)*100:.1f}%)
Losses:           {len(losses)} ({len(losses)/len(all_trades)*100:.1f}%)

Gross Profit:     ${sum(t['pnl_usd'] for t in wins):,.2f}
Gross Loss:       ${sum(t['pnl_usd'] for t in losses):,.2f}

Avg Win:          ${np.mean([t['pnl_usd'] for t in wins]):.2f}
Avg Loss:         ${np.mean([t['pnl_usd'] for t in losses]):.2f}
    """)
    
    # Exit reason breakdown
    print("\nEXIT REASONS:")
    for reason in ['PROFIT', 'STOP', 'TIMEOUT']:
        trades_with_reason = [t for t in all_trades if t['reason'] == reason]
        if trades_with_reason:
            pnl = sum(t['pnl_usd'] for t in trades_with_reason)
            print(f"  {reason}: {len(trades_with_reason)} trades, ${pnl:+,.2f}")
    
    # Show some winning and losing trades
    print("\n" + "="*80)
    print("SAMPLE WINNING TRADES")
    print("="*80)
    
    for t in sorted(wins, key=lambda x: x['pnl_usd'], reverse=True)[:5]:
        print(f"""
  {t['market']}
  {t['side'].upper()} @ {t['entry_price']:.4f} → {t['exit_price']:.4f}
  PnL: ${t['pnl_usd']:+.2f} ({t['reason']}, {t['periods_held']} periods)
""")
    
    print("\n" + "="*80)
    print("SAMPLE LOSING TRADES")
    print("="*80)
    
    for t in sorted(losses, key=lambda x: x['pnl_usd'])[:5]:
        print(f"""
  {t['market']}
  {t['side'].upper()} @ {t['entry_price']:.4f} → {t['exit_price']:.4f}
  PnL: ${t['pnl_usd']:+.2f} ({t['reason']}, {t['periods_held']} periods)
""")
    
    # Sanity check
    print("\n" + "="*80)
    print("SANITY CHECK")
    print("="*80)
    
    total_pnl = sum(t['pnl_usd'] for t in all_trades)
    calc_return = total_pnl / initial_capital
    
    print(f"""
Sum of all trade PnLs: ${total_pnl:,.2f}
Calculated return:     {calc_return*100:+.2f}%
Reported return:       {total_return*100:+.2f}%
Difference:            {abs(total_return - calc_return)*100:.2f}%

Open positions at end: {len(positions)}
Capital in open pos:   ${sum(p['size'] for p in positions.values()):,.2f}
    """)
    
    return all_trades


if __name__ == "__main__":
    run_audit()

#!/usr/bin/env python3
"""
TIME SPLIT BACKTEST
Run strategy on different time periods to validate consistency.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


def load_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("""
        SELECT market_id, timestamp, yes_price
        FROM historical_prices
        ORDER BY timestamp ASC
    """, conn)
    conn.close()
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
    df['date'] = df['datetime'].dt.date
    return df


def run_backtest_on_period(df, start_ts, end_ts, period_name):
    """Run backtest on a specific time period."""
    
    # Filter data to period
    period_df = df[(df['timestamp'] >= start_ts) & (df['timestamp'] < end_ts)]
    
    if len(period_df) == 0:
        return None
    
    # Strategy params
    ENTRY_LOW = 0.10
    ENTRY_HIGH = 0.90
    TAKE_PROFIT = 0.05
    STOP_LOSS = 0.05
    MAX_HOLD = 24
    POSITION_SIZE = 0.02
    FEE = 0.01
    
    capital = 10000
    initial_capital = capital
    positions = {}
    trades = []
    
    timestamps = sorted(period_df['timestamp'].unique())
    
    for ts in timestamps:
        current_data = period_df[period_df['timestamp'] == ts]
        
        for _, row in current_data.iterrows():
            market_id = row['market_id']
            price = row['yes_price']
            
            if price is None or pd.isna(price):
                continue
            
            # Check exits
            if market_id in positions:
                pos = positions[market_id]
                pos['periods'] += 1
                
                if pos['side'] == 'yes':
                    pnl_pct = (price - pos['entry']) / pos['entry'] if pos['entry'] > 0 else 0
                else:
                    entry_no = 1 - pos['entry']
                    current_no = 1 - price
                    pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
                
                should_exit = False
                if pnl_pct > TAKE_PROFIT:
                    should_exit = True
                elif pnl_pct < -STOP_LOSS:
                    should_exit = True
                elif pos['periods'] > MAX_HOLD:
                    should_exit = True
                
                if should_exit:
                    pnl_usd = pos['size'] * pnl_pct - pos['size'] * FEE
                    capital += pos['size'] + pnl_usd
                    trades.append({'pnl': pnl_usd, 'win': pnl_usd > 0})
                    del positions[market_id]
            
            # Check entries
            elif len(positions) < 10:
                if price < ENTRY_LOW:
                    size = capital * POSITION_SIZE
                    if size > 10:
                        capital -= size + size * FEE
                        positions[market_id] = {'side': 'yes', 'entry': price, 'size': size, 'periods': 0}
                elif price > ENTRY_HIGH:
                    size = capital * POSITION_SIZE
                    if size > 10:
                        capital -= size + size * FEE
                        positions[market_id] = {'side': 'no', 'entry': price, 'size': size, 'periods': 0}
    
    # Calculate results
    final_capital = capital + sum(p['size'] for p in positions.values())
    total_return = (final_capital - initial_capital) / initial_capital
    
    wins = [t for t in trades if t['win']]
    losses = [t for t in trades if not t['win']]
    
    return {
        'period': period_name,
        'start': datetime.fromtimestamp(start_ts).strftime('%Y-%m-%d'),
        'end': datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d'),
        'data_points': len(period_df),
        'markets': period_df['market_id'].nunique(),
        'return': total_return,
        'trades': len(trades),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(trades) if trades else 0,
        'gross_profit': sum(t['pnl'] for t in wins),
        'gross_loss': sum(t['pnl'] for t in losses),
        'avg_win': np.mean([t['pnl'] for t in wins]) if wins else 0,
        'avg_loss': np.mean([t['pnl'] for t in losses]) if losses else 0,
    }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  TIME SPLIT BACKTEST                                                         ║
║  Testing strategy across different time periods                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    df = load_data()
    
    min_ts = df['timestamp'].min()
    max_ts = df['timestamp'].max()
    
    min_date = datetime.fromtimestamp(min_ts)
    max_date = datetime.fromtimestamp(max_ts)
    
    print(f"Full data range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    print(f"Total records: {len(df):,}")
    print()
    
    # Define time periods
    periods = []
    
    # Weekly splits
    week_start = datetime(2026, 1, 4)
    for i in range(5):
        start = week_start + timedelta(days=7*i)
        end = start + timedelta(days=7)
        periods.append({
            'name': f'Week {i+1}',
            'start': start.timestamp(),
            'end': end.timestamp()
        })
    
    # First half vs second half
    mid_ts = min_ts + (max_ts - min_ts) / 2
    periods.append({'name': 'First Half', 'start': min_ts, 'end': mid_ts})
    periods.append({'name': 'Second Half', 'start': mid_ts, 'end': max_ts})
    
    # Different market conditions (arbitrary splits for variety)
    third = (max_ts - min_ts) / 3
    periods.append({'name': 'Period 1/3', 'start': min_ts, 'end': min_ts + third})
    periods.append({'name': 'Period 2/3', 'start': min_ts + third, 'end': min_ts + 2*third})
    periods.append({'name': 'Period 3/3', 'start': min_ts + 2*third, 'end': max_ts})
    
    # Full period for comparison
    periods.append({'name': 'FULL PERIOD', 'start': min_ts, 'end': max_ts})
    
    print("Running backtest on each period...\n")
    
    results = []
    for p in periods:
        print(f"  {p['name']}...", end=" ", flush=True)
        result = run_backtest_on_period(df, p['start'], p['end'], p['name'])
        if result:
            results.append(result)
            print(f"{result['return']*100:+.2f}% ({result['trades']} trades)")
        else:
            print("No data")
    
    # Display results table
    print("\n" + "═"*100)
    print("  RESULTS BY TIME PERIOD")
    print("═"*100)
    print(f"{'Period':<15} {'Dates':<25} {'Return':>10} {'Trades':>8} {'Wins':>6} {'WinRate':>8} {'AvgWin':>10} {'AvgLoss':>10}")
    print("─"*100)
    
    for r in results:
        dates = f"{r['start']} to {r['end']}"
        print(f"{r['period']:<15} {dates:<25} {r['return']*100:>+9.2f}% {r['trades']:>8} {r['wins']:>6} {r['win_rate']*100:>7.1f}% ${r['avg_win']:>9.2f} ${r['avg_loss']:>9.2f}")
    
    print("═"*100)
    
    # Analysis
    print("\n" + "═"*100)
    print("  CONSISTENCY ANALYSIS")
    print("═"*100)
    
    # Exclude full period for analysis
    period_results = [r for r in results if r['period'] != 'FULL PERIOD']
    weekly_results = [r for r in results if r['period'].startswith('Week')]
    
    profitable_periods = [r for r in period_results if r['return'] > 0]
    losing_periods = [r for r in period_results if r['return'] <= 0]
    
    print(f"""
    Profitable periods: {len(profitable_periods)}/{len(period_results)}
    Losing periods:     {len(losing_periods)}/{len(period_results)}
    
    Weekly breakdown:
    """)
    
    for r in weekly_results:
        status = "✅" if r['return'] > 0 else "❌"
        print(f"      {status} {r['period']}: {r['return']*100:+.2f}%")
    
    # Check for consistency
    returns = [r['return'] for r in weekly_results if r['trades'] > 0]
    
    if returns:
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        print(f"""
    Weekly statistics:
      Mean return:   {avg_return*100:+.2f}%
      Std deviation: {std_return*100:.2f}%
      Best week:     {max(returns)*100:+.2f}%
      Worst week:    {min(returns)*100:+.2f}%
    """)
        
        # Verdict
        print("═"*100)
        print("  VERDICT")
        print("═"*100)
        
        if len(profitable_periods) >= len(period_results) * 0.6:
            if std_return < 0.30:
                print("""
    ✅ CONSISTENT EDGE
    
    Strategy is profitable across most time periods with reasonable variance.
    This suggests a real edge, not just lucky timing.
                """)
            else:
                print("""
    ⚠️ PROFITABLE BUT HIGH VARIANCE
    
    Strategy shows profit overall but with high variance across periods.
    Edge may be real but expect significant drawdowns.
                """)
        elif len(profitable_periods) >= len(period_results) * 0.4:
            print("""
    ⚠️ MIXED RESULTS
    
    Strategy profitable in some periods, losing in others.
    May be sensitive to market conditions.
    More data needed to confirm edge.
            """)
        else:
            print("""
    ❌ NOT CONSISTENT
    
    Strategy loses in most individual periods.
    Full-period profit may be due to a few lucky trades.
    Likely NOT a reliable edge.
            """)
    
    return results


if __name__ == "__main__":
    main()

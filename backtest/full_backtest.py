#!/usr/bin/env python3
"""
FULL BACKTEST - All Strategies Compared
Run every strategy, show honest results, find alpha (if any exists).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.engine import run_strategy, BacktestEngine
from backtest.strategies import STRATEGIES
from backtest.new_strategies import NEW_STRATEGIES


def run_all():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗  █████╗  ██████╗██╗  ██╗████████╗███████╗███████╗████████╗        ║
║   ██╔══██╗██╔══██╗██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝        ║
║   ██████╔╝███████║██║     █████╔╝    ██║   █████╗  ███████╗   ██║           ║
║   ██╔══██╗██╔══██║██║     ██╔═██╗    ██║   ██╔══╝  ╚════██║   ██║           ║
║   ██████╔╝██║  ██║╚██████╗██║  ██╗   ██║   ███████╗███████║   ██║           ║
║   ╚═════╝ ╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝   ╚═╝           ║
║                                                                              ║
║   Testing ALL strategies. No HFT. Human psychology edges only.               ║
║   If it doesn't show alpha here, it won't work in production.                ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Combine all strategies
    all_strategies = {}
    all_strategies.update(STRATEGIES)
    all_strategies.update(NEW_STRATEGIES)
    
    results = {}
    
    print(f"Testing {len(all_strategies)} strategies...\n")
    
    for name, strategy_fn in all_strategies.items():
        print(f"  ⏳ {name}...", end=" ", flush=True)
        
        try:
            result = run_strategy(strategy_fn)
            results[name] = result
            
            if result.total_trades > 0:
                print(f"✓ {result.total_trades} trades, {result.total_return*100:+.2f}%")
            else:
                print(f"○ No trades")
        except Exception as e:
            print(f"✗ Error: {e}")
            results[name] = None
    
    # Sort by Sharpe ratio (valid strategies first)
    valid_results = [(n, r) for n, r in results.items() if r and r.total_trades > 0]
    valid_results.sort(key=lambda x: x[1].sharpe_ratio if x[1].sharpe_ratio > -1000 else -9999, reverse=True)
    
    # Print comparison table
    print("\n" + "═"*90)
    print("  STRATEGY COMPARISON")
    print("═"*90)
    print(f"{'Strategy':<22} {'Return':>10} {'Sharpe':>10} {'MaxDD':>10} {'Trades':>8} {'WinRate':>8} {'Valid':>8}")
    print("─"*90)
    
    for name, result in valid_results:
        sharpe_str = f"{result.sharpe_ratio:.2f}" if abs(result.sharpe_ratio) < 1000 else "N/A"
        valid = "✅" if result.is_valid() else "❌"
        print(f"{name:<22} {result.total_return*100:>9.2f}% {sharpe_str:>10} {result.max_drawdown*100:>9.2f}% {result.total_trades:>8} {result.win_rate*100:>7.1f}% {valid:>8}")
    
    # Strategies with no trades
    no_trade_strategies = [n for n, r in results.items() if r and r.total_trades == 0]
    if no_trade_strategies:
        print("─"*90)
        print(f"No trades: {', '.join(no_trade_strategies)}")
    
    print("═"*90)
    
    # Detailed analysis of top performers
    print("\n\n📊 DETAILED ANALYSIS")
    print("═"*90)
    
    # Best by return
    if valid_results:
        best_return = max(valid_results, key=lambda x: x[1].total_return)
        print(f"\n🏆 BEST RETURN: {best_return[0]}")
        print(best_return[1])
    
    # Best by Sharpe (valid only)
    valid_sharpe = [(n, r) for n, r in valid_results if r.sharpe_ratio > 0 and abs(r.sharpe_ratio) < 100]
    if valid_sharpe:
        best_sharpe = max(valid_sharpe, key=lambda x: x[1].sharpe_ratio)
        if best_sharpe[0] != best_return[0]:
            print(f"\n🎯 BEST RISK-ADJUSTED: {best_sharpe[0]}")
            print(best_sharpe[1])
    
    # Valid strategies summary
    valid_strategies = [r for r in valid_results if r[1].is_valid()]
    
    print("\n\n" + "═"*90)
    print("  FINAL VERDICT")
    print("═"*90)
    
    if valid_strategies:
        print(f"""
✅ VALID STRATEGIES FOUND: {len(valid_strategies)}

Strategies that passed bullshit detection:
""")
        for name, result in valid_strategies:
            print(f"  • {name}: {result.total_return*100:+.2f}% return, {result.sharpe_ratio:.2f} Sharpe")
        
        print("""
RECOMMENDATION:
1. Paper trade the top strategy for 1 week
2. If results hold, start with 1% of intended capital
3. Scale up only if edge persists

⚠️  Past performance ≠ future results
⚠️  This is simulation, not real trading
""")
    else:
        print("""
❌ NO VALID STRATEGIES

All strategies either:
• Had zero trades (no signals in current data)
• Failed bullshit detection (curve fit, insufficient trades, etc.)
• Had negative expectancy

REASONS:
1. Insufficient historical data (need 24-48h minimum)
2. Market is efficient - no easy alpha
3. Strategy hypotheses don't match reality

RECOMMENDATION:
• Run collector for longer: nohup python main.py collect &
• Try again after 24-48 hours of data
• Consider different strategy hypotheses

The system is working correctly by NOT showing false alpha.
""")
    
    return results


if __name__ == "__main__":
    run_all()

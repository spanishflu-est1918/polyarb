#!/usr/bin/env python3
"""
Run backtests on all strategies.
Outputs honest, no-bullshit results.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.engine import run_strategy, BacktestEngine
from backtest.strategies import STRATEGIES


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  POLYARB BACKTESTING ENGINE                                      ║
║  "If it doesn't backtest, it doesn't trade"                      ║
╠══════════════════════════════════════════════════════════════════╣
║  Testing all strategies against historical data                  ║
║  With realistic fees, slippage, and bullshit detection           ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    results = {}
    
    for name, strategy_fn in STRATEGIES.items():
        print(f"\n{'='*60}")
        print(f"  Testing: {name.upper()}")
        print(f"{'='*60}")
        
        result = run_strategy(strategy_fn)
        results[name] = result
        print(result)
    
    # Summary comparison
    print("\n" + "="*70)
    print("  STRATEGY COMPARISON")
    print("="*70)
    print(f"{'Strategy':<20} {'Return':>10} {'Sharpe':>10} {'MaxDD':>10} {'Valid':>10}")
    print("-"*70)
    
    for name, result in sorted(results.items(), key=lambda x: x[1].sharpe_ratio, reverse=True):
        valid = "✅" if result.is_valid() else "❌"
        print(f"{name:<20} {result.total_return*100:>9.2f}% {result.sharpe_ratio:>10.2f} {result.max_drawdown*100:>9.2f}% {valid:>10}")
    
    print("-"*70)
    
    # Final recommendation
    valid_strategies = [r for r in results.values() if r.is_valid()]
    
    if not valid_strategies:
        print("""
⚠️  NO VALID STRATEGIES FOUND

All strategies failed bullshit detection. This means either:
1. Insufficient historical data (need more collection time)
2. No real alpha exists in current approach
3. Need different strategy hypotheses

RECOMMENDATION: Collect more data before trading real money.
        """)
    else:
        best = max(valid_strategies, key=lambda x: x.sharpe_ratio)
        print(f"""
✅ VALID STRATEGY FOUND

Best risk-adjusted strategy has:
- Sharpe Ratio: {best.sharpe_ratio:.2f}
- Max Drawdown: {best.max_drawdown*100:.2f}%
- Win Rate: {best.win_rate*100:.1f}%

RECOMMENDATION: Paper trade first, then small position sizes.
        """)


if __name__ == "__main__":
    main()

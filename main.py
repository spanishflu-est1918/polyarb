#!/usr/bin/env python3
"""
PolyArb - Polymarket Alpha Extraction System

Commands:
  collect   - Start data collection daemon
  scan      - One-time market scan  
  backtest  - Run backtests on all strategies
  analyze   - Analyze player/bot patterns
  status    - Check data collection status
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent


def print_banner():
    print("""
    ____        __      ___         __  
   / __ \\____  / /_  __/   |  _____/ /_ 
  / /_/ / __ \\/ / / / / /| | / ___/ __ \\
 / ____/ /_/ / / /_/ / ___ |/ /  / /_/ /
/_/    \\____/_/\\__, /_/  |_/_/  /_.___/ 
              /____/                     

  Polymarket Alpha Extraction System
  "Beat the market by understanding the players"
    """)


def cmd_collect():
    """Start data collection."""
    print("🔄 Starting data collector...")
    print("   Press Ctrl+C to stop\n")
    subprocess.run([sys.executable, str(ROOT / "collectors" / "polymarket_collector.py")])


def cmd_scan():
    """Run market scan."""
    subprocess.run(["node", str(ROOT / "src" / "scanner.js")])


def cmd_backtest():
    """Run backtests."""
    subprocess.run([sys.executable, str(ROOT / "backtest" / "run_backtest.py")])


def cmd_analyze():
    """Analyze player patterns."""
    subprocess.run([sys.executable, str(ROOT / "analysis" / "player_analysis.py")])


def cmd_status():
    """Check system status."""
    import sqlite3
    
    db_path = ROOT / "data" / "polymarket.db"
    
    print("📊 PolyArb Status")
    print("="*50)
    
    if not db_path.exists():
        print("❌ No database found. Run 'collect' first.")
        return
    
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # Snapshot count
    c.execute("SELECT COUNT(*) FROM price_snapshots")
    snapshots = c.fetchone()[0]
    
    # Market count
    c.execute("SELECT COUNT(DISTINCT market_id) FROM price_snapshots")
    markets = c.fetchone()[0]
    
    # Time range
    c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM price_snapshots")
    time_range = c.fetchone()
    
    print(f"   Database: {db_path}")
    print(f"   Snapshots: {snapshots:,}")
    print(f"   Markets tracked: {markets}")
    print(f"   Time range: {time_range[0]} to {time_range[1]}")
    
    # Recommendation
    if snapshots < 1000:
        print(f"\n⚠️  Need more data. Run collector for at least 24 hours.")
    elif snapshots < 10000:
        print(f"\n📈 Good start. More data = better backtests.")
    else:
        print(f"\n✅ Sufficient data for backtesting.")
    
    conn.close()


def main():
    print_banner()
    
    if len(sys.argv) < 2:
        print("Usage: python main.py <command>")
        print("")
        print("Commands:")
        print("  collect   - Start data collection (run 24/7)")
        print("  scan      - One-time arbitrage scan")
        print("  backtest  - Run strategy backtests")
        print("  analyze   - Analyze player/bot patterns")
        print("  status    - Check data collection status")
        return
    
    cmd = sys.argv[1].lower()
    
    commands = {
        'collect': cmd_collect,
        'scan': cmd_scan,
        'backtest': cmd_backtest,
        'analyze': cmd_analyze,
        'status': cmd_status,
    }
    
    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")
        return
    
    commands[cmd]()


if __name__ == "__main__":
    main()

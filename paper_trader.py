#!/usr/bin/env python3
"""
PAPER TRADER
Generate live signals, track paper positions, log everything.
Run hourly via cron.
"""

import json
import requests
import sqlite3
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
POSITIONS_FILE = DATA_DIR / "paper_positions.json"
TRADES_LOG = DATA_DIR / "paper_trades.log"
GAMMA_API = "https://gamma-api.polymarket.com"

# Strategy params (loose_stop - best performer)
ENTRY_LOW = 0.10
ENTRY_HIGH = 0.90
TAKE_PROFIT = 0.05
STOP_LOSS = 0.10  # Wider stop
MAX_HOLD_HOURS = 24
POSITION_SIZE = 200  # $200 per position (paper)
MAX_POSITIONS = 10


def log(msg):
    """Log to file and print."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(TRADES_LOG, "a") as f:
        f.write(line + "\n")


def load_positions():
    """Load current paper positions."""
    if POSITIONS_FILE.exists():
        return json.loads(POSITIONS_FILE.read_text())
    return {}


def save_positions(positions):
    """Save paper positions."""
    POSITIONS_FILE.write_text(json.dumps(positions, indent=2))


def fetch_prices():
    """Fetch current market prices."""
    try:
        resp = requests.get(f"{GAMMA_API}/markets", params={
            "closed": "false",
            "limit": 500
        }, timeout=30)
        
        if resp.status_code != 200:
            return {}
        
        markets = resp.json()
        prices = {}
        
        for m in markets:
            market_id = str(m.get('id', ''))
            question = m.get('question', '')[:50]
            
            raw_prices = m.get('outcomePrices', [])
            if isinstance(raw_prices, str):
                try:
                    raw_prices = json.loads(raw_prices)
                except:
                    continue
            
            if len(raw_prices) >= 2:
                prices[market_id] = {
                    'yes_price': float(raw_prices[0]),
                    'question': question
                }
        
        return prices
    except Exception as e:
        log(f"ERROR fetching prices: {e}")
        return {}


def check_exits(positions, prices):
    """Check for exit signals on existing positions."""
    exits = []
    now = datetime.now()
    
    for market_id, pos in list(positions.items()):
        if market_id not in prices:
            continue
        
        current_price = prices[market_id]['yes_price']
        entry_price = pos['entry_price']
        side = pos['side']
        entry_time = datetime.fromisoformat(pos['entry_time'])
        hours_held = (now - entry_time).total_seconds() / 3600
        
        # Calculate PnL
        if side == 'yes':
            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        else:
            entry_no = 1 - entry_price
            current_no = 1 - current_price
            pnl_pct = (current_no - entry_no) / entry_no if entry_no > 0 else 0
        
        pnl_usd = POSITION_SIZE * pnl_pct
        
        # Check exit conditions
        reason = None
        if pnl_pct >= TAKE_PROFIT:
            reason = 'PROFIT'
        elif pnl_pct <= -STOP_LOSS:
            reason = 'STOP'
        elif hours_held >= MAX_HOLD_HOURS:
            reason = 'TIMEOUT'
        
        if reason:
            exits.append({
                'market_id': market_id,
                'question': pos['question'],
                'side': side,
                'entry_price': entry_price,
                'exit_price': current_price,
                'pnl_pct': pnl_pct,
                'pnl_usd': pnl_usd,
                'reason': reason,
                'hours_held': hours_held
            })
            del positions[market_id]
    
    return exits


def check_entries(positions, prices):
    """Check for entry signals."""
    entries = []
    
    if len(positions) >= MAX_POSITIONS:
        return entries
    
    for market_id, data in prices.items():
        if market_id in positions:
            continue
        
        if len(positions) + len(entries) >= MAX_POSITIONS:
            break
        
        price = data['yes_price']
        question = data['question']
        
        side = None
        if price < ENTRY_LOW:
            side = 'yes'
        elif price > ENTRY_HIGH:
            side = 'no'
        
        if side:
            entries.append({
                'market_id': market_id,
                'question': question,
                'side': side,
                'entry_price': price,
                'entry_time': datetime.now().isoformat()
            })
    
    return entries


def run():
    """Run one iteration of paper trading."""
    log("="*60)
    log("PAPER TRADER RUN")
    log("="*60)
    
    # Load state
    positions = load_positions()
    log(f"Current positions: {len(positions)}")
    
    # Fetch prices
    prices = fetch_prices()
    log(f"Markets fetched: {len(prices)}")
    
    if not prices:
        log("No prices fetched, aborting")
        return
    
    # Check exits
    exits = check_exits(positions, prices)
    for ex in exits:
        win_loss = "WIN" if ex['pnl_usd'] > 0 else "LOSS"
        log(f"EXIT ({win_loss}): {ex['question']}")
        log(f"  {ex['side'].upper()} @ {ex['entry_price']:.4f} → {ex['exit_price']:.4f}")
        log(f"  PnL: ${ex['pnl_usd']:+.2f} ({ex['pnl_pct']*100:+.1f}%) | {ex['reason']} after {ex['hours_held']:.1f}h")
    
    # Check entries
    entries = check_entries(positions, prices)
    for en in entries:
        log(f"ENTRY: {en['question']}")
        log(f"  {en['side'].upper()} @ {en['entry_price']:.4f}")
        positions[en['market_id']] = en
    
    # Save state
    save_positions(positions)
    
    # Summary
    total_entries = len(entries)
    total_exits = len(exits)
    total_pnl = sum(ex['pnl_usd'] for ex in exits)
    
    log("-"*60)
    log(f"SUMMARY: {total_entries} entries, {total_exits} exits, PnL: ${total_pnl:+.2f}")
    log(f"Open positions: {len(positions)}")
    
    # Show open positions
    for mid, pos in positions.items():
        if mid in prices:
            current = prices[mid]['yes_price']
            entry = pos['entry_price']
            if pos['side'] == 'yes':
                pnl_pct = (current - entry) / entry if entry > 0 else 0
            else:
                pnl_pct = ((1-current) - (1-entry)) / (1-entry) if (1-entry) > 0 else 0
            log(f"  {pos['question'][:40]}: {pnl_pct*100:+.1f}%")


if __name__ == "__main__":
    run()

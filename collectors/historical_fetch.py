#!/usr/bin/env python3
"""
HISTORICAL DATA FETCHER
Pull 30 days of price history from Polymarket CLOB API.
"""

import sqlite3
import requests
import json
import time
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"


def init_historical_table(conn):
    """Create table for historical prices."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market_id TEXT,
            token_id TEXT,
            timestamp INTEGER,
            yes_price REAL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(market_id, timestamp)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_market ON historical_prices(market_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_time ON historical_prices(timestamp)")
    conn.commit()


def fetch_markets():
    """Get markets with volume > $100k."""
    resp = requests.get(f"{GAMMA_API}/markets", params={
        'limit': 500,
        'closed': 'false'
    })
    
    if resp.status_code != 200:
        print(f"Error fetching markets: {resp.status_code}")
        return []
    
    markets = resp.json()
    
    # Filter for liquid markets
    liquid = []
    for m in markets:
        volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
        if volume > 100000:
            clob_ids = m.get('clobTokenIds', '[]')
            if isinstance(clob_ids, str):
                clob_ids = json.loads(clob_ids)
            
            if clob_ids:
                liquid.append({
                    'id': m.get('id'),
                    'question': m.get('question', '')[:60],
                    'token_id': clob_ids[0],  # YES token
                    'volume': volume
                })
    
    return liquid


def fetch_price_history(token_id: str) -> list:
    """Fetch price history for a token."""
    url = f"{CLOB_API}/prices-history"
    params = {
        'market': token_id,
        'interval': 'max',
        'fidelity': '60'  # 60 minute intervals
    }
    
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('history', [])
    except Exception as e:
        print(f"  Error: {e}")
    
    return []


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║  HISTORICAL DATA FETCHER                                                     ║
║  Pulling 30 days of price history from Polymarket                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    conn = sqlite3.connect(DB_PATH)
    init_historical_table(conn)
    
    print("Fetching liquid markets...")
    markets = fetch_markets()
    print(f"Found {len(markets)} markets with volume > $100k\n")
    
    total_points = 0
    
    for i, m in enumerate(markets, 1):
        print(f"[{i}/{len(markets)}] {m['question']}")
        print(f"  Volume: ${m['volume']:,.0f}")
        
        history = fetch_price_history(m['token_id'])
        print(f"  History: {len(history)} points")
        
        if history:
            # Insert into database
            for point in history:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO historical_prices 
                        (market_id, token_id, timestamp, yes_price)
                        VALUES (?, ?, ?, ?)
                    """, (m['id'], m['token_id'], point['t'], point['p']))
                except Exception as e:
                    pass
            
            conn.commit()
            total_points += len(history)
            
            # Show date range
            t1 = datetime.fromtimestamp(history[0]['t'])
            t2 = datetime.fromtimestamp(history[-1]['t'])
            print(f"  Range: {t1.strftime('%Y-%m-%d')} to {t2.strftime('%Y-%m-%d')}")
        
        print()
        
        # Rate limit
        time.sleep(0.2)
    
    # Summary
    result = conn.execute("SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM historical_prices").fetchone()
    
    print("=" * 70)
    print(f"TOTAL: {result[0]:,} historical price points")
    
    if result[1] and result[2]:
        t1 = datetime.fromtimestamp(result[1])
        t2 = datetime.fromtimestamp(result[2])
        print(f"RANGE: {t1.strftime('%Y-%m-%d %H:%M')} to {t2.strftime('%Y-%m-%d %H:%M')}")
        print(f"SPAN:  {(t2-t1).days} days")
    
    conn.close()
    
    return total_points


if __name__ == "__main__":
    main()

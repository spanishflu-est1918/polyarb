#!/usr/bin/env python3
"""
Polymarket Data Collector
Captures price, volume, and order book snapshots for backtesting.
Run continuously to build historical dataset.
"""

import os
import json
import time
import sqlite3
import requests
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"
GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Collection interval in seconds
SNAPSHOT_INTERVAL = 60  # 1 minute
ORDERBOOK_INTERVAL = 300  # 5 minutes (heavier call)

def init_db():
    """Initialize SQLite database with proper schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Markets metadata
    c.execute('''
        CREATE TABLE IF NOT EXISTS markets (
            id TEXT PRIMARY KEY,
            question TEXT,
            description TEXT,
            outcomes TEXT,  -- JSON array
            end_date TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # Price snapshots (core data for backtesting)
    c.execute('''
        CREATE TABLE IF NOT EXISTS price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            market_id TEXT NOT NULL,
            yes_price REAL,
            no_price REAL,
            yes_bid REAL,
            yes_ask REAL,
            no_bid REAL,
            no_ask REAL,
            spread REAL,
            volume_24h REAL,
            liquidity REAL,
            UNIQUE(timestamp, market_id)
        )
    ''')
    
    # Order book snapshots (for depth analysis)
    c.execute('''
        CREATE TABLE IF NOT EXISTS orderbook_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            market_id TEXT NOT NULL,
            side TEXT NOT NULL,  -- 'yes' or 'no'
            bids TEXT,  -- JSON [[price, size], ...]
            asks TEXT,  -- JSON [[price, size], ...]
            bid_depth REAL,  -- Total bid liquidity
            ask_depth REAL,  -- Total ask liquidity
            UNIQUE(timestamp, market_id, side)
        )
    ''')
    
    # Trade events (for flow analysis)
    c.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            market_id TEXT NOT NULL,
            side TEXT,  -- 'buy' or 'sell'
            outcome TEXT,  -- 'yes' or 'no'
            price REAL,
            size REAL,
            maker TEXT,  -- wallet address
            taker TEXT
        )
    ''')
    
    # Indexes for fast queries
    c.execute('CREATE INDEX IF NOT EXISTS idx_prices_time ON price_snapshots(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_prices_market ON price_snapshots(market_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_time ON trades(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_trades_market ON trades(market_id)')
    
    conn.commit()
    return conn


def fetch_markets():
    """Fetch all active markets."""
    try:
        resp = requests.get(f"{GAMMA_API}/markets", params={"closed": "false", "limit": 500})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Failed to fetch markets: {e}")
        return []


def fetch_orderbook(token_id):
    """Fetch order book for a token."""
    try:
        resp = requests.get(f"{CLOB_API}/book", params={"token_id": token_id})
        resp.raise_for_status()
        return resp.json()
    except:
        return {"bids": [], "asks": []}


def parse_prices(market):
    """Extract prices from market data."""
    try:
        prices = market.get("outcomePrices", [])
        if isinstance(prices, str):
            prices = json.loads(prices)
        
        yes_price = float(prices[0]) if len(prices) > 0 else None
        no_price = float(prices[1]) if len(prices) > 1 else None
        
        return yes_price, no_price
    except:
        return None, None


def collect_snapshot(conn, markets):
    """Collect price snapshot for all markets."""
    timestamp = datetime.now(timezone.utc).isoformat()
    c = conn.cursor()
    
    collected = 0
    for market in markets:
        market_id = market.get("id") or market.get("conditionId")
        if not market_id:
            continue
        
        yes_price, no_price = parse_prices(market)
        if yes_price is None:
            continue
        
        # Calculate spread
        spread = abs(1 - (yes_price + no_price)) if yes_price and no_price else None
        
        # Volume and liquidity
        volume = float(market.get("volume", 0) or market.get("volumeNum", 0) or 0)
        liquidity = float(market.get("liquidity", 0) or 0)
        
        try:
            c.execute('''
                INSERT OR REPLACE INTO price_snapshots 
                (timestamp, market_id, yes_price, no_price, spread, volume_24h, liquidity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (timestamp, market_id, yes_price, no_price, spread, volume, liquidity))
            collected += 1
        except Exception as e:
            print(f"[WARN] Failed to insert snapshot for {market_id}: {e}")
    
    conn.commit()
    return collected


def update_markets_metadata(conn, markets):
    """Update markets table with metadata."""
    c = conn.cursor()
    
    for market in markets:
        market_id = market.get("id") or market.get("conditionId")
        if not market_id:
            continue
        
        c.execute('''
            INSERT OR REPLACE INTO markets (id, question, description, outcomes, end_date, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            market_id,
            market.get("question", ""),
            market.get("description", ""),
            json.dumps(market.get("outcomes", [])),
            market.get("endDate"),
            datetime.now(timezone.utc).isoformat()
        ))
    
    conn.commit()


def collector_loop():
    """Main collection loop."""
    print("=" * 60)
    print("  POLYMARKET DATA COLLECTOR")
    print("  Building historical dataset for backtesting")
    print("=" * 60)
    print(f"  Database: {DB_PATH}")
    print(f"  Snapshot interval: {SNAPSHOT_INTERVAL}s")
    print("=" * 60)
    
    conn = init_db()
    last_metadata_update = 0
    
    while True:
        try:
            now = time.time()
            
            # Fetch markets
            markets = fetch_markets()
            if not markets:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No markets fetched, retrying...")
                time.sleep(30)
                continue
            
            # Update metadata every hour
            if now - last_metadata_update > 3600:
                update_markets_metadata(conn, markets)
                last_metadata_update = now
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated metadata for {len(markets)} markets")
            
            # Collect price snapshot
            collected = collect_snapshot(conn, markets)
            
            # Stats
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM price_snapshots")
            total_snapshots = c.fetchone()[0]
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Collected {collected} snapshots (total: {total_snapshots})")
            
        except Exception as e:
            print(f"[ERROR] Collection failed: {e}")
        
        time.sleep(SNAPSHOT_INTERVAL)


if __name__ == "__main__":
    collector_loop()

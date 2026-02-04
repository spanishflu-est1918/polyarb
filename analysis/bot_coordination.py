#!/usr/bin/env python3
"""
BOT COORDINATION DETECTOR
Find where bots are crowding. Take the other side.

Insight: When multiple bots coordinate on the same trade,
they create temporary mispricings. Fade the coordination.

Signals of bot coordination:
1. Price moves without proportional volume
2. Uniform moves across correlated markets  
3. Spreads tightening then snapping (liquidity games)
4. Time-based patterns (bots run on schedules)
5. Order flow imbalances
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Tuple
import requests
import json

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"
GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class CoordinationSignal:
    """Detected bot coordination pattern."""
    market_id: str
    market_name: str
    signal_type: str
    strength: float  # 0-1
    bot_direction: str  # 'long' or 'short' (what bots are doing)
    fade_direction: str  # opposite of bot_direction
    timestamp: datetime
    evidence: str
    confidence: float
    expected_reversion: float  # % expected fade


class BotCoordinationDetector:
    """
    Detect coordinated bot activity and generate fade signals.
    """
    
    def __init__(self):
        self.signals: List[CoordinationSignal] = []
    
    def fetch_market_data(self) -> pd.DataFrame:
        """Fetch current market data for analysis."""
        try:
            resp = requests.get(f"{GAMMA_API}/markets", params={
                "closed": "false", 
                "limit": 500
            })
            markets = resp.json() if resp.status_code == 200 else []
            
            data = []
            for m in markets:
                prices = m.get('outcomePrices', [])
                if isinstance(prices, str):
                    try:
                        prices = json.loads(prices)
                    except:
                        continue
                
                if len(prices) >= 2:
                    data.append({
                        'market_id': m.get('id', m.get('conditionId')),
                        'question': m.get('question', '')[:60],
                        'yes_price': float(prices[0]),
                        'no_price': float(prices[1]),
                        'volume': float(m.get('volume', 0) or m.get('volumeNum', 0) or 0),
                        'liquidity': float(m.get('liquidity', 0) or 0),
                        'spread': abs(1 - float(prices[0]) - float(prices[1])),
                        'category': m.get('category', ''),
                    })
            
            return pd.DataFrame(data)
        except Exception as e:
            print(f"Error fetching data: {e}")
            return pd.DataFrame()
    
    def detect_price_clustering(self, df: pd.DataFrame) -> List[CoordinationSignal]:
        """
        Detect suspicious price clustering.
        
        When many markets cluster at same price levels,
        bots are likely coordinating rebalancing.
        """
        signals = []
        
        # Check for clustering at round numbers
        round_levels = [0.10, 0.15, 0.20, 0.25, 0.30, 0.33, 0.40, 0.50, 
                       0.60, 0.67, 0.70, 0.75, 0.80, 0.85, 0.90]
        
        for level in round_levels:
            # Count markets within 1% of this level
            near_level = df[abs(df['yes_price'] - level) < 0.01]
            
            if len(near_level) > 5:  # Unusual clustering
                cluster_pct = len(near_level) / len(df)
                
                if cluster_pct > 0.03:  # More than 3% at same level
                    # Bots are holding this level - expect breakout
                    for _, row in near_level.iterrows():
                        # Fade toward center (0.50)
                        if level < 0.50:
                            fade_dir = 'yes'  # Price too low, fade up
                            bot_dir = 'short'
                        else:
                            fade_dir = 'no'  # Price too high, fade down
                            bot_dir = 'long'
                        
                        signals.append(CoordinationSignal(
                            market_id=row['market_id'],
                            market_name=row['question'],
                            signal_type='PRICE_CLUSTERING',
                            strength=cluster_pct * 10,
                            bot_direction=bot_dir,
                            fade_direction=fade_dir,
                            timestamp=datetime.now(),
                            evidence=f"{len(near_level)} markets clustered at {level:.0%}",
                            confidence=min(0.6, cluster_pct * 5),
                            expected_reversion=0.03
                        ))
        
        return signals
    
    def detect_spread_anomalies(self, df: pd.DataFrame) -> List[CoordinationSignal]:
        """
        Detect spread anomalies indicating bot games.
        
        Very tight spreads = bots competing aggressively
        When they all pull back, spread widens → opportunity
        """
        signals = []
        
        avg_spread = df['spread'].mean()
        std_spread = df['spread'].std()
        
        # Abnormally tight spreads (bots competing)
        tight = df[df['spread'] < avg_spread - std_spread]
        
        for _, row in tight.iterrows():
            if row['volume'] > 100000:  # Only liquid markets
                signals.append(CoordinationSignal(
                    market_id=row['market_id'],
                    market_name=row['question'],
                    signal_type='TIGHT_SPREAD',
                    strength=0.5,
                    bot_direction='neutral',  # Bots making market
                    fade_direction='wait',  # Wait for spread to widen
                    timestamp=datetime.now(),
                    evidence=f"Spread {row['spread']:.4f} vs avg {avg_spread:.4f}",
                    confidence=0.4,
                    expected_reversion=0.02
                ))
        
        # Abnormally wide spreads (bots pulled liquidity)
        wide = df[df['spread'] > avg_spread + 2*std_spread]
        
        for _, row in wide.iterrows():
            if row['volume'] > 50000:
                # Wide spread = uncertainty. Bots are unsure.
                # This is actually when edge exists (if you know something)
                signals.append(CoordinationSignal(
                    market_id=row['market_id'],
                    market_name=row['question'],
                    signal_type='WIDE_SPREAD',
                    strength=0.7,
                    bot_direction='uncertain',
                    fade_direction='research',  # Need info edge here
                    timestamp=datetime.now(),
                    evidence=f"Spread {row['spread']:.4f} is 2σ above avg",
                    confidence=0.5,
                    expected_reversion=0.05
                ))
        
        return signals
    
    def detect_volume_price_divergence(self, df: pd.DataFrame) -> List[CoordinationSignal]:
        """
        Detect when price moved without volume.
        
        Price move + low volume = bots manipulating
        Real moves have volume. Fake moves fade.
        """
        signals = []
        
        # Need historical comparison
        # For now, use liquidity as proxy
        df['price_extremity'] = abs(df['yes_price'] - 0.5) / 0.5
        df['vol_normalized'] = df['volume'] / (df['volume'].mean() + 1)
        
        # High price extremity + low relative volume = suspicious
        suspicious = df[
            (df['price_extremity'] > 0.6) &  # Price far from 50%
            (df['vol_normalized'] < 0.5)  # Below average volume
        ]
        
        for _, row in suspicious.iterrows():
            # Price is extreme but volume is low - likely bot manipulation
            if row['yes_price'] > 0.80:
                fade_dir = 'no'  # Fade the high price
                bot_dir = 'long'
            elif row['yes_price'] < 0.20:
                fade_dir = 'yes'  # Fade the low price
                bot_dir = 'short'
            else:
                continue
            
            signals.append(CoordinationSignal(
                market_id=row['market_id'],
                market_name=row['question'],
                signal_type='VOLUME_DIVERGENCE',
                strength=row['price_extremity'],
                bot_direction=bot_dir,
                fade_direction=fade_dir,
                timestamp=datetime.now(),
                evidence=f"Price {row['yes_price']:.0%} but only {row['vol_normalized']:.1f}x avg volume",
                confidence=0.5,
                expected_reversion=0.05
            ))
        
        return signals
    
    def detect_correlated_moves(self, df: pd.DataFrame) -> List[CoordinationSignal]:
        """
        Detect coordinated moves across related markets.
        
        If multiple markets in same category move together,
        bots are rebalancing. Fade the laggard.
        """
        signals = []
        
        # Group by rough category (from question keywords)
        categories = {}
        
        keywords = {
            'politics': ['trump', 'biden', 'election', 'president', 'senate', 'congress'],
            'crypto': ['bitcoin', 'btc', 'ethereum', 'eth', 'crypto'],
            'sports': ['nfl', 'nba', 'super bowl', 'championship', 'finals'],
            'tech': ['ai', 'openai', 'google', 'apple', 'tesla'],
        }
        
        for _, row in df.iterrows():
            q = row['question'].lower()
            for cat, kws in keywords.items():
                if any(kw in q for kw in kws):
                    if cat not in categories:
                        categories[cat] = []
                    categories[cat].append(row)
                    break
        
        # For each category, check for uniform pricing
        for cat, markets in categories.items():
            if len(markets) < 3:
                continue
            
            prices = [m['yes_price'] for m in markets]
            price_std = np.std(prices)
            
            # Very low variance = bots coordinating prices
            if price_std < 0.05 and len(markets) >= 5:
                avg_price = np.mean(prices)
                
                # Find the outliers (laggards)
                for m in markets:
                    deviation = m['yes_price'] - avg_price
                    
                    if abs(deviation) > price_std * 2:
                        # This market is the outlier - expect mean reversion
                        fade_dir = 'no' if deviation > 0 else 'yes'
                        bot_dir = 'long' if deviation > 0 else 'short'
                        
                        signals.append(CoordinationSignal(
                            market_id=m['market_id'],
                            market_name=m['question'],
                            signal_type='CORRELATED_OUTLIER',
                            strength=abs(deviation) / 0.1,
                            bot_direction=bot_dir,
                            fade_direction=fade_dir,
                            timestamp=datetime.now(),
                            evidence=f"Outlier in {cat}: {m['yes_price']:.0%} vs category avg {avg_price:.0%}",
                            confidence=0.6,
                            expected_reversion=abs(deviation)
                        ))
        
        return signals
    
    def find_fade_opportunities(self) -> Dict:
        """
        Run all detection methods and compile fade opportunities.
        """
        print("📊 Fetching market data...")
        df = self.fetch_market_data()
        
        if df.empty:
            return {'error': 'No data available'}
        
        print(f"   Analyzing {len(df)} markets\n")
        
        all_signals = []
        
        print("🎯 Detecting price clustering...")
        clustering = self.detect_price_clustering(df)
        print(f"   Found {len(clustering)} clustering signals")
        all_signals.extend(clustering)
        
        print("📏 Detecting spread anomalies...")
        spreads = self.detect_spread_anomalies(df)
        print(f"   Found {len(spreads)} spread anomaly signals")
        all_signals.extend(spreads)
        
        print("📉 Detecting volume/price divergence...")
        divergence = self.detect_volume_price_divergence(df)
        print(f"   Found {len(divergence)} divergence signals")
        all_signals.extend(divergence)
        
        print("🔗 Detecting correlated moves...")
        correlated = self.detect_correlated_moves(df)
        print(f"   Found {len(correlated)} correlation signals")
        all_signals.extend(correlated)
        
        # Dedupe and sort by confidence
        seen = set()
        unique = []
        for s in all_signals:
            if s.market_id not in seen:
                seen.add(s.market_id)
                unique.append(s)
        
        unique.sort(key=lambda x: x.confidence, reverse=True)
        
        # Separate actionable from informational
        actionable = [s for s in unique if s.fade_direction in ['yes', 'no']]
        informational = [s for s in unique if s.fade_direction in ['wait', 'research', 'neutral', 'uncertain']]
        
        return {
            'total_signals': len(unique),
            'actionable': actionable,
            'informational': informational,
            'by_type': {
                'clustering': len(clustering),
                'spread': len(spreads),
                'divergence': len(divergence),
                'correlated': len(correlated)
            }
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗  ██████╗ ████████╗    ███████╗ █████╗ ██████╗ ███████╗            ║
║   ██╔══██╗██╔═══██╗╚══██╔══╝    ██╔════╝██╔══██╗██╔══██╗██╔════╝            ║
║   ██████╔╝██║   ██║   ██║       █████╗  ███████║██║  ██║█████╗              ║
║   ██╔══██╗██║   ██║   ██║       ██╔══╝  ██╔══██║██║  ██║██╔══╝              ║
║   ██████╔╝╚██████╔╝   ██║       ██║     ██║  ██║██████╔╝███████╗            ║
║   ╚═════╝  ╚═════╝    ╚═╝       ╚═╝     ╚═╝  ╚═╝╚═════╝ ╚══════╝            ║
║                                                                              ║
║   Detect bot coordination. Take the other side.                              ║
║   When everyone zigs, you zag.                                               ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    detector = BotCoordinationDetector()
    results = detector.find_fade_opportunities()
    
    if 'error' in results:
        print(f"❌ {results['error']}")
        return
    
    print("\n" + "═"*80)
    print("  COORDINATION DETECTION RESULTS")
    print("═"*80)
    print(f"""
   Total Signals: {results['total_signals']}
   Actionable:    {len(results['actionable'])}
   Informational: {len(results['informational'])}
   
   By Type:
   ├─ Price Clustering:    {results['by_type']['clustering']}
   ├─ Spread Anomalies:    {results['by_type']['spread']}
   ├─ Volume Divergence:   {results['by_type']['divergence']}
   └─ Correlated Moves:    {results['by_type']['correlated']}
    """)
    
    if results['actionable']:
        print("\n" + "─"*80)
        print("  🎯 ACTIONABLE FADE SIGNALS")
        print("─"*80)
        
        for i, sig in enumerate(results['actionable'][:10], 1):
            print(f"""
#{i} {sig.market_name}
    Signal: {sig.signal_type}
    Bot Direction: {sig.bot_direction.upper()}
    → FADE: {sig.fade_direction.upper()}
    Confidence: {sig.confidence:.0%}
    Expected Reversion: {sig.expected_reversion:.1%}
    Evidence: {sig.evidence}
""")
    
    if results['informational']:
        print("\n" + "─"*80)
        print("  📊 INFORMATIONAL SIGNALS (need more research)")
        print("─"*80)
        
        for sig in results['informational'][:5]:
            print(f"   • {sig.market_name[:50]}: {sig.signal_type} - {sig.evidence[:40]}")
    
    print("\n" + "═"*80)
    print("  BOT FADE STRATEGY")
    print("═"*80)
    print("""
   The Math:
   ─────────
   Bots coordinate → temporary mispricing → fade opportunity
   
   Position Sizing:
   ─────────────────
   High confidence (>60%): 1% of bankroll
   Medium confidence (40-60%): 0.5% of bankroll
   Low confidence (<40%): Skip or 0.25%
   
   Risk Management:
   ────────────────
   Stop loss: 5% adverse move
   Take profit: Expected reversion reached
   Max positions: 10 concurrent
   
   Expected Edge:
   ─────────────
   If bots coordinate 30% of the time,
   and we correctly identify 50% of those,
   and fade works 60% when we identify correctly:
   
   Net edge ≈ 0.30 × 0.50 × 0.60 = 9% of opportunities
   
   ⚠️  This is adversarial trading
   ⚠️  Bots adapt - edge decays
   ⚠️  Paper trade first
    """)
    
    return results


if __name__ == "__main__":
    main()

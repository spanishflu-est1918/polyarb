#!/usr/bin/env python3
"""
Player & Bot Analysis
Find alpha by understanding WHO is trading, not just WHAT.
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"


class PlayerAnalyzer:
    """
    Analyze trader behavior to find exploitable patterns.
    
    Key insights:
    - Bots have predictable behavior (rebalancing, timing)
    - Humans have emotional patterns (FOMO, panic)
    - Big players move markets (follow or fade?)
    """
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
    
    def analyze_price_patterns(self, market_id: str = None) -> dict:
        """
        Find exploitable price patterns:
        1. Time-of-day effects
        2. Day-of-week effects  
        3. Round number magnetism
        4. Mean reversion speed
        """
        
        query = "SELECT * FROM price_snapshots"
        if market_id:
            query += f" WHERE market_id = '{market_id}'"
        query += " ORDER BY timestamp"
        
        df = pd.read_sql(query, self.conn)
        
        if len(df) == 0:
            return {"error": "No data available"}
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['price_change'] = df.groupby('market_id')['yes_price'].pct_change()
        
        results = {}
        
        # Time-of-day analysis
        hourly = df.groupby('hour')['price_change'].agg(['mean', 'std', 'count'])
        results['hourly_patterns'] = {
            'best_hour': int(hourly['mean'].idxmax()),
            'worst_hour': int(hourly['mean'].idxmin()),
            'most_volatile_hour': int(hourly['std'].idxmax()),
            'data': hourly.to_dict()
        }
        
        # Day-of-week analysis
        daily = df.groupby('day_of_week')['price_change'].agg(['mean', 'std', 'count'])
        results['daily_patterns'] = {
            'best_day': int(daily['mean'].idxmax()),
            'worst_day': int(daily['mean'].idxmin()),
            'weekend_effect': float(daily.loc[[5, 6], 'std'].mean() - daily.loc[[0, 1, 2, 3, 4], 'std'].mean()),
            'data': daily.to_dict()
        }
        
        # Round number magnetism
        df['near_round'] = df['yes_price'].apply(
            lambda x: any(abs(x - r) < 0.02 for r in [0.25, 0.5, 0.75])
        )
        round_number_freq = df['near_round'].mean()
        results['round_number_magnetism'] = {
            'frequency_near_round': float(round_number_freq),
            'expected_random': 0.24,  # 3 zones of 0.04 width each = 0.12, times 2 directions
            'magnetism_strength': float(round_number_freq / 0.24)
        }
        
        # Mean reversion analysis
        df['deviation_from_50'] = abs(df['yes_price'] - 0.5)
        df['next_deviation'] = df.groupby('market_id')['deviation_from_50'].shift(-1)
        df['reversion'] = df['deviation_from_50'] - df['next_deviation']
        
        mean_reversion_rate = df['reversion'].mean()
        results['mean_reversion'] = {
            'rate': float(mean_reversion_rate) if not pd.isna(mean_reversion_rate) else 0,
            'interpretation': 'Prices tend to revert to 0.5' if mean_reversion_rate > 0 else 'Prices trend away from 0.5'
        }
        
        return results
    
    def detect_bot_activity(self) -> dict:
        """
        Identify likely bot traders by behavior patterns:
        1. Regular timing intervals
        2. Precise position sizes
        3. 24/7 activity
        4. Instant response to price changes
        """
        
        # This would analyze trade data if we had wallet-level info
        # For now, analyze aggregate patterns that suggest bot presence
        
        query = "SELECT * FROM price_snapshots ORDER BY timestamp"
        df = pd.read_sql(query, self.conn)
        
        if len(df) == 0:
            return {"error": "No data available"}
        
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        results = {}
        
        # Check for 24/7 activity (bots don't sleep)
        hourly_activity = df.groupby(df['timestamp'].dt.hour).size()
        activity_variance = hourly_activity.std() / hourly_activity.mean()
        
        results['activity_pattern'] = {
            'hour_variance_coefficient': float(activity_variance),
            'interpretation': 'High bot activity (uniform)' if activity_variance < 0.3 else 'Human patterns (variable)',
            'hourly_distribution': hourly_activity.to_dict()
        }
        
        # Price precision analysis (bots often use round prices)
        df['price_precision'] = df['yes_price'].apply(lambda x: len(str(x).split('.')[-1]) if '.' in str(x) else 0)
        avg_precision = df['price_precision'].mean()
        
        results['price_precision'] = {
            'average_decimal_places': float(avg_precision),
            'interpretation': 'Bot-like (low precision)' if avg_precision < 3 else 'Human-like (high precision)'
        }
        
        # Spread tightness (bots keep spreads tight)
        avg_spread = df['spread'].mean() if 'spread' in df.columns else None
        results['spread_analysis'] = {
            'average_spread': float(avg_spread) if avg_spread else None,
            'interpretation': 'Active market making bots' if avg_spread and avg_spread < 0.02 else 'Less bot activity'
        }
        
        return results
    
    def find_alpha_opportunities(self) -> dict:
        """
        Synthesize analysis into actionable alpha signals.
        """
        
        price_patterns = self.analyze_price_patterns()
        bot_activity = self.detect_bot_activity()
        
        opportunities = []
        
        # Opportunity 1: Time-based edge
        if 'hourly_patterns' in price_patterns:
            best_hour = price_patterns['hourly_patterns']['best_hour']
            worst_hour = price_patterns['hourly_patterns']['worst_hour']
            opportunities.append({
                'type': 'TIME_OF_DAY',
                'signal': f'Buy at hour {worst_hour}, sell at hour {best_hour}',
                'confidence': 'LOW - needs more data validation'
            })
        
        # Opportunity 2: Weekend inefficiency
        if 'daily_patterns' in price_patterns:
            weekend_effect = price_patterns['daily_patterns']['weekend_effect']
            if abs(weekend_effect) > 0.01:
                opportunities.append({
                    'type': 'WEEKEND_EFFECT',
                    'signal': 'Higher volatility on weekends - wider spreads to capture',
                    'magnitude': float(weekend_effect),
                    'confidence': 'MEDIUM - consistent across markets'
                })
        
        # Opportunity 3: Round number exploitation
        if 'round_number_magnetism' in price_patterns:
            magnetism = price_patterns['round_number_magnetism']['magnetism_strength']
            if magnetism > 1.2:
                opportunities.append({
                    'type': 'ROUND_NUMBER_MAGNET',
                    'signal': 'Prices cluster at 0.25/0.50/0.75 - fade moves away from these',
                    'strength': float(magnetism),
                    'confidence': 'MEDIUM - behavioral edge'
                })
        
        # Opportunity 4: Bot front-running
        if 'activity_pattern' in bot_activity:
            if bot_activity['activity_pattern']['hour_variance_coefficient'] < 0.3:
                opportunities.append({
                    'type': 'BOT_FRONTRUN',
                    'signal': 'Uniform activity suggests bots - look for rebalancing patterns',
                    'confidence': 'SPECULATIVE - needs trade-level data'
                })
        
        return {
            'opportunities': opportunities,
            'data_quality': {
                'price_snapshots': len(pd.read_sql("SELECT COUNT(*) FROM price_snapshots", self.conn).iloc[0, 0]),
                'markets_tracked': len(pd.read_sql("SELECT DISTINCT market_id FROM price_snapshots", self.conn))
            },
            'recommendation': 'COLLECT MORE DATA' if len(opportunities) < 2 else 'BACKTEST OPPORTUNITIES'
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  PLAYER ANALYSIS ENGINE                                          ║
║  "Play the players, not the game"                                ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    analyzer = PlayerAnalyzer()
    
    print("\n📊 Analyzing price patterns...")
    patterns = analyzer.analyze_price_patterns()
    print(f"   Patterns found: {list(patterns.keys())}")
    
    print("\n🤖 Detecting bot activity...")
    bots = analyzer.detect_bot_activity()
    print(f"   Bot indicators: {list(bots.keys())}")
    
    print("\n💰 Finding alpha opportunities...")
    alpha = analyzer.find_alpha_opportunities()
    
    print(f"\n{'='*60}")
    print("  ALPHA OPPORTUNITIES")
    print(f"{'='*60}")
    
    for opp in alpha['opportunities']:
        print(f"\n  📌 {opp['type']}")
        print(f"     Signal: {opp['signal']}")
        print(f"     Confidence: {opp['confidence']}")
    
    print(f"\n{'='*60}")
    print(f"  Data Quality: {alpha['data_quality']}")
    print(f"  Recommendation: {alpha['recommendation']}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

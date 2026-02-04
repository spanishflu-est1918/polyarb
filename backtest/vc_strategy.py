#!/usr/bin/env python3
"""
VC-STYLE BETTING
Accept the market is efficient. Hunt for asymmetric payoffs.

Philosophy:
- 80% of bets will lose (that's fine)
- Looking for 10-100x payoffs on the 20% that hit
- Quick expiry = forced resolution = less time for efficient pricing
- Small bets, many positions (portfolio theory)
- Boring markets with binary outcomes = volatility mispriced
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Optional
import requests

DB_PATH = Path(__file__).parent.parent / "data" / "polymarket.db"
GAMMA_API = "https://gamma-api.polymarket.com"


@dataclass
class VCBet:
    """A VC-style asymmetric bet."""
    market_id: str
    market_name: str
    bet_side: str  # 'yes' or 'no'
    price: float
    potential_return: float  # X multiple if correct
    days_to_expiry: int
    thesis: str
    confidence: str  # 'low', 'medium', 'high'
    bet_size_pct: float  # % of bankroll
    
    @property
    def expected_value(self) -> float:
        """Rough EV assuming price = probability."""
        if self.bet_side == 'yes':
            # Buying YES at price P, wins 1/P - 1 if correct
            win_prob = self.price
            return (win_prob * self.potential_return) - ((1 - win_prob) * 1)
        else:
            win_prob = 1 - self.price  # NO wins when YES fails
            return (win_prob * self.potential_return) - ((1 - win_prob) * 1)


class VCBetFinder:
    """
    Find asymmetric bets with VC economics.
    
    Target profile:
    - Quick expiry (1-14 days)
    - Low probability event (YES < 0.20 or NO < 0.20)
    - Binary outcome (clear resolution)
    - Mispriced volatility
    """
    
    def __init__(self):
        self.bets: List[VCBet] = []
    
    def fetch_markets_with_expiry(self) -> List[Dict]:
        """Fetch markets and filter for quick expiry."""
        try:
            resp = requests.get(f"{GAMMA_API}/markets", params={
                "closed": "false",
                "limit": 500
            })
            markets = resp.json() if resp.status_code == 200 else []
            
            # Filter for expiry
            now = datetime.now()
            quick_expiry = []
            
            for m in markets:
                end_date = m.get('endDate') or m.get('end_date')
                if end_date:
                    try:
                        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                        days_left = (end.replace(tzinfo=None) - now).days
                        if 1 <= days_left <= 30:  # 1-30 days out
                            m['days_to_expiry'] = days_left
                            quick_expiry.append(m)
                    except:
                        pass
            
            return quick_expiry
        except Exception as e:
            print(f"Error fetching markets: {e}")
            return []
    
    def find_long_shots(self, markets: List[Dict]) -> List[VCBet]:
        """
        Find long-shot bets with asymmetric payoff.
        
        Criteria:
        - YES price < 0.15 (6.7x+ return if wins)
        - Or NO price < 0.15 (betting against near-certainties)
        - Quick expiry (less time for market to correct)
        """
        bets = []
        
        for m in markets:
            prices = m.get('outcomePrices', [])
            if isinstance(prices, str):
                try:
                    import json
                    prices = json.loads(prices)
                except:
                    continue
            
            if len(prices) < 2:
                continue
            
            yes_price = float(prices[0])
            no_price = float(prices[1])
            days = m.get('days_to_expiry', 30)
            question = m.get('question', '')[:60]
            market_id = m.get('id', m.get('conditionId', 'unknown'))
            volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
            
            # Skip illiquid
            if volume < 10000:
                continue
            
            # Long-shot YES (cheap YES, big upside)
            if yes_price < 0.15 and yes_price > 0.01:
                potential_return = (1 / yes_price) - 1
                
                # Quick expiry bonus
                expiry_bonus = 1 + (0.1 * (14 - min(days, 14)) / 14)
                
                bet = VCBet(
                    market_id=market_id,
                    market_name=question,
                    bet_side='yes',
                    price=yes_price,
                    potential_return=potential_return,
                    days_to_expiry=days,
                    thesis=f"Long-shot YES. {potential_return:.1f}x if correct. Market may underestimate tail risk.",
                    confidence='low',
                    bet_size_pct=0.5  # 0.5% of bankroll per long-shot
                )
                bets.append(bet)
            
            # Contrarian NO (fade the "sure thing")
            if yes_price > 0.90 and yes_price < 0.99:
                no_price_actual = 1 - yes_price
                potential_return = (1 / no_price_actual) - 1
                
                bet = VCBet(
                    market_id=market_id,
                    market_name=question,
                    bet_side='no',
                    price=yes_price,  # Store YES price for context
                    potential_return=potential_return,
                    days_to_expiry=days,
                    thesis=f"Fade the sure thing. {potential_return:.1f}x if consensus is wrong. Nothing is 90%+ certain.",
                    confidence='low',
                    bet_size_pct=0.5
                )
                bets.append(bet)
        
        return bets
    
    def find_volatility_plays(self, markets: List[Dict]) -> List[VCBet]:
        """
        Find markets where volatility is likely mispriced.
        
        Quick expiry + uncertain outcome = volatility.
        Markets priced near 0.50 with quick expiry = coin flips.
        """
        bets = []
        
        for m in markets:
            prices = m.get('outcomePrices', [])
            if isinstance(prices, str):
                try:
                    import json
                    prices = json.loads(prices)
                except:
                    continue
            
            if len(prices) < 2:
                continue
            
            yes_price = float(prices[0])
            days = m.get('days_to_expiry', 30)
            question = m.get('question', '')[:60]
            market_id = m.get('id', m.get('conditionId', 'unknown'))
            volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
            
            if volume < 50000:  # Need liquidity for vol plays
                continue
            
            # Coin flip + quick expiry = vol opportunity
            if 0.40 <= yes_price <= 0.60 and days <= 7:
                # These markets will move. Direction unknown.
                # VC play: pick a side based on minimal edge, ride volatility
                bet = VCBet(
                    market_id=market_id,
                    market_name=question,
                    bet_side='yes' if yes_price < 0.50 else 'no',
                    price=yes_price,
                    potential_return=1.0,  # ~2x on coin flip
                    days_to_expiry=days,
                    thesis=f"Coin flip resolving in {days} days. Vol likely underpriced. Small edge from price < 0.50.",
                    confidence='medium',
                    bet_size_pct=1.0  # Slightly larger for coin flips
                )
                bets.append(bet)
        
        return bets
    
    def find_boring_anomalies(self, markets: List[Dict]) -> List[VCBet]:
        """
        Find boring markets where anomalies might exist.
        
        Sports finals, earnings, scheduled events.
        These have forced resolution and clear outcomes.
        """
        bets = []
        
        boring_keywords = ['finals', 'championship', 'election', 'rate', 'gdp', 
                         'unemployment', 'earnings', 'announcement', 'decision']
        
        for m in markets:
            question = m.get('question', '').lower()
            
            # Check if boring/scheduled event
            is_boring = any(kw in question for kw in boring_keywords)
            if not is_boring:
                continue
            
            prices = m.get('outcomePrices', [])
            if isinstance(prices, str):
                try:
                    import json
                    prices = json.loads(prices)
                except:
                    continue
            
            if len(prices) < 2:
                continue
            
            yes_price = float(prices[0])
            days = m.get('days_to_expiry', 30)
            market_id = m.get('id', m.get('conditionId', 'unknown'))
            volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
            
            if volume < 100000:  # Boring events need high liquidity
                continue
            
            # For boring events, slight mispricings matter
            # If price is slightly off round numbers, there might be edge
            for target in [0.25, 0.33, 0.50, 0.67, 0.75]:
                if abs(yes_price - target) < 0.03:
                    # Price is near a psychological level
                    direction = 'yes' if yes_price < target else 'no'
                    
                    bet = VCBet(
                        market_id=market_id,
                        market_name=m.get('question', '')[:60],
                        bet_side=direction,
                        price=yes_price,
                        potential_return=(1 / (yes_price if direction == 'yes' else 1-yes_price)) - 1,
                        days_to_expiry=days,
                        thesis=f"Boring event near {target:.0%}. Slight mispricing toward {direction.upper()}.",
                        confidence='medium',
                        bet_size_pct=0.5
                    )
                    bets.append(bet)
                    break
        
        return bets
    
    def build_portfolio(self, bankroll: float = 1000) -> Dict:
        """
        Build a VC-style portfolio of bets.
        
        Target: 20-30 small positions across different categories.
        """
        print("🔍 Fetching markets with quick expiry...")
        markets = self.fetch_markets_with_expiry()
        print(f"   Found {len(markets)} markets expiring in 1-30 days")
        
        all_bets = []
        
        print("\n🎰 Finding long-shot bets...")
        long_shots = self.find_long_shots(markets)
        print(f"   Found {len(long_shots)} long-shots")
        all_bets.extend(long_shots)
        
        print("\n📈 Finding volatility plays...")
        vol_plays = self.find_volatility_plays(markets)
        print(f"   Found {len(vol_plays)} volatility plays")
        all_bets.extend(vol_plays)
        
        print("\n📊 Finding boring anomalies...")
        boring = self.find_boring_anomalies(markets)
        print(f"   Found {len(boring)} boring event anomalies")
        all_bets.extend(boring)
        
        # Deduplicate by market
        seen = set()
        unique_bets = []
        for bet in all_bets:
            if bet.market_id not in seen:
                seen.add(bet.market_id)
                unique_bets.append(bet)
        
        # Sort by potential return
        unique_bets.sort(key=lambda b: b.potential_return, reverse=True)
        
        # Build portfolio (max 30 bets)
        portfolio_bets = unique_bets[:30]
        
        # Calculate allocations
        total_allocation = sum(b.bet_size_pct for b in portfolio_bets)
        
        return {
            'bets': portfolio_bets,
            'total_bets': len(portfolio_bets),
            'long_shots': len([b for b in portfolio_bets if b.potential_return > 5]),
            'vol_plays': len([b for b in portfolio_bets if b.confidence == 'medium']),
            'total_allocation_pct': total_allocation,
            'bankroll': bankroll,
            'max_loss': bankroll * (total_allocation / 100),
            'median_upside': np.median([b.potential_return for b in portfolio_bets]) if portfolio_bets else 0
        }


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██╗   ██╗ ██████╗    ██████╗ ███████╗████████╗███████╗                    ║
║   ██║   ██║██╔════╝    ██╔══██╗██╔════╝╚══██╔══╝██╔════╝                    ║
║   ██║   ██║██║         ██████╔╝█████╗     ██║   ███████╗                    ║
║   ╚██╗ ██╔╝██║         ██╔══██╗██╔══╝     ██║   ╚════██║                    ║
║    ╚████╔╝ ╚██████╗    ██████╔╝███████╗   ██║   ███████║                    ║
║     ╚═══╝   ╚═════╝    ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝                    ║
║                                                                              ║
║   Efficient market? Fine. Look for asymmetric payoffs.                       ║
║   80% will lose. The 20% need to pay 10x+.                                   ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """)
    
    finder = VCBetFinder()
    portfolio = finder.build_portfolio(bankroll=1000)
    
    print("\n" + "═"*80)
    print("  VC PORTFOLIO SUMMARY")
    print("═"*80)
    print(f"""
   Total Bets:          {portfolio['total_bets']}
   Long-shots (10x+):   {portfolio['long_shots']}
   Volatility Plays:    {portfolio['vol_plays']}
   
   Total Allocation:    {portfolio['total_allocation_pct']:.1f}% of bankroll
   Max Loss (if all fail): ${portfolio['max_loss']:.2f}
   Median Upside:       {portfolio['median_upside']:.1f}x
    """)
    
    if portfolio['bets']:
        print("\n" + "─"*80)
        print("  TOP BETS BY POTENTIAL RETURN")
        print("─"*80)
        
        for i, bet in enumerate(portfolio['bets'][:15], 1):
            print(f"""
#{i} {bet.market_name}
    Side: {bet.bet_side.upper()} @ ${bet.price:.3f}
    Potential: {bet.potential_return:.1f}x | Expires: {bet.days_to_expiry} days
    Thesis: {bet.thesis}
    Size: {bet.bet_size_pct}% of bankroll | Confidence: {bet.confidence}
""")
        
        print("\n" + "═"*80)
        print("  VC MATH")
        print("═"*80)
        
        # Calculate portfolio expected value assuming prices are correct
        avg_return = np.mean([b.potential_return for b in portfolio['bets']])
        
        print(f"""
   If prices are efficient (no edge):
   - Expected return: 0% (minus fees)
   - This is a lottery ticket portfolio
   
   If we have 5% information edge:
   - Win rate: ~25% (vs 20% implied)
   - Expected value: +{0.05 * avg_return * 100:.0f}% per bet
   
   VC MINDSET:
   - Comfortable losing 80% of bets
   - Looking for 1-2 big winners to pay for all losses
   - Quick expiry forces resolution (no limbo)
   - Diversified across uncorrelated events
   
   ⚠️  THIS IS HIGH RISK SPECULATION
   ⚠️  ONLY BET WHAT YOU CAN LOSE 100%
        """)
    else:
        print("\n❌ No suitable bets found. Market may be too efficient right now.")
    
    return portfolio


if __name__ == "__main__":
    main()

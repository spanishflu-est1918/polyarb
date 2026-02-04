#!/usr/bin/env python3
"""
LIVE SIGNALS - Bot Fade Opportunities
Quick view of current actionable signals.
"""

import requests
import json
from datetime import datetime

GAMMA_API = "https://gamma-api.polymarket.com"


def get_signals():
    """Fetch markets and find fade opportunities."""
    
    # Fetch markets
    resp = requests.get(f"{GAMMA_API}/markets", params={
        "closed": "false",
        "limit": 500
    })
    markets = resp.json() if resp.status_code == 200 else []
    
    signals = []
    
    for m in markets:
        prices = m.get('outcomePrices', [])
        if isinstance(prices, str):
            try:
                prices = json.loads(prices)
            except:
                continue
        
        if len(prices) < 2:
            continue
        
        yes_price = float(prices[0])
        volume = float(m.get('volume', 0) or m.get('volumeNum', 0) or 0)
        question = m.get('question', '')[:55]
        market_id = m.get('id', '')
        
        # Skip illiquid
        if volume < 10000:
            continue
        
        # Calculate volume ratio (using median as benchmark)
        avg_volume = 500000  # Rough benchmark
        vol_ratio = volume / avg_volume
        
        # SIGNAL 1: Extreme price + low volume = fade
        is_extreme_low = yes_price < 0.12
        is_extreme_high = yes_price > 0.88
        is_low_volume = vol_ratio < 0.5
        
        if is_extreme_low and is_low_volume:
            potential = (1 / yes_price) - 1 if yes_price > 0 else 0
            signals.append({
                'question': question,
                'signal': 'LOW_PRICE_LOW_VOL',
                'action': 'BUY YES',
                'price': yes_price,
                'potential': potential,
                'volume': volume,
                'vol_ratio': vol_ratio,
                'confidence': min(0.6, (0.12 - yes_price) * 10)
            })
        
        elif is_extreme_high and is_low_volume:
            no_price = 1 - yes_price
            potential = (1 / no_price) - 1 if no_price > 0 else 0
            signals.append({
                'question': question,
                'signal': 'HIGH_PRICE_LOW_VOL',
                'action': 'BUY NO',
                'price': yes_price,
                'potential': potential,
                'volume': volume,
                'vol_ratio': vol_ratio,
                'confidence': min(0.6, (yes_price - 0.88) * 10)
            })
    
    # Sort by potential return
    signals.sort(key=lambda x: x['potential'], reverse=True)
    
    return signals


def main():
    print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│  🎯 LIVE BOT FADE SIGNALS                                          │
│  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                          │
└─────────────────────────────────────────────────────────────────────┘
""")
    
    signals = get_signals()
    
    if not signals:
        print("  No actionable signals right now.\n")
        return
    
    print(f"  Found {len(signals)} fade opportunities\n")
    print("  ─" * 35)
    
    for i, sig in enumerate(signals[:15], 1):
        conf_bar = "█" * int(sig['confidence'] * 10) + "░" * (6 - int(sig['confidence'] * 10))
        
        print(f"""
  #{i} {sig['question']}
      {sig['action']} @ {sig['price']:.1%} → {sig['potential']:.0f}x potential
      Vol: ${sig['volume']:,.0f} ({sig['vol_ratio']:.1f}x avg)
      Confidence: [{conf_bar}] {sig['confidence']:.0%}
""")
    
    print("  ─" * 35)
    print("""
  THE TRADE:
  • Bots pushed prices to extremes without volume
  • If ANY real news hits, price moves violently
  • Asymmetric: risk 1x to make 10-50x

  SIZING: 0.5% of bankroll per signal
  STOP: Exit if price goes 5% further against you
  
  ⚠️  This is speculation, not investment
""")


if __name__ == "__main__":
    main()

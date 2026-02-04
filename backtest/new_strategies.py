#!/usr/bin/env python3
"""
New Strategies - Based on Slop Detection & Smart Money Analysis
No HFT. No competing with bots on speed. Human psychology edges only.
"""

from typing import List, Dict
import pandas as pd
import numpy as np


# =============================================================================
# STRATEGY: Fade Extreme Moves (Anti-FOMO)
# Hypothesis: Big moves driven by retail FOMO revert partially
# =============================================================================

def strategy_fade_extremes(engine, row, history) -> List[Dict]:
    """
    When price moves too fast, fade it.
    Not competing on speed - waiting for FOMO exhaustion.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    
    if yes_price is None:
        return signals
    
    # Get history for this market
    market_history = history[history['market_id'] == market_id]['yes_price']
    
    if len(market_history) < 5:
        return signals
    
    # Calculate recent move
    price_5_ago = market_history.iloc[-5] if len(market_history) >= 5 else market_history.iloc[0]
    move = (yes_price - price_5_ago) / price_5_ago if price_5_ago > 0 else 0
    
    position_key = f"fade_{market_id}"
    
    # Fade big moves (>10% in 5 periods)
    if abs(move) > 0.10 and position_key not in engine.positions:
        # Fade direction
        if move > 0:
            # Price spiked up, bet on reversion (buy NO)
            size = engine.capital * engine.max_position_pct * 0.5
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_no',
                'price': 1 - yes_price,  # NO price
                'size_usd': size
            })
            engine.positions[position_key] = {'direction': 'down', 'entry': yes_price}
        else:
            # Price dumped, bet on bounce (buy YES)
            size = engine.capital * engine.max_position_pct * 0.5
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_yes',
                'price': yes_price,
                'size_usd': size
            })
            engine.positions[position_key] = {'direction': 'up', 'entry': yes_price}
    
    # Exit on partial reversion (50% of move)
    elif position_key in engine.positions:
        pos = engine.positions[position_key]
        entry = pos['entry']
        
        if pos['direction'] == 'down' and yes_price < entry * 0.95:
            # Reverted 50%+ of up move, take profit
            size = engine.capital * engine.max_position_pct * 0.5
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'sell_no',
                'price': 1 - yes_price,
                'size_usd': size
            })
            del engine.positions[position_key]
        elif pos['direction'] == 'up' and yes_price > entry * 1.05:
            size = engine.capital * engine.max_position_pct * 0.5
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'sell_yes',
                'price': yes_price,
                'size_usd': size
            })
            del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY: Grinder Copy (Follow Consistent Winners)
# Hypothesis: High trade count + modest win rate = real edge, not luck
# =============================================================================

def strategy_grinder_follow(engine, row, history) -> List[Dict]:
    """
    Simulate following a consistent grinder's behavior:
    - Many small bets
    - Slight edge (52-58% win rate)
    - Compound over time
    
    We simulate this by betting on high-volume markets with tight spreads
    (where grinders operate).
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    volume = row.get('volume_24h', 0) or 0
    spread = row.get('spread', 1) or 1
    
    if yes_price is None:
        return signals
    
    # Grinders operate in high-volume, tight-spread markets
    if volume < 100000 or spread > 0.02:
        return signals
    
    position_key = f"grind_{market_id}"
    
    # Simple momentum in liquid markets (grinders ride momentum)
    market_history = history[history['market_id'] == market_id]['yes_price']
    
    if len(market_history) < 3:
        return signals
    
    # 3-period momentum
    price_3_ago = market_history.iloc[-3] if len(market_history) >= 3 else market_history.iloc[0]
    momentum = (yes_price - price_3_ago) / price_3_ago if price_3_ago > 0 else 0
    
    # Small positions, follow momentum
    if abs(momentum) > 0.02 and position_key not in engine.positions:
        size = engine.capital * 0.02  # Tiny position (2%)
        
        if momentum > 0:
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_yes',
                'price': yes_price,
                'size_usd': size
            })
        else:
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_no',
                'price': 1 - yes_price,
                'size_usd': size
            })
        engine.positions[position_key] = {'direction': 'long' if momentum > 0 else 'short'}
    
    # Quick exit - grinders don't hold
    elif position_key in engine.positions:
        # Exit after 5 periods regardless
        if len(market_history) >= 5:
            pos = engine.positions[position_key]
            size = engine.capital * 0.02
            
            if pos['direction'] == 'long':
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_yes',
                    'price': yes_price,
                    'size_usd': size
                })
            else:
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_no',
                    'price': 1 - yes_price,
                    'size_usd': size
                })
            del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY: Round Number Fade
# Hypothesis: Prices cluster at 0.25/0.50/0.75 then revert
# =============================================================================

def strategy_round_number_fade(engine, row, history) -> List[Dict]:
    """
    Fade moves toward round numbers.
    When price approaches 0.25/0.50/0.75, bet on bounce back.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    
    if yes_price is None:
        return signals
    
    round_levels = [0.25, 0.50, 0.75]
    position_key = f"round_{market_id}"
    
    # Check if near a round number
    for level in round_levels:
        distance = abs(yes_price - level)
        
        if distance < 0.02 and position_key not in engine.positions:
            # At a round number - bet on bounce away
            size = engine.capital * engine.max_position_pct * 0.3
            
            # If just above, expect fade down. If just below, expect fade up.
            if yes_price > level:
                # Slightly above round number, expect fade down
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'buy_no',
                    'price': 1 - yes_price,
                    'size_usd': size
                })
                engine.positions[position_key] = {'level': level, 'direction': 'down'}
            else:
                # Slightly below, expect bounce up
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'buy_yes',
                    'price': yes_price,
                    'size_usd': size
                })
                engine.positions[position_key] = {'level': level, 'direction': 'up'}
            break
    
    # Exit when moved away from round number
    if position_key in engine.positions:
        pos = engine.positions[position_key]
        distance_from_level = abs(yes_price - pos['level'])
        
        if distance_from_level > 0.05:  # Moved 5% away
            size = engine.capital * engine.max_position_pct * 0.3
            
            if pos['direction'] == 'down':
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_no',
                    'price': 1 - yes_price,
                    'size_usd': size
                })
            else:
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_yes',
                    'price': yes_price,
                    'size_usd': size
                })
            del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY: Volume Spike Fade  
# Hypothesis: Volume spikes = retail FOMO, fade after the spike
# =============================================================================

def strategy_volume_spike_fade(engine, row, history) -> List[Dict]:
    """
    When volume spikes unusually high, retail is piling in.
    Fade the move that accompanies the volume spike.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    volume = row.get('volume_24h', 0) or 0
    
    if yes_price is None or volume == 0:
        return signals
    
    # Get volume history
    market_history = history[history['market_id'] == market_id]
    
    if len(market_history) < 10:
        return signals
    
    vol_history = market_history['volume_24h'].dropna()
    if len(vol_history) < 5:
        return signals
    
    avg_volume = vol_history.mean()
    
    position_key = f"volspike_{market_id}"
    
    # Volume spike = 2x average
    if volume > avg_volume * 2 and position_key not in engine.positions:
        # Get price direction during spike
        price_history = market_history['yes_price']
        if len(price_history) < 2:
            return signals
        
        recent_move = yes_price - price_history.iloc[-2]
        
        size = engine.capital * engine.max_position_pct * 0.4
        
        # Fade the spike direction
        if recent_move > 0:
            # Price went up with volume, fade down
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_no',
                'price': 1 - yes_price,
                'size_usd': size
            })
            engine.positions[position_key] = {'fade_dir': 'down', 'entry': yes_price}
        else:
            # Price went down with volume, fade up
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'buy_yes',
                'price': yes_price,
                'size_usd': size
            })
            engine.positions[position_key] = {'fade_dir': 'up', 'entry': yes_price}
    
    # Exit on reversion
    elif position_key in engine.positions:
        pos = engine.positions[position_key]
        entry = pos['entry']
        
        reversion = abs(yes_price - entry) / entry if entry > 0 else 0
        
        if reversion > 0.03:  # 3% reversion, take profit
            size = engine.capital * engine.max_position_pct * 0.4
            
            if pos['fade_dir'] == 'down':
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_no',
                    'price': 1 - yes_price,
                    'size_usd': size
                })
            else:
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'sell_yes',
                    'price': yes_price,
                    'size_usd': size
                })
            del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY: Extreme Value (Buy cheap, sell expensive)
# Hypothesis: Prices at extremes (<0.10 or >0.90) tend to mean revert
# =============================================================================

def strategy_extreme_value(engine, row, history) -> List[Dict]:
    """
    Buy cheap outcomes, sell expensive ones.
    Long-shot bias: people overpay for unlikely events.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    volume = row.get('volume_24h', 0) or 0
    
    if yes_price is None:
        return signals
    
    # Only trade liquid markets
    if volume < 50000:
        return signals
    
    position_key = f"extreme_{market_id}"
    
    # Extreme cheap (YES < 0.10) - people underestimate unlikely events
    if yes_price < 0.10 and position_key not in engine.positions:
        # Small bet on cheap YES
        size = engine.capital * 0.01  # Tiny (1%)
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_yes',
            'price': yes_price,
            'size_usd': size
        })
        engine.positions[position_key] = {'type': 'cheap_yes', 'entry': yes_price}
    
    # Extreme expensive (YES > 0.90) - people overpay for "sure things"
    elif yes_price > 0.90 and position_key not in engine.positions:
        # Bet against the "sure thing"
        size = engine.capital * 0.01
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_no',
            'price': 1 - yes_price,
            'size_usd': size
        })
        engine.positions[position_key] = {'type': 'cheap_no', 'entry': yes_price}
    
    # Exit on any movement toward center
    elif position_key in engine.positions:
        pos = engine.positions[position_key]
        
        if pos['type'] == 'cheap_yes' and yes_price > 0.15:
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'sell_yes',
                'price': yes_price,
                'size_usd': engine.capital * 0.01
            })
            del engine.positions[position_key]
        elif pos['type'] == 'cheap_no' and yes_price < 0.85:
            signals.append({
                'timestamp': row['timestamp'],
                'market_id': market_id,
                'side': 'sell_no',
                'price': 1 - yes_price,
                'size_usd': engine.capital * 0.01
            })
            del engine.positions[position_key]
    
    return signals


# All new strategies
NEW_STRATEGIES = {
    'fade_extremes': strategy_fade_extremes,
    'grinder_follow': strategy_grinder_follow,
    'round_number_fade': strategy_round_number_fade,
    'volume_spike_fade': strategy_volume_spike_fade,
    'extreme_value': strategy_extreme_value,
}

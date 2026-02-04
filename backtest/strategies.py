#!/usr/bin/env python3
"""
Trading Strategies for Backtesting

Each strategy should:
1. Have a clear hypothesis
2. Be testable against data
3. Not rely on future information
"""

from typing import List, Dict
import pandas as pd
import numpy as np


# =============================================================================
# STRATEGY 1: Basic Arbitrage
# Hypothesis: When YES + NO < 0.98, buy both and wait for convergence
# =============================================================================

def strategy_basic_arb(engine, row, history) -> List[Dict]:
    """
    Simple arbitrage: buy YES and NO when combined price < 0.98
    Exit when price converges to 1.0
    """
    signals = []
    
    yes_price = row.get('yes_price')
    no_price = row.get('no_price')
    
    if yes_price is None or no_price is None:
        return signals
    
    combined = yes_price + no_price
    market_id = row['market_id']
    position_key = f"arb_{market_id}"
    
    # Entry: combined price < 0.98 (2% edge)
    if combined < 0.98 and position_key not in engine.positions:
        # Buy both YES and NO
        size = engine.capital * engine.max_position_pct / 2
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_yes',
            'price': yes_price,
            'size_usd': size
        })
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_no',
            'price': no_price,
            'size_usd': size
        })
        engine.positions[position_key] = True
    
    # Exit: combined price > 0.995 (converged)
    elif combined > 0.995 and position_key in engine.positions:
        size = engine.capital * engine.max_position_pct / 2
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'sell_yes',
            'price': yes_price,
            'size_usd': size
        })
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'sell_no',
            'price': no_price,
            'size_usd': size
        })
        del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY 2: Mean Reversion
# Hypothesis: Prices that move too fast revert
# =============================================================================

def strategy_mean_reversion(engine, row, history) -> List[Dict]:
    """
    Mean reversion: buy when price drops sharply, sell when it spikes.
    Uses 20-period moving average and 2 std dev bands.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    
    if yes_price is None:
        return signals
    
    # Get history for this market
    market_history = history[history['market_id'] == market_id]['yes_price']
    
    if len(market_history) < 20:
        return signals
    
    # Calculate bands
    ma = market_history.rolling(20).mean().iloc[-1]
    std = market_history.rolling(20).std().iloc[-1]
    
    if pd.isna(ma) or pd.isna(std) or std == 0:
        return signals
    
    upper_band = ma + 2 * std
    lower_band = ma - 2 * std
    
    position_key = f"mr_{market_id}"
    
    # Entry: price below lower band (oversold)
    if yes_price < lower_band and position_key not in engine.positions:
        size = engine.capital * engine.max_position_pct
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_yes',
            'price': yes_price,
            'size_usd': size
        })
        engine.positions[position_key] = {'entry_price': yes_price, 'ma': ma}
    
    # Exit: price returns to MA or hits upper band
    elif position_key in engine.positions:
        entry = engine.positions[position_key]
        if yes_price >= entry['ma'] or yes_price >= upper_band:
            size = engine.capital * engine.max_position_pct
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
# STRATEGY 3: Spread Capture
# Hypothesis: Wide spreads mean inefficiency, capture the spread
# =============================================================================

def strategy_spread_capture(engine, row, history) -> List[Dict]:
    """
    When spread is abnormally wide, place limit orders to capture it.
    Simplified: buy at bid, sell at ask.
    """
    signals = []
    
    spread = row.get('spread')
    yes_price = row.get('yes_price')
    no_price = row.get('no_price')
    market_id = row['market_id']
    
    if spread is None or spread < 0.03:  # Need 3%+ spread
        return signals
    
    # In a real system, you'd place limit orders
    # For backtest, we simulate capturing half the spread
    
    position_key = f"spread_{market_id}"
    
    if position_key not in engine.positions:
        size = engine.capital * engine.max_position_pct
        # Simulate buying at mid - spread/4
        effective_price = yes_price - (spread / 4)
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_yes',
            'price': max(0.01, effective_price),
            'size_usd': size
        })
        engine.positions[position_key] = {'entry': effective_price}
    
    # Exit when spread narrows
    elif spread < 0.02 and position_key in engine.positions:
        size = engine.capital * engine.max_position_pct
        # Simulate selling at mid + spread/4
        effective_price = yes_price + (spread / 4)
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'sell_yes',
            'price': min(0.99, effective_price),
            'size_usd': size
        })
        del engine.positions[position_key]
    
    return signals


# =============================================================================
# STRATEGY 4: Momentum (Counter-Strategy for Testing)
# Hypothesis: Trends continue. Buy winners, sell losers.
# Note: This often LOSES in prediction markets. Good for comparison.
# =============================================================================

def strategy_momentum(engine, row, history) -> List[Dict]:
    """
    Momentum: buy assets that have been rising.
    Often a BAD strategy in prediction markets - good control test.
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    
    if yes_price is None:
        return signals
    
    # Get history
    market_history = history[history['market_id'] == market_id]['yes_price']
    
    if len(market_history) < 10:
        return signals
    
    # 10-period momentum
    past_price = market_history.iloc[-10] if len(market_history) >= 10 else market_history.iloc[0]
    momentum = (yes_price - past_price) / past_price if past_price > 0 else 0
    
    position_key = f"mom_{market_id}"
    
    # Buy strong momentum
    if momentum > 0.1 and position_key not in engine.positions:
        size = engine.capital * engine.max_position_pct
        signals.append({
            'timestamp': row['timestamp'],
            'market_id': market_id,
            'side': 'buy_yes',
            'price': yes_price,
            'size_usd': size
        })
        engine.positions[position_key] = True
    
    # Exit on reversal
    elif momentum < 0 and position_key in engine.positions:
        size = engine.capital * engine.max_position_pct
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
# META STRATEGY: Bot Behavior Exploitation
# Hypothesis: Bots rebalance at predictable thresholds
# =============================================================================

def strategy_bot_front_run(engine, row, history) -> List[Dict]:
    """
    Detect likely bot rebalancing levels and front-run.
    
    Bot behaviors to exploit:
    1. Round number rebalancing (0.5, 0.25, 0.75)
    2. Regular interval activity
    3. Threshold-based position changes
    """
    signals = []
    
    market_id = row['market_id']
    yes_price = row.get('yes_price')
    volume = row.get('volume_24h', 0)
    
    if yes_price is None:
        return signals
    
    # Detect approach to round numbers (bot rebalancing levels)
    round_levels = [0.25, 0.50, 0.75]
    
    for level in round_levels:
        distance = abs(yes_price - level)
        
        # Price approaching round number from below
        if 0.02 < distance < 0.05 and yes_price < level:
            # Hypothesis: bots will buy to rebalance, pushing price up
            position_key = f"bot_front_{market_id}_{level}"
            
            if position_key not in engine.positions:
                size = engine.capital * engine.max_position_pct * 0.5  # Half size, risky
                signals.append({
                    'timestamp': row['timestamp'],
                    'market_id': market_id,
                    'side': 'buy_yes',
                    'price': yes_price,
                    'size_usd': size
                })
                engine.positions[position_key] = {'target': level}
        
        # Exit once past the level
        position_key = f"bot_front_{market_id}_{level}"
        if position_key in engine.positions:
            if yes_price > level + 0.01:
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


# All strategies for testing
STRATEGIES = {
    'basic_arb': strategy_basic_arb,
    'mean_reversion': strategy_mean_reversion,
    'spread_capture': strategy_spread_capture,
    'momentum': strategy_momentum,
    'bot_front_run': strategy_bot_front_run,
}

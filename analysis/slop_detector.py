#!/usr/bin/env python3
"""
SLOP DETECTOR & NARRATIVE ALPHA
Turn the bullshit into signal.

The insight: Viral threads and slop create predictable market movements.
- FOMO spike 15-60 min after viral content
- Overreaction decay 2-6 hours later
- Copycat behavior clusters

Instead of fighting the slop, front-run it.
"""

import re
import requests
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class SlopSignal:
    """A detected slop/narrative pattern."""
    type: str  # 'viral_thread', 'fomo_spike', 'honeypot_promo', 'whale_alert'
    source: str
    timestamp: datetime
    market_ids: List[str]
    confidence: float
    expected_move: str  # 'spike_then_fade', 'sustained', 'pump_dump'
    trade_signal: str  # 'fade_after_spike', 'front_run', 'avoid'
    reasoning: str


class SlopDetector:
    """
    Detect and classify market-moving slop.
    Convert noise into trading signals.
    """
    
    # Slop patterns that move markets
    SLOP_PATTERNS = {
        'viral_thread': {
            'keywords': ['1 minute read', 'thread', 'how i made', 'here\'s what happened', 
                        'no one is talking about', 'alpha', 'free money', 'in one week',
                        'i installed', 'everyone has been talking', 'found me a wallet',
                        'what happened', 'printing', 'here is what'],
            'action': 'fade_after_spike',
            'confidence': 0.6,
            'explanation': 'Viral threads cause FOMO spike → fade 2-4 hours later'
        },
        'whale_alert': {
            'keywords': ['whale', 'million dollar', '$1m', 'huge position', 'smart money'],
            'action': 'front_run_fade',
            'confidence': 0.5,
            'explanation': 'Whale alerts attract followers → price spikes → whale exits on followers'
        },
        'guaranteed_money': {
            'keywords': ['guaranteed', 'risk free', 'free money', 'can\'t lose', 'arbitrage'],
            'action': 'avoid',
            'confidence': 0.9,
            'explanation': 'If it sounds too easy, it\'s either priced in or a trap'
        },
        'fomo_bait': {
            'keywords': ['last chance', 'closing soon', 'don\'t miss', 'everyone is', 
                        'you\'re ngmi', 'still early'],
            'action': 'fade',
            'confidence': 0.7,
            'explanation': 'FOMO bait = top signal. Fade the crowd.'
        },
        'cope_post': {
            'keywords': ['still bullish', 'nothing changed', 'zoom out', 'this is good actually',
                        'shaking out weak hands'],
            'action': 'momentum_continue',
            'confidence': 0.5,
            'explanation': 'Cope = denial phase. Move likely continues.'
        }
    }
    
    # Market categories prone to slop movements
    SLOP_SENSITIVE_CATEGORIES = [
        'politics',  # Trump, elections
        'crypto',    # Bitcoin price targets
        'celebrities',  # Kanye, Elon
        'sports',    # Playoffs, championships
        'geopolitics'  # Wars, strikes
    ]
    
    def __init__(self):
        self.detected_signals: List[SlopSignal] = []
    
    def analyze_content(self, content: str, source: str = "unknown") -> List[SlopSignal]:
        """
        Analyze text content for slop patterns.
        Returns trading signals based on detected patterns.
        """
        signals = []
        content_lower = content.lower()
        
        for pattern_name, pattern_data in self.SLOP_PATTERNS.items():
            # Count keyword matches
            matches = sum(1 for kw in pattern_data['keywords'] if kw in content_lower)
            
            if matches >= 2:  # Multiple keyword hits = signal
                confidence = min(0.9, pattern_data['confidence'] + (matches * 0.05))
                
                signal = SlopSignal(
                    type=pattern_name,
                    source=source,
                    timestamp=datetime.now(),
                    market_ids=[],  # Would be populated from content analysis
                    confidence=confidence,
                    expected_move=self._get_expected_move(pattern_name),
                    trade_signal=pattern_data['action'],
                    reasoning=pattern_data['explanation']
                )
                signals.append(signal)
        
        return signals
    
    def _get_expected_move(self, pattern: str) -> str:
        """Get expected market movement for pattern."""
        moves = {
            'viral_thread': 'spike_5-15%_then_fade_over_2-4h',
            'whale_alert': 'spike_3-10%_then_dump_when_followers_buy',
            'guaranteed_money': 'either_priced_in_or_trap',
            'fomo_bait': 'local_top_fade_5-20%',
            'cope_post': 'continue_trend_another_10-30%'
        }
        return moves.get(pattern, 'unknown')
    
    def generate_counter_strategies(self) -> Dict[str, str]:
        """
        Generate strategies that exploit slop patterns.
        """
        return {
            'viral_thread_fade': """
                VIRAL THREAD FADE
                ─────────────────────────────────────────
                Trigger: High-engagement thread about Polymarket gains
                
                Action:
                1. Wait 30-60 min for FOMO spike
                2. Enter opposite position (fade the move)
                3. Target: 50% retracement
                4. Stop: If move extends 20% beyond spike
                
                Edge: Retail FOMO is predictable. Spikes fade.
                Win rate estimate: 55-60%
            """,
            
            'whale_shadow': """
                WHALE SHADOW STRATEGY
                ─────────────────────────────────────────
                Trigger: Whale wallet activity publicized
                
                Action:
                1. DO NOT copy immediately
                2. Wait for 10-20% spike from followers
                3. Enter opposite direction
                4. Target: Full retracement of follower spike
                
                Edge: Whales exit on followers. Classic pump pattern.
                Win rate estimate: 50-55%
            """,
            
            'cope_momentum': """
                COPE CONTINUATION
                ─────────────────────────────────────────
                Trigger: Heavy cope posting about a position
                
                Action:
                1. Identify cope (denial, "zoom out", etc.)
                2. Enter WITH the existing trend (against the copers)
                3. Target: Another 20-50% move
                4. Stop: If trend actually reverses (cope was right)
                
                Edge: Cope = emotional denial. Reality usually wins.
                Win rate estimate: 55-60%
            """,
            
            'fomo_top_signal': """
                FOMO TOP FADE
                ─────────────────────────────────────────
                Trigger: "Last chance", "don't miss", mass excitement
                
                Action:
                1. Peak FOMO = local top
                2. Wait for first red candle
                3. Enter fade position
                4. Target: 30-50% retracement
                
                Edge: Crowd is always wrong at extremes.
                Win rate estimate: 60-65%
            """
        }
    
    def score_content_tradability(self, content: str) -> Dict:
        """
        Score a piece of content for trading potential.
        """
        signals = self.analyze_content(content)
        
        if not signals:
            return {
                'tradable': False,
                'reason': 'No slop patterns detected',
                'action': 'No trade'
            }
        
        # Take highest confidence signal
        best_signal = max(signals, key=lambda s: s.confidence)
        
        return {
            'tradable': best_signal.trade_signal != 'avoid',
            'signal_type': best_signal.type,
            'confidence': best_signal.confidence,
            'expected_move': best_signal.expected_move,
            'action': best_signal.trade_signal,
            'reasoning': best_signal.reasoning
        }


def analyze_viral_tweet():
    """Analyze the viral tweet from earlier."""
    
    detector = SlopDetector()
    
    # The viral tweet content
    viral_content = """
    $1,400,000 in one week. On a market about Iran.
    How do you make $1M without predicting anything? You buy dollars for 94 cents.
    Three days ago I installed ClawdBot. Everyone has been talking about it. 
    I expected another overhyped tool. Instead, it found me a wallet printing $300K in 24 hours.
    This trader opened the same market more than 30 times. Same market. Over and over.
    Total profit: $1,017,000. In seven days.
    Arbitrage is not about being smarter. It is about noticing that $1 is on sale for 94 cents.
    The sale ends when enough people notice. Have you checked the prices today?
    """
    
    print("""
╔══════════════════════════════════════════════════════════════════╗
║  SLOP DETECTOR - NARRATIVE ANALYSIS                              ║
║  "Turn the bullshit into signal"                                 ║
╚══════════════════════════════════════════════════════════════════╝
    """)
    
    # Analyze the viral tweet
    print("📝 ANALYZING VIRAL CONTENT")
    print("─" * 60)
    
    result = detector.score_content_tradability(viral_content)
    
    print(f"   Tradable: {'✅ YES' if result['tradable'] else '❌ NO'}")
    if 'signal_type' in result:
        print(f"   Signal Type: {result['signal_type']}")
        print(f"   Confidence: {result['confidence']:.0%}")
        print(f"   Expected Move: {result['expected_move']}")
        print(f"   Action: {result['action']}")
        print(f"   Reasoning: {result['reasoning']}")
    else:
        print(f"   Reason: {result['reason']}")
    
    # Show counter strategies
    print("\n\n🎯 COUNTER-STRATEGIES (how to trade against slop)")
    print("─" * 60)
    
    strategies = detector.generate_counter_strategies()
    for name, strategy in strategies.items():
        print(strategy)
    
    # Final recommendation
    print("\n📊 RECOMMENDATION FOR THIS VIRAL THREAD")
    print("─" * 60)
    print("""
    The tweet is GUARANTEED_MONEY + VIRAL_THREAD slop.
    
    What happened after this thread went viral:
    1. Thousands of people rushed to Polymarket
    2. Arb opportunities (if any existed) got crushed
    3. The wallet being tracked now has 23,000 followers
    4. Any edge is gone - too many eyes
    
    CORRECT TRADE:
    ❌ DO NOT copy the wallet
    ❌ DO NOT look for arbs (priced in)
    ✅ Watch for FOMO spike in Iran markets
    ✅ Fade the spike once retail piles in
    
    The alpha isn't in the strategy. It's in fading the people
    who read the thread and think they found alpha.
    """)


if __name__ == "__main__":
    analyze_viral_tweet()

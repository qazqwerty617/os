"""
MEXC Pump Monitor - Fear & Greed Index
Custom fear/greed calculation based on multiple market indicators
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class FearGreedLevel(Enum):
    """Fear & Greed levels"""
    EXTREME_FEAR = "EXTREME_FEAR"      # 0-20
    FEAR = "FEAR"                       # 21-40
    NEUTRAL = "NEUTRAL"                 # 41-60
    GREED = "GREED"                     # 61-80
    EXTREME_GREED = "EXTREME_GREED"    # 81-100


@dataclass
class FearGreedComponents:
    """Individual components of the index"""
    volatility: float = 50        # Lower vol = more greed
    momentum: float = 50          # Price momentum
    volume: float = 50            # Volume comparison
    social: float = 50            # Social sentiment
    funding: float = 50           # Funding rates (high = greed)
    dominance: float = 50         # BTC dominance trend
    liquidations: float = 50      # Liquidation imbalance
    
    def to_dict(self) -> Dict:
        return {
            'volatility': self.volatility,
            'momentum': self.momentum,
            'volume': self.volume,
            'social': self.social,
            'funding': self.funding,
            'dominance': self.dominance,
            'liquidations': self.liquidations
        }


@dataclass
class FearGreedIndex:
    """Complete Fear & Greed Index reading"""
    timestamp: int
    value: int  # 0-100
    level: FearGreedLevel
    
    # Previous reading
    previous_value: int = 50
    change: int = 0  # +/- change
    
    # Components
    components: FearGreedComponents = field(default_factory=FearGreedComponents)
    
    # Historical context
    avg_7d: float = 50
    avg_30d: float = 50
    high_30d: int = 100
    low_30d: int = 0
    
    # Interpretation
    interpretation: str = ""
    signal: str = ""  # "BUY", "SELL", "HOLD"
    
    def to_dict(self) -> Dict:
        return {
            'value': self.value,
            'level': self.level.value,
            'change': self.change,
            'components': self.components.to_dict(),
            'avg_7d': self.avg_7d,
            'interpretation': self.interpretation,
            'signal': self.signal
        }


class FearGreedCalculator:
    """
    Custom Fear & Greed Index calculator
    Uses real market data instead of external APIs
    """
    
    # Component weights
    WEIGHTS = {
        'volatility': 0.15,
        'momentum': 0.25,
        'volume': 0.15,
        'social': 0.10,
        'funding': 0.15,
        'dominance': 0.10,
        'liquidations': 0.10
    }
    
    def __init__(self):
        # Historical readings
        self.history: deque = deque(maxlen=1000)
        
        # Current reading
        self.current: Optional[FearGreedIndex] = None
        
        # Input data stores
        self.volatility_data: deque = deque(maxlen=100)
        self.price_data: Dict[str, deque] = {}
        self.volume_data: Dict[str, deque] = {}
        self.funding_data: Dict[str, float] = {}
        self.social_scores: Dict[str, float] = {}
        self.long_liqs: deque = deque(maxlen=100)
        self.short_liqs: deque = deque(maxlen=100)
        
        # Stats
        self.stats = {
            'calculations': 0,
            'extreme_fear_count': 0,
            'extreme_greed_count': 0
        }
    
    def record_volatility(self, vol_index: float):
        """Record volatility index (0-100)"""
        self.volatility_data.append({
            'value': vol_index,
            'timestamp': int(time.time() * 1000)
        })
    
    def record_price(self, symbol: str, price: float):
        """Record price for momentum calculation"""
        if symbol not in self.price_data:
            self.price_data[symbol] = deque(maxlen=100)
        
        self.price_data[symbol].append({
            'price': price,
            'timestamp': int(time.time() * 1000)
        })
    
    def record_volume(self, symbol: str, volume: float):
        """Record volume"""
        if symbol not in self.volume_data:
            self.volume_data[symbol] = deque(maxlen=100)
        
        self.volume_data[symbol].append(volume)
    
    def record_funding(self, symbol: str, rate: float):
        """Record funding rate"""
        self.funding_data[symbol] = rate
    
    def record_social(self, symbol: str, sentiment: float):
        """Record social sentiment (-1 to 1)"""
        self.social_scores[symbol] = sentiment
    
    def record_liquidation(self, side: str, value_usd: float):
        """Record liquidation"""
        if side.upper() == 'LONG':
            self.long_liqs.append(value_usd)
        else:
            self.short_liqs.append(value_usd)
    
    def calculate(self) -> FearGreedIndex:
        """Calculate current Fear & Greed Index"""
        components = FearGreedComponents()
        
        # 1. Volatility component (inverted - high vol = fear)
        components.volatility = self._calc_volatility_component()
        
        # 2. Momentum component
        components.momentum = self._calc_momentum_component()
        
        # 3. Volume component
        components.volume = self._calc_volume_component()
        
        # 4. Social component
        components.social = self._calc_social_component()
        
        # 5. Funding component
        components.funding = self._calc_funding_component()
        
        # 6. Dominance component
        components.dominance = self._calc_dominance_component()
        
        # 7. Liquidation component
        components.liquidations = self._calc_liquidation_component()
        
        # Calculate weighted index
        value = int(
            components.volatility * self.WEIGHTS['volatility'] +
            components.momentum * self.WEIGHTS['momentum'] +
            components.volume * self.WEIGHTS['volume'] +
            components.social * self.WEIGHTS['social'] +
            components.funding * self.WEIGHTS['funding'] +
            components.dominance * self.WEIGHTS['dominance'] +
            components.liquidations * self.WEIGHTS['liquidations']
        )
        
        value = max(0, min(100, value))
        
        # Determine level
        level = self._get_level(value)
        
        # Get previous value
        previous = self.current.value if self.current else 50
        
        # Historical stats
        history_values = [h.value for h in self.history]
        recent_7d = history_values[-7*24:] if len(history_values) >= 7*24 else history_values
        recent_30d = history_values[-30*24:] if len(history_values) >= 30*24 else history_values
        
        # Create index
        index = FearGreedIndex(
            timestamp=int(time.time() * 1000),
            value=value,
            level=level,
            previous_value=previous,
            change=value - previous,
            components=components,
            avg_7d=statistics.mean(recent_7d) if recent_7d else 50,
            avg_30d=statistics.mean(recent_30d) if recent_30d else 50,
            high_30d=max(recent_30d) if recent_30d else 100,
            low_30d=min(recent_30d) if recent_30d else 0
        )
        
        # Interpretation
        index.interpretation = self._get_interpretation(value, level)
        index.signal = self._get_signal(value, level)
        
        # Store
        self.current = index
        self.history.append(index)
        
        # Stats
        self.stats['calculations'] += 1
        if level == FearGreedLevel.EXTREME_FEAR:
            self.stats['extreme_fear_count'] += 1
        elif level == FearGreedLevel.EXTREME_GREED:
            self.stats['extreme_greed_count'] += 1
        
        return index
    
    def _calc_volatility_component(self) -> float:
        """Calculate volatility component (inverted)"""
        if not self.volatility_data:
            return 50
        
        recent = [d['value'] for d in list(self.volatility_data)[-10:]]
        avg_vol = sum(recent) / len(recent)
        
        # Invert: high volatility = fear (low score)
        return max(0, min(100, 100 - avg_vol))
    
    def _calc_momentum_component(self) -> float:
        """Calculate momentum component"""
        if 'BTC_USDT' not in self.price_data:
            return 50
        
        prices = [d['price'] for d in self.price_data['BTC_USDT']]
        
        if len(prices) < 10:
            return 50
        
        # Compare recent to older
        recent = prices[-5:]
        older = prices[-20:-10] if len(prices) >= 20 else prices[:5]
        
        if not older:
            return 50
        
        change = (sum(recent)/len(recent) - sum(older)/len(older)) / (sum(older)/len(older)) * 100
        
        # Map change to 0-100
        # +10% change = 100 (extreme greed)
        # -10% change = 0 (extreme fear)
        return max(0, min(100, 50 + change * 5))
    
    def _calc_volume_component(self) -> float:
        """Calculate volume component"""
        if not self.volume_data:
            return 50
        
        # Compare recent volume to average
        total_recent = 0
        total_avg = 0
        
        for symbol, vols in self.volume_data.items():
            vol_list = list(vols)
            if len(vol_list) >= 10:
                total_recent += sum(vol_list[-5:]) / 5
                total_avg += sum(vol_list) / len(vol_list)
        
        if total_avg == 0:
            return 50
        
        ratio = total_recent / total_avg
        
        # High volume = greed
        return max(0, min(100, ratio * 50))
    
    def _calc_social_component(self) -> float:
        """Calculate social sentiment component"""
        if not self.social_scores:
            return 50
        
        avg_sentiment = sum(self.social_scores.values()) / len(self.social_scores)
        
        # Map -1 to 1 → 0 to 100
        return max(0, min(100, (avg_sentiment + 1) * 50))
    
    def _calc_funding_component(self) -> float:
        """Calculate funding rate component"""
        if not self.funding_data:
            return 50
        
        avg_funding = sum(self.funding_data.values()) / len(self.funding_data)
        
        # High positive funding = greed
        # High negative funding = fear
        # Map funding (-0.1% to +0.1%) to 0-100
        return max(0, min(100, 50 + avg_funding * 500))
    
    def _calc_dominance_component(self) -> float:
        """Calculate BTC dominance component"""
        # Would need dominance data from external source
        # For now, estimate from alt performance
        return 50  # Neutral
    
    def _calc_liquidation_component(self) -> float:
        """Calculate liquidation component"""
        long_total = sum(self.long_liqs) if self.long_liqs else 0
        short_total = sum(self.short_liqs) if self.short_liqs else 0
        
        if long_total + short_total == 0:
            return 50
        
        # More long liquidations = fear
        # More short liquidations = greed
        ratio = short_total / (long_total + short_total) * 100
        
        return max(0, min(100, ratio))
    
    def _get_level(self, value: int) -> FearGreedLevel:
        """Get fear/greed level from value"""
        if value <= 20:
            return FearGreedLevel.EXTREME_FEAR
        elif value <= 40:
            return FearGreedLevel.FEAR
        elif value <= 60:
            return FearGreedLevel.NEUTRAL
        elif value <= 80:
            return FearGreedLevel.GREED
        else:
            return FearGreedLevel.EXTREME_GREED
    
    def _get_interpretation(self, value: int, level: FearGreedLevel) -> str:
        """Get interpretation text"""
        interpretations = {
            FearGreedLevel.EXTREME_FEAR: "Market is in extreme fear. Historical opportunity to buy.",
            FearGreedLevel.FEAR: "Market is fearful. Caution but potential opportunities.",
            FearGreedLevel.NEUTRAL: "Market is neutral. No strong bias.",
            FearGreedLevel.GREED: "Market is greedy. Be cautious of overextension.",
            FearGreedLevel.EXTREME_GREED: "Extreme greed! High risk of reversal. Consider taking profits."
        }
        return interpretations.get(level, "")
    
    def _get_signal(self, value: int, level: FearGreedLevel) -> str:
        """Get trading signal"""
        if level == FearGreedLevel.EXTREME_FEAR:
            return "BUY"  # Contrarian
        elif level == FearGreedLevel.EXTREME_GREED:
            return "SELL"  # Contrarian
        else:
            return "HOLD"
    
    def get_index(self) -> int:
        """Get current index value"""
        return self.current.value if self.current else 50
    
    def get_level(self) -> FearGreedLevel:
        """Get current level"""
        return self.current.level if self.current else FearGreedLevel.NEUTRAL
    
    def is_extreme(self) -> bool:
        """Check if in extreme zone"""
        if not self.current:
            return False
        return self.current.level in [
            FearGreedLevel.EXTREME_FEAR,
            FearGreedLevel.EXTREME_GREED
        ]
    
    def get_ascii_gauge(self) -> str:
        """Generate ASCII gauge visualization"""
        value = self.current.value if self.current else 50
        level = self.current.level if self.current else FearGreedLevel.NEUTRAL
        
        # Create gauge
        filled = value // 5
        gauge = "█" * filled + "░" * (20 - filled)
        
        # Emoji
        emojis = {
            FearGreedLevel.EXTREME_FEAR: "😱",
            FearGreedLevel.FEAR: "😨",
            FearGreedLevel.NEUTRAL: "😐",
            FearGreedLevel.GREED: "🤑",
            FearGreedLevel.EXTREME_GREED: "🔥"
        }
        
        emoji = emojis.get(level, "😐")
        
        return f"""
{emoji} Fear & Greed Index: {value}/100
[{gauge}]
Level: {level.value}
Signal: {self.current.signal if self.current else 'N/A'}
"""
    
    def get_components_breakdown(self) -> str:
        """Get detailed components breakdown"""
        if not self.current:
            return "No data"
        
        c = self.current.components
        
        return f"""
📊 Fear & Greed Components
━━━━━━━━━━━━━━━━━━━━━
Volatility:    {c.volatility:.0f}/100 (weight: {self.WEIGHTS['volatility']*100:.0f}%)
Momentum:      {c.momentum:.0f}/100 (weight: {self.WEIGHTS['momentum']*100:.0f}%)
Volume:        {c.volume:.0f}/100 (weight: {self.WEIGHTS['volume']*100:.0f}%)
Social:        {c.social:.0f}/100 (weight: {self.WEIGHTS['social']*100:.0f}%)
Funding:       {c.funding:.0f}/100 (weight: {self.WEIGHTS['funding']*100:.0f}%)
Dominance:     {c.dominance:.0f}/100 (weight: {self.WEIGHTS['dominance']*100:.0f}%)
Liquidations:  {c.liquidations:.0f}/100 (weight: {self.WEIGHTS['liquidations']*100:.0f}%)
━━━━━━━━━━━━━━━━━━━━━
Final Index:   {self.current.value}/100
"""

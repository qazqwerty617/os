"""
MEXC Pump Monitor - Fear & Greed Index
Optimized custom fear/greed calculation
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


# Level thresholds
LEVEL_THRESHOLDS = [
    (81, FearGreedLevel.EXTREME_GREED),
    (61, FearGreedLevel.GREED),
    (41, FearGreedLevel.NEUTRAL),
    (21, FearGreedLevel.FEAR),
    (0, FearGreedLevel.EXTREME_FEAR),
]

# Level emojis
LEVEL_EMOJIS = {
    FearGreedLevel.EXTREME_FEAR: "😱",
    FearGreedLevel.FEAR: "😨",
    FearGreedLevel.NEUTRAL: "😐",
    FearGreedLevel.GREED: "🤑",
    FearGreedLevel.EXTREME_GREED: "🔥"
}

# Interpretations
INTERPRETATIONS = {
    FearGreedLevel.EXTREME_FEAR: "Market in extreme fear. Historical opportunity to buy.",
    FearGreedLevel.FEAR: "Market fearful. Caution but potential opportunities.",
    FearGreedLevel.NEUTRAL: "Market neutral. No strong bias.",
    FearGreedLevel.GREED: "Market greedy. Be cautious of overextension.",
    FearGreedLevel.EXTREME_GREED: "Extreme greed! High risk of reversal."
}


@dataclass
class FearGreedComponents:
    """Individual components"""
    volatility: float = 50
    momentum: float = 50
    volume: float = 50
    social: float = 50
    funding: float = 50
    dominance: float = 50
    liquidations: float = 50
    
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
    value: int
    level: FearGreedLevel
    previous_value: int = 50
    change: int = 0
    components: FearGreedComponents = field(default_factory=FearGreedComponents)
    avg_7d: float = 50
    avg_30d: float = 50
    high_30d: int = 100
    low_30d: int = 0
    interpretation: str = ""
    signal: str = ""
    
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
    """Optimized Fear & Greed Index calculator"""
    
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
        self.history: deque = deque(maxlen=1000)
        self.current: Optional[FearGreedIndex] = None
        
        self.volatility_data: deque = deque(maxlen=100)
        self.price_data: Dict[str, deque] = {}
        self.volume_data: Dict[str, deque] = {}
        self.funding_data: Dict[str, float] = {}
        self.social_scores: Dict[str, float] = {}
        self.long_liqs: deque = deque(maxlen=100)
        self.short_liqs: deque = deque(maxlen=100)
        
        self.stats = {
            'calculations': 0,
            'extreme_fear_count': 0,
            'extreme_greed_count': 0
        }
    
    def record_volatility(self, vol_index: float):
        self.volatility_data.append({'value': vol_index, 'timestamp': int(time.time() * 1000)})
    
    def record_price(self, symbol: str, price: float):
        if symbol not in self.price_data:
            self.price_data[symbol] = deque(maxlen=100)
        self.price_data[symbol].append({'price': price, 'timestamp': int(time.time() * 1000)})
    
    def record_volume(self, symbol: str, volume: float):
        if symbol not in self.volume_data:
            self.volume_data[symbol] = deque(maxlen=100)
        self.volume_data[symbol].append(volume)
    
    def record_funding(self, symbol: str, rate: float):
        self.funding_data[symbol] = rate
    
    def record_social(self, symbol: str, sentiment: float):
        self.social_scores[symbol] = sentiment
    
    def record_liquidation(self, side: str, value_usd: float):
        target = self.long_liqs if side.upper() == 'LONG' else self.short_liqs
        target.append(value_usd)
    
    def calculate(self) -> FearGreedIndex:
        """Calculate current Fear & Greed Index"""
        c = FearGreedComponents(
            volatility=self._calc_volatility(),
            momentum=self._calc_momentum(),
            volume=self._calc_volume(),
            social=self._calc_social(),
            funding=self._calc_funding(),
            dominance=50,  # Placeholder
            liquidations=self._calc_liquidations()
        )
        
        # Weighted sum
        value = int(sum(
            getattr(c, name) * weight
            for name, weight in self.WEIGHTS.items()
        ))
        value = max(0, min(100, value))
        
        level = self._get_level(value)
        previous = self.current.value if self.current else 50
        
        # Historical stats
        history_values = [h.value for h in self.history]
        recent_7d = history_values[-168:] if len(history_values) >= 168 else history_values
        recent_30d = history_values[-720:] if len(history_values) >= 720 else history_values
        
        index = FearGreedIndex(
            timestamp=int(time.time() * 1000),
            value=value,
            level=level,
            previous_value=previous,
            change=value - previous,
            components=c,
            avg_7d=statistics.mean(recent_7d) if recent_7d else 50,
            avg_30d=statistics.mean(recent_30d) if recent_30d else 50,
            high_30d=max(recent_30d) if recent_30d else 100,
            low_30d=min(recent_30d) if recent_30d else 0,
            interpretation=INTERPRETATIONS.get(level, ""),
            signal=self._get_signal(level)
        )
        
        self.current = index
        self.history.append(index)
        
        self.stats['calculations'] += 1
        if level == FearGreedLevel.EXTREME_FEAR:
            self.stats['extreme_fear_count'] += 1
        elif level == FearGreedLevel.EXTREME_GREED:
            self.stats['extreme_greed_count'] += 1
        
        return index
    
    def _calc_volatility(self) -> float:
        if not self.volatility_data:
            return 50
        recent = [d['value'] for d in list(self.volatility_data)[-10:]]
        return max(0, min(100, 100 - sum(recent) / len(recent)))
    
    def _calc_momentum(self) -> float:
        if 'BTC_USDT' not in self.price_data:
            return 50
        prices = [d['price'] for d in self.price_data['BTC_USDT']]
        if len(prices) < 10:
            return 50
        
        recent_avg = sum(prices[-5:]) / 5
        older_avg = sum(prices[-20:-10]) / 10 if len(prices) >= 20 else sum(prices[:5]) / 5
        
        if older_avg == 0:
            return 50
        
        change = ((recent_avg - older_avg) / older_avg) * 100
        return max(0, min(100, 50 + change * 5))
    
    def _calc_volume(self) -> float:
        if not self.volume_data:
            return 50
        
        total_recent, total_avg = 0, 0
        for vols in self.volume_data.values():
            vol_list = list(vols)
            if len(vol_list) >= 10:
                total_recent += sum(vol_list[-5:]) / 5
                total_avg += sum(vol_list) / len(vol_list)
        
        if total_avg == 0:
            return 50
        return max(0, min(100, (total_recent / total_avg) * 50))
    
    def _calc_social(self) -> float:
        if not self.social_scores:
            return 50
        avg = sum(self.social_scores.values()) / len(self.social_scores)
        return max(0, min(100, (avg + 1) * 50))
    
    def _calc_funding(self) -> float:
        if not self.funding_data:
            return 50
        avg = sum(self.funding_data.values()) / len(self.funding_data)
        return max(0, min(100, 50 + avg * 500))
    
    def _calc_liquidations(self) -> float:
        long_total = sum(self.long_liqs) if self.long_liqs else 0
        short_total = sum(self.short_liqs) if self.short_liqs else 0
        total = long_total + short_total
        
        if total == 0:
            return 50
        return max(0, min(100, (short_total / total) * 100))
    
    @staticmethod
    def _get_level(value: int) -> FearGreedLevel:
        for threshold, level in LEVEL_THRESHOLDS:
            if value >= threshold:
                return level
        return FearGreedLevel.EXTREME_FEAR
    
    @staticmethod
    def _get_signal(level: FearGreedLevel) -> str:
        if level == FearGreedLevel.EXTREME_FEAR:
            return "BUY"
        elif level == FearGreedLevel.EXTREME_GREED:
            return "SELL"
        return "HOLD"
    
    def get_index(self) -> int:
        return self.current.value if self.current else 50
    
    def get_level(self) -> FearGreedLevel:
        return self.current.level if self.current else FearGreedLevel.NEUTRAL
    
    def is_extreme(self) -> bool:
        if not self.current:
            return False
        return self.current.level in (FearGreedLevel.EXTREME_FEAR, FearGreedLevel.EXTREME_GREED)
    
    def get_ascii_gauge(self) -> str:
        value = self.current.value if self.current else 50
        level = self.current.level if self.current else FearGreedLevel.NEUTRAL
        
        filled = value // 5
        gauge = "█" * filled + "░" * (20 - filled)
        emoji = LEVEL_EMOJIS.get(level, "😐")
        
        return f"""
{emoji} Fear & Greed Index: {value}/100
[{gauge}]
Level: {level.value}
Signal: {self.current.signal if self.current else 'N/A'}
"""
    
    def get_components_breakdown(self) -> str:
        if not self.current:
            return "No data"
        
        c = self.current.components
        lines = [
            "📊 Fear & Greed Components",
            "━━━━━━━━━━━━━━━━━━━━━"
        ]
        
        for name, weight in self.WEIGHTS.items():
            val = getattr(c, name)
            lines.append(f"{name.capitalize():14s} {val:.0f}/100 (weight: {weight*100:.0f}%)")
        
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━━━",
            f"Final Index:   {self.current.value}/100"
        ])
        
        return "\n".join(lines)

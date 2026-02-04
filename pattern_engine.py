"""
MEXC Pump Monitor - Pattern Recognition Engine
Optimized pump/dump pattern detection and prediction
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Detected pattern types"""
    # Pump patterns
    VERTICAL_PUMP = "VERTICAL_PUMP"
    STAIR_STEP_PUMP = "STAIR_STEP_PUMP"
    FOMO_SPIKE = "FOMO_SPIKE"
    
    # Top patterns (reversal signals)
    DOUBLE_TOP = "DOUBLE_TOP"
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    BLOW_OFF_TOP = "BLOW_OFF_TOP"
    EXHAUSTION = "EXHAUSTION"
    
    # Dump patterns
    WATERFALL = "WATERFALL"
    DEAD_CAT_BOUNCE = "DEAD_CAT_BOUNCE"
    CAPITULATION = "CAPITULATION"
    
    # Accumulation/Distribution
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    
    # Manipulation
    STOP_HUNT = "STOP_HUNT"
    FAKE_BREAKOUT = "FAKE_BREAKOUT"
    WASH_TRADING = "WASH_TRADING"


@dataclass
class Pattern:
    """Detected pattern"""
    type: PatternType
    symbol: str
    timestamp: int
    start_time: int
    start_price: float
    peak_price: float
    current_price: float
    price_change_pct: float
    duration_minutes: int
    volume_profile: str
    confidence: int
    expected_move: str
    target_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'type': self.type.value,
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price_change_pct': self.price_change_pct,
            'duration_minutes': self.duration_minutes,
            'confidence': self.confidence,
            'expected_move': self.expected_move,
            'target_price': self.target_price,
            'notes': self.notes
        }


@dataclass
class PricePoint:
    """Price data point"""
    timestamp: int
    price: float
    volume: float
    is_high: bool = False
    is_low: bool = False


class PatternRecognition:
    """
    Optimized pattern recognition for pump/dump detection
    """
    
    def __init__(self, lookback_minutes: int = 60):
        self.lookback_minutes = lookback_minutes
        self.price_history: Dict[str, deque] = {}
        self.max_history = 1000
        self.patterns: Dict[str, List[Pattern]] = {}
        
        self.stats = {
            'patterns_detected': 0,
            'by_type': {}
        }
    
    def record_price(self, symbol: str, price: float, volume: float, timestamp: int = None):
        """Record price point"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.max_history)
        
        self.price_history[symbol].append(PricePoint(timestamp=timestamp, price=price, volume=volume))
        
        if len(self.price_history[symbol]) > 10:
            self._mark_swing_points(symbol)
    
    def _mark_swing_points(self, symbol: str):
        """Mark swing highs and lows"""
        history = list(self.price_history[symbol])
        
        for i in range(2, len(history) - 2):
            prices = [history[j].price for j in range(i-2, i+3)]
            history[i].is_high = prices[2] == max(prices)
            history[i].is_low = prices[2] == min(prices)
    
    def analyze(self, symbol: str) -> List[Pattern]:
        """Analyze and detect patterns"""
        if symbol not in self.price_history:
            return []
        
        history = list(self.price_history[symbol])
        if len(history) < 20:
            return []
        
        patterns = []
        
        # Detection methods
        detectors = [
            self._detect_pump_pattern,
            self._detect_top_pattern,
            self._detect_exhaustion,
            self._detect_manipulation
        ]
        
        for detector in detectors:
            pattern = detector(symbol, history)
            if pattern:
                patterns.append(pattern)
                self.stats['patterns_detected'] += 1
                self.stats['by_type'][pattern.type.value] = self.stats['by_type'].get(pattern.type.value, 0) + 1
        
        if patterns:
            self.patterns[symbol] = patterns
        
        return patterns
    
    def _detect_pump_pattern(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect pump patterns"""
        now = int(time.time() * 1000)
        recent = [p for p in history if now - p.timestamp < 900000]  # 15 min
        
        if len(recent) < 10:
            return None
        
        start_price = recent[0].price
        current_price = recent[-1].price
        peak_price = max(p.price for p in recent)
        
        peak_change = ((peak_price - start_price) / start_price) * 100
        if peak_change < 10:
            return None
        
        # Volume profile
        half = len(recent) // 2
        first_vol = sum(p.volume for p in recent[:half])
        second_vol = sum(p.volume for p in recent[half:])
        
        if second_vol > first_vol * 2:
            vol_profile = "SPIKE"
        elif second_vol > first_vol * 1.2:
            vol_profile = "INCREASING"
        elif second_vol < first_vol * 0.8:
            vol_profile = "DECREASING"
        else:
            vol_profile = "FLAT"
        
        # Count pullbacks
        prices = [p.price for p in recent]
        pullbacks = sum(1 for i in range(2, len(prices)) if prices[i] < prices[i-1] < prices[i-2])
        
        # Determine type
        if pullbacks < 2 and peak_change > 20:
            pattern_type, confidence = PatternType.VERTICAL_PUMP, 80
        elif pullbacks >= 3:
            pattern_type, confidence = PatternType.STAIR_STEP_PUMP, 70
        elif vol_profile == "SPIKE":
            pattern_type, confidence = PatternType.FOMO_SPIKE, 85
        else:
            return None
        
        return Pattern(
            type=pattern_type,
            symbol=symbol,
            timestamp=now,
            start_time=recent[0].timestamp,
            start_price=start_price,
            peak_price=peak_price,
            current_price=current_price,
            price_change_pct=((current_price - start_price) / start_price) * 100,
            duration_minutes=(recent[-1].timestamp - recent[0].timestamp) // 60000,
            volume_profile=vol_profile,
            confidence=confidence,
            expected_move="DOWN",
            target_price=current_price * 0.9,
            notes=[f"Peak: +{peak_change:.1f}%", f"Volume: {vol_profile}", f"Pullbacks: {pullbacks}"]
        )
    
    def _detect_top_pattern(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect double top pattern"""
        now = int(time.time() * 1000)
        
        highs = [p for p in history if p.is_high and now - p.timestamp < 1800000]
        if len(highs) < 2:
            return None
        
        h1, h2 = highs[-2], highs[-1]
        if abs(h1.price - h2.price) / h1.price * 100 >= 2:
            return None
        
        current = history[-1]
        vol_profile = "DECREASING" if h2.volume < h1.volume * 0.8 else "FLAT"
        confidence = 85 if h2.volume < h1.volume * 0.8 else 65
        
        neckline = min(p.price for p in history if h1.timestamp < p.timestamp < h2.timestamp)
        target = neckline - (h1.price - neckline)
        
        return Pattern(
            type=PatternType.DOUBLE_TOP,
            symbol=symbol,
            timestamp=now,
            start_time=h1.timestamp,
            start_price=h1.price,
            peak_price=max(h1.price, h2.price),
            current_price=current.price,
            price_change_pct=((current.price - h1.price) / h1.price) * 100,
            duration_minutes=(h2.timestamp - h1.timestamp) // 60000,
            volume_profile=vol_profile,
            confidence=confidence,
            expected_move="DOWN",
            target_price=target,
            invalidation_price=max(h1.price, h2.price) * 1.02,
            notes=["Double top detected", f"Neckline: {neckline:.8f}", f"Target: {target:.8f}"]
        )
    
    def _detect_exhaustion(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect volume exhaustion"""
        now = int(time.time() * 1000)
        recent = history[-30:] if len(history) >= 30 else list(history)
        
        if len(recent) < 20:
            return None
        
        half = len(recent) // 2
        first_half, second_half = recent[:half], recent[half:]
        
        first_high = max(p.price for p in first_half)
        second_high = max(p.price for p in second_half)
        first_vol = sum(p.volume for p in first_half)
        second_vol = sum(p.volume for p in second_half)
        
        if second_high > first_high and second_vol < first_vol * 0.7:
            current = recent[-1]
            vol_drop = (first_vol - second_vol) / first_vol * 100
            
            return Pattern(
                type=PatternType.EXHAUSTION,
                symbol=symbol,
                timestamp=now,
                start_time=recent[0].timestamp,
                start_price=recent[0].price,
                peak_price=second_high,
                current_price=current.price,
                price_change_pct=((current.price - recent[0].price) / recent[0].price) * 100,
                duration_minutes=(recent[-1].timestamp - recent[0].timestamp) // 60000,
                volume_profile="DECREASING",
                confidence=75,
                expected_move="DOWN",
                target_price=first_high * 0.95,
                notes=["Volume exhaustion", f"Vol drop: {vol_drop:.1f}%", "Bearish divergence"]
            )
        return None
    
    def _detect_manipulation(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect stop hunt"""
        now = int(time.time() * 1000)
        recent = [p for p in history if now - p.timestamp < 300000]  # 5 min
        
        if len(recent) < 10:
            return None
        
        prices = [p.price for p in recent]
        range_pct = (max(prices) - min(prices)) / min(prices) * 100
        
        if range_pct <= 5:
            return None
        
        high_idx = prices.index(max(prices))
        low_idx = prices.index(min(prices))
        
        if abs(high_idx - len(prices)) >= 3 and abs(low_idx - len(prices)) >= 3:
            return None
        
        current = prices[-1]
        avg_price = statistics.mean(prices)
        
        if abs(current - avg_price) / avg_price < 0.01:
            return Pattern(
                type=PatternType.STOP_HUNT,
                symbol=symbol,
                timestamp=now,
                start_time=recent[0].timestamp,
                start_price=recent[0].price,
                peak_price=max(prices),
                current_price=current,
                price_change_pct=((current - recent[0].price) / recent[0].price) * 100,
                duration_minutes=5,
                volume_profile="SPIKE",
                confidence=70,
                expected_move="SIDEWAYS",
                notes=["Stop hunt detected", f"Range: {range_pct:.1f}%", "Quick spike reversal"]
            )
        return None
    
    def get_patterns(self, symbol: str) -> List[Pattern]:
        return self.patterns.get(symbol, [])
    
    def get_all_recent_patterns(self, minutes: int = 30) -> List[Pattern]:
        cutoff = int(time.time() * 1000) - (minutes * 60000)
        return sorted(
            [p for patterns in self.patterns.values() for p in patterns if p.timestamp > cutoff],
            key=lambda p: p.timestamp, reverse=True
        )
    
    def get_high_confidence_patterns(self, min_confidence: int = 75) -> List[Pattern]:
        return [p for p in self.get_all_recent_patterns() if p.confidence >= min_confidence]


class SmartFilter:
    """Smart filtering - MEMECOIN OPTIMIZED (не переборщить с фильтрами)"""
    
    # СНИЖЕНЫ пороги для мемкоинов
    DEFAULT_THRESHOLDS = {'large': 200_000, 'mid': 50_000, 'small': 20_000}  # Было 500k/100k/50k
    
    def __init__(self):
        self.blacklist: set = set()
        self.whitelist: set = set()
        self.volume_thresholds = self.DEFAULT_THRESHOLDS.copy()
        self.recent_pumps: Dict[str, List[int]] = {}
        self.symbol_scores: Dict[str, int] = {}
        self.pump_history: Dict[str, int] = {}  # Для статистики
    
    def should_process(self, symbol: str, volume_24h: float, price_change: float) -> Tuple[bool, str]:
        """Check if symbol should be processed - ЛЕГКИЕ фильтры для мемкоинов"""
        if symbol in self.blacklist:
            return False, "blacklisted"
        
        # МИНИМАЛЬНЫЙ фильтр по объему (только совсем мертвые токены)
        if volume_24h < self.volume_thresholds['small']:
            # Но если цена выросла сильно (>20%), пропускаем даже с низким объемом
            if price_change < 20:
                return False, "low_volume"
        
        # Анти-спам: максимум 10 пампов в час (было 5)
        if self._is_spam(symbol):
            return False, "spam_pattern"
        
        from config import config
        # Минимальное движение - берем из конфига
        if abs(price_change) < config.pump.min_price_change_pct:
            return False, f"insufficient_move (<{config.pump.min_price_change_pct}%)"
        
        # Whitelist всегда проходит
        if symbol in self.whitelist:
            return True, "whitelisted"
        
        return True, "passed"
    
    def _is_spam(self, symbol: str) -> bool:
        """Анти-спам фильтр - увеличен лимит для мемкоинов"""
        now = int(time.time() * 1000)
        hour_ago = now - 3600000
        
        pumps = self.recent_pumps.get(symbol, [])
        return len([t for t in pumps if t > hour_ago]) > 10  # Было 5, стало 10 для мемкоинов
    
    def record_pump(self, symbol: str):
        """Записать памп в историю"""
        if symbol not in self.recent_pumps:
            self.recent_pumps[symbol] = []
        
        now = int(time.time() * 1000)
        hour_ago = now - 3600000
        
        self.recent_pumps[symbol].append(now)
        self.recent_pumps[symbol] = [t for t in self.recent_pumps[symbol] if t > hour_ago]
        
        # Также записываем в pump_history для статистики
        self.pump_history[symbol] = now
    
    def add_to_blacklist(self, symbol: str, reason: str = ""):
        self.blacklist.add(symbol)
        logger.info(f"Blacklisted: {symbol} ({reason})")
    
    def add_to_whitelist(self, symbol: str):
        self.whitelist.add(symbol)
    
    def update_score(self, symbol: str, delta: int):
        if symbol not in self.symbol_scores:
            self.symbol_scores[symbol] = 50
        
        self.symbol_scores[symbol] = max(0, min(100, self.symbol_scores[symbol] + delta))
        
        if self.symbol_scores[symbol] < 10:
            self.add_to_blacklist(symbol, "low_quality_score")
    
    def get_score(self, symbol: str) -> int:
        return self.symbol_scores.get(symbol, 50)

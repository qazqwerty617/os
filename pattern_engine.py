"""
MEXC Pump Monitor - Pattern Recognition Engine
Identifies pump/dump patterns and predicts reversals
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
    VERTICAL_PUMP = "VERTICAL_PUMP"         # Straight up, no pullback
    STAIR_STEP_PUMP = "STAIR_STEP_PUMP"     # Pump with consolidations
    FOMO_SPIKE = "FOMO_SPIKE"               # Exponential acceleration
    
    # Top patterns (reversal signals)
    DOUBLE_TOP = "DOUBLE_TOP"               # Classic double top
    HEAD_SHOULDERS = "HEAD_SHOULDERS"       # H&S pattern
    BLOW_OFF_TOP = "BLOW_OFF_TOP"           # Extreme volume spike at top
    EXHAUSTION = "EXHAUSTION"               # Volume declining on new highs
    
    # Dump patterns
    WATERFALL = "WATERFALL"                 # Continuous selling
    DEAD_CAT_BOUNCE = "DEAD_CAT_BOUNCE"     # Small bounce before more dump
    CAPITULATION = "CAPITULATION"           # Massive volume dump
    
    # Accumulation/Distribution
    ACCUMULATION = "ACCUMULATION"           # Smart money buying
    DISTRIBUTION = "DISTRIBUTION"           # Smart money selling
    
    # Manipulation
    STOP_HUNT = "STOP_HUNT"                 # Quick spike to trigger stops
    FAKE_BREAKOUT = "FAKE_BREAKOUT"         # Failed breakout
    WASH_TRADING = "WASH_TRADING"           # Suspicious volume patterns


@dataclass
class Pattern:
    """Detected pattern"""
    type: PatternType
    symbol: str
    timestamp: int
    
    # Pattern boundaries
    start_time: int
    start_price: float
    peak_price: float
    current_price: float
    
    # Metrics
    price_change_pct: float
    duration_minutes: int
    volume_profile: str  # "INCREASING", "DECREASING", "SPIKE"
    
    # Confidence
    confidence: int  # 0-100
    
    # Prediction
    expected_move: str  # "UP", "DOWN", "SIDEWAYS"
    target_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    
    # Extra data
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
    Advanced pattern recognition for pump/dump detection
    Uses price action, volume analysis, and statistical methods
    """
    
    def __init__(self, lookback_minutes: int = 60):
        self.lookback_minutes = lookback_minutes
        
        # Price history per symbol
        self.price_history: Dict[str, deque] = {}
        self.max_history = 1000
        
        # Detected patterns
        self.patterns: Dict[str, List[Pattern]] = {}
        
        # Stats
        self.stats = {
            'patterns_detected': 0,
            'by_type': {}
        }
    
    def record_price(
        self,
        symbol: str,
        price: float,
        volume: float,
        timestamp: int = None
    ):
        """Record price point"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.max_history)
        
        point = PricePoint(timestamp=timestamp, price=price, volume=volume)
        self.price_history[symbol].append(point)
        
        # Mark highs/lows periodically
        if len(self.price_history[symbol]) > 10:
            self._mark_swing_points(symbol)
    
    def _mark_swing_points(self, symbol: str):
        """Mark swing highs and lows"""
        history = list(self.price_history[symbol])
        
        if len(history) < 5:
            return
        
        # Check last 5 points for swing high/low
        for i in range(2, len(history) - 2):
            prices = [history[j].price for j in range(i-2, i+3)]
            
            if prices[2] == max(prices):
                history[i].is_high = True
            if prices[2] == min(prices):
                history[i].is_low = True
    
    def analyze(self, symbol: str) -> List[Pattern]:
        """
        Analyze price history and detect patterns
        
        Returns:
            List of detected patterns
        """
        if symbol not in self.price_history:
            return []
        
        history = list(self.price_history[symbol])
        
        if len(history) < 20:
            return []
        
        patterns = []
        
        # Detect various patterns
        pump_pattern = self._detect_pump_pattern(symbol, history)
        if pump_pattern:
            patterns.append(pump_pattern)
        
        top_pattern = self._detect_top_pattern(symbol, history)
        if top_pattern:
            patterns.append(top_pattern)
        
        exhaustion = self._detect_exhaustion(symbol, history)
        if exhaustion:
            patterns.append(exhaustion)
        
        manipulation = self._detect_manipulation(symbol, history)
        if manipulation:
            patterns.append(manipulation)
        
        # Store patterns
        if patterns:
            self.patterns[symbol] = patterns
            for p in patterns:
                self.stats['patterns_detected'] += 1
                self.stats['by_type'][p.type.value] = self.stats['by_type'].get(p.type.value, 0) + 1
        
        return patterns
    
    def _detect_pump_pattern(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect pump patterns"""
        now = int(time.time() * 1000)
        
        # Get recent data (last 15 minutes)
        recent = [p for p in history if now - p.timestamp < 15 * 60 * 1000]
        
        if len(recent) < 10:
            return None
        
        start_price = recent[0].price
        current_price = recent[-1].price
        peak_price = max(p.price for p in recent)
        
        # Calculate change
        change_pct = ((current_price - start_price) / start_price) * 100
        peak_change = ((peak_price - start_price) / start_price) * 100
        
        # Need significant move
        if peak_change < 10:
            return None
        
        # Analyze volume profile
        first_half_vol = sum(p.volume for p in recent[:len(recent)//2])
        second_half_vol = sum(p.volume for p in recent[len(recent)//2:])
        
        if second_half_vol > first_half_vol * 2:
            vol_profile = "SPIKE"
        elif second_half_vol > first_half_vol * 1.2:
            vol_profile = "INCREASING"
        elif second_half_vol < first_half_vol * 0.8:
            vol_profile = "DECREASING"
        else:
            vol_profile = "FLAT"
        
        # Determine pattern type
        # Check for pullbacks
        prices = [p.price for p in recent]
        pullbacks = 0
        for i in range(2, len(prices)):
            if prices[i] < prices[i-1] < prices[i-2]:
                pullbacks += 1
        
        if pullbacks < 2 and peak_change > 20:
            pattern_type = PatternType.VERTICAL_PUMP
            confidence = 80
        elif pullbacks >= 3:
            pattern_type = PatternType.STAIR_STEP_PUMP
            confidence = 70
        elif vol_profile == "SPIKE":
            pattern_type = PatternType.FOMO_SPIKE
            confidence = 85
        else:
            return None
        
        # Expected move (after pump, expect pullback)
        expected_move = "DOWN"
        target_price = current_price * 0.9  # 10% pullback target
        
        duration = (recent[-1].timestamp - recent[0].timestamp) // 60000
        
        return Pattern(
            type=pattern_type,
            symbol=symbol,
            timestamp=now,
            start_time=recent[0].timestamp,
            start_price=start_price,
            peak_price=peak_price,
            current_price=current_price,
            price_change_pct=change_pct,
            duration_minutes=duration,
            volume_profile=vol_profile,
            confidence=confidence,
            expected_move=expected_move,
            target_price=target_price,
            notes=[
                f"Peak change: +{peak_change:.1f}%",
                f"Volume profile: {vol_profile}",
                f"Pullbacks detected: {pullbacks}"
            ]
        )
    
    def _detect_top_pattern(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect top/reversal patterns"""
        # Get swing highs
        highs = [p for p in history if p.is_high]
        
        if len(highs) < 2:
            return None
        
        now = int(time.time() * 1000)
        recent_highs = [h for h in highs if now - h.timestamp < 30 * 60 * 1000]
        
        if len(recent_highs) < 2:
            return None
        
        # Check for double top
        h1, h2 = recent_highs[-2], recent_highs[-1]
        price_diff = abs(h1.price - h2.price) / h1.price * 100
        
        if price_diff < 2:  # Within 2% = double top
            current = history[-1]
            
            # Confirm with volume
            vol_at_h1 = h1.volume
            vol_at_h2 = h2.volume
            
            if vol_at_h2 < vol_at_h1 * 0.8:  # Lower volume on second top
                confidence = 85
            else:
                confidence = 65
            
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
                volume_profile="DECREASING" if vol_at_h2 < vol_at_h1 else "FLAT",
                confidence=confidence,
                expected_move="DOWN",
                target_price=target,
                invalidation_price=max(h1.price, h2.price) * 1.02,
                notes=[
                    "Double top formation detected",
                    f"Neckline at {neckline:.8f}",
                    f"Target: {target:.8f}"
                ]
            )
        
        return None
    
    def _detect_exhaustion(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect exhaustion patterns (divergence between price and volume)"""
        now = int(time.time() * 1000)
        
        # Get last 30 data points
        recent = history[-30:] if len(history) >= 30 else list(history)
        
        if len(recent) < 20:
            return None
        
        # Split into two halves
        first_half = recent[:len(recent)//2]
        second_half = recent[len(recent)//2:]
        
        # Price making new highs?
        first_high = max(p.price for p in first_half)
        second_high = max(p.price for p in second_half)
        price_higher = second_high > first_high
        
        # Volume declining?
        first_vol = sum(p.volume for p in first_half)
        second_vol = sum(p.volume for p in second_half)
        volume_declining = second_vol < first_vol * 0.7
        
        # Exhaustion = price up but volume down
        if price_higher and volume_declining:
            current = recent[-1]
            
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
                notes=[
                    "Volume exhaustion detected",
                    f"Volume drop: {((first_vol - second_vol) / first_vol * 100):.1f}%",
                    "Bearish divergence - price up, volume down"
                ]
            )
        
        return None
    
    def _detect_manipulation(self, symbol: str, history: List[PricePoint]) -> Optional[Pattern]:
        """Detect potential manipulation patterns"""
        now = int(time.time() * 1000)
        
        # Get last 5 minutes of data
        recent = [p for p in history if now - p.timestamp < 5 * 60 * 1000]
        
        if len(recent) < 10:
            return None
        
        prices = [p.price for p in recent]
        volumes = [p.volume for p in recent]
        
        # Check for stop hunt (quick spike and immediate reversal)
        if len(prices) >= 10:
            high_idx = prices.index(max(prices))
            low_idx = prices.index(min(prices))
            
            range_pct = (max(prices) - min(prices)) / min(prices) * 100
            
            # High volatility with quick reversal = potential stop hunt
            if range_pct > 5:
                # Check if spike was very brief
                if abs(high_idx - len(prices)) < 3 or abs(low_idx - len(prices)) < 3:
                    # Recent spike
                    current = prices[-1]
                    avg_price = statistics.mean(prices)
                    
                    if abs(current - avg_price) / avg_price < 0.01:  # Back to mean
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
                            notes=[
                                "Potential stop hunt detected",
                                f"Range: {range_pct:.1f}%",
                                "Quick spike and reversal"
                            ]
                        )
        
        return None
    
    def get_patterns(self, symbol: str) -> List[Pattern]:
        """Get detected patterns for symbol"""
        return self.patterns.get(symbol, [])
    
    def get_all_recent_patterns(self, minutes: int = 30) -> List[Pattern]:
        """Get all recent patterns across symbols"""
        cutoff = int(time.time() * 1000) - (minutes * 60 * 1000)
        
        all_patterns = []
        for patterns in self.patterns.values():
            all_patterns.extend([p for p in patterns if p.timestamp > cutoff])
        
        return sorted(all_patterns, key=lambda p: p.timestamp, reverse=True)
    
    def get_high_confidence_patterns(self, min_confidence: int = 75) -> List[Pattern]:
        """Get patterns with high confidence"""
        patterns = self.get_all_recent_patterns()
        return [p for p in patterns if p.confidence >= min_confidence]


class SmartFilter:
    """
    Smart filtering to reduce noise and focus on quality signals
    """
    
    def __init__(self):
        # Blacklist (symbols to ignore)
        self.blacklist: set = set()
        
        # Whitelist (priority symbols)
        self.whitelist: set = set()
        
        # Volume thresholds by market cap tier
        self.volume_thresholds = {
            'large': 500_000,    # >$1B mcap
            'mid': 100_000,      # $100M-$1B mcap
            'small': 50_000,     # <$100M mcap
        }
        
        # Spam detection
        self.recent_pumps: Dict[str, List[int]] = {}  # symbol -> list of pump timestamps
        
        # Quality scores
        self.symbol_scores: Dict[str, int] = {}
    
    def should_process(
        self,
        symbol: str,
        volume_24h: float,
        price_change: float
    ) -> Tuple[bool, str]:
        """
        Check if symbol should be processed
        
        Returns:
            (should_process, reason)
        """
        # Blacklist check
        if symbol in self.blacklist:
            return False, "blacklisted"
        
        # Volume check
        if volume_24h < self.volume_thresholds['small']:
            return False, "low_volume"
        
        # Spam check (too many pumps = suspicious)
        if self._is_spam(symbol):
            return False, "spam_pattern"
        
        # Minimum price change
        # Minimum price change from config
        from config import config
        if abs(price_change) < config.pump.min_price_change_pct:
            return False, f"insufficient_move (<{config.pump.min_price_change_pct}%)"
        
        # Whitelist gets priority
        if symbol in self.whitelist:
            return True, "whitelisted"
        
        return True, "passed"
    
    def _is_spam(self, symbol: str) -> bool:
        """Check if symbol has spam-like patterns"""
        now = int(time.time() * 1000)
        hour_ago = now - 3600000
        
        if symbol not in self.recent_pumps:
            return False
        
        # Count pumps in last hour
        recent_count = len([t for t in self.recent_pumps[symbol] if t > hour_ago])
        
        # More than 5 "pumps" in an hour = suspicious
        return recent_count > 5
    
    def record_pump(self, symbol: str):
        """Record a pump event"""
        if symbol not in self.recent_pumps:
            self.recent_pumps[symbol] = []
        
        self.recent_pumps[symbol].append(int(time.time() * 1000))
        
        # Cleanup old data
        hour_ago = int(time.time() * 1000) - 3600000
        self.recent_pumps[symbol] = [t for t in self.recent_pumps[symbol] if t > hour_ago]
    
    def add_to_blacklist(self, symbol: str, reason: str = ""):
        """Add symbol to blacklist"""
        self.blacklist.add(symbol)
        logger.info(f"Blacklisted: {symbol} ({reason})")
    
    def add_to_whitelist(self, symbol: str):
        """Add symbol to whitelist"""
        self.whitelist.add(symbol)
    
    def update_score(self, symbol: str, delta: int):
        """Update symbol quality score"""
        if symbol not in self.symbol_scores:
            self.symbol_scores[symbol] = 50
        
        self.symbol_scores[symbol] = max(0, min(100, self.symbol_scores[symbol] + delta))
        
        # Auto-blacklist very low scores
        if self.symbol_scores[symbol] < 10:
            self.add_to_blacklist(symbol, "low_quality_score")
    
    def get_score(self, symbol: str) -> int:
        """Get symbol quality score"""
        return self.symbol_scores.get(symbol, 50)

"""
MEXC Pump Monitor - Chart Pattern CNN
Visual pattern recognition using lightweight neural network
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger("ChartPatternCNN")


class PatternType(Enum):
    # Bullish patterns
    DOUBLE_BOTTOM = "double_bottom"
    INVERSE_HEAD_SHOULDERS = "inverse_head_shoulders"
    ASCENDING_TRIANGLE = "ascending_triangle"
    CUP_AND_HANDLE = "cup_and_handle"
    BULL_FLAG = "bull_flag"
    FALLING_WEDGE = "falling_wedge"
    
    # Bearish patterns
    DOUBLE_TOP = "double_top"
    HEAD_AND_SHOULDERS = "head_and_shoulders"
    DESCENDING_TRIANGLE = "descending_triangle"
    BEAR_FLAG = "bear_flag"
    RISING_WEDGE = "rising_wedge"
    
    # Neutral/Continuation
    TRIANGLE = "triangle"
    RECTANGLE = "rectangle"
    PENNANT = "pennant"
    
    # No pattern
    NONE = "none"


@dataclass
class DetectedPattern:
    """Detected chart pattern"""
    pattern_type: PatternType
    confidence: float  # 0-100
    direction: str  # bullish, bearish, neutral
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    current_price: float = 0.0
    expected_move_pct: float = 0.0
    time_detected: datetime = field(default_factory=datetime.now)


class ChartPatternCNN:
    """
    Chart Pattern Recognition Engine
    Uses mathematical pattern detection (no heavy ML dependencies)
    
    Implements:
    - Pattern detection via geometric analysis
    - Support/Resistance identification
    - Trend channel detection
    - Volume confirmation
    """
    
    def __init__(self, lookback_periods: int = 50):
        self.lookback = lookback_periods
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.detected_patterns: Dict[str, List[DetectedPattern]] = {}
        
        logger.info(f"📊 Chart Pattern CNN initialized (lookback: {lookback_periods})")
    
    def add_candle(self, symbol: str, open_price: float, high: float, 
                  low: float, close: float, volume: float):
        """Add new candle data"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=200)
            self.volume_history[symbol] = deque(maxlen=200)
        
        candle = {
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'timestamp': datetime.now()
        }
        self.price_history[symbol].append(candle)
        self.volume_history[symbol].append(volume)
    
    def add_prices(self, symbol: str, prices: List[float], volumes: List[float] = None):
        """Add multiple price points (for quick analysis)"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=200)
            self.volume_history[symbol] = deque(maxlen=200)
        
        for i, price in enumerate(prices):
            candle = {
                'open': price,
                'high': price * 1.001,
                'low': price * 0.999,
                'close': price,
                'timestamp': datetime.now()
            }
            self.price_history[symbol].append(candle)
            if volumes and i < len(volumes):
                self.volume_history[symbol].append(volumes[i])
            else:
                self.volume_history[symbol].append(1.0)
    
    def _get_closes(self, symbol: str) -> np.ndarray:
        """Get close prices as numpy array"""
        if symbol not in self.price_history:
            return np.array([])
        return np.array([c['close'] for c in self.price_history[symbol]])
    
    def _get_highs(self, symbol: str) -> np.ndarray:
        """Get high prices"""
        if symbol not in self.price_history:
            return np.array([])
        return np.array([c['high'] for c in self.price_history[symbol]])
    
    def _get_lows(self, symbol: str) -> np.ndarray:
        """Get low prices"""
        if symbol not in self.price_history:
            return np.array([])
        return np.array([c['low'] for c in self.price_history[symbol]])
    
    def _find_local_extrema(self, data: np.ndarray, window: int = 5) -> Tuple[List[int], List[int]]:
        """Find local maxima and minima indices"""
        if len(data) < window * 2:
            return [], []
        
        maxima = []
        minima = []
        
        for i in range(window, len(data) - window):
            # Local max
            if data[i] == max(data[i-window:i+window+1]):
                maxima.append(i)
            # Local min
            if data[i] == min(data[i-window:i+window+1]):
                minima.append(i)
        
        return maxima, minima
    
    def _detect_double_top(self, symbol: str) -> Optional[DetectedPattern]:
        """Detect double top pattern (bearish)"""
        highs = self._get_highs(symbol)
        if len(highs) < 20:
            return None
        
        maxima, _ = self._find_local_extrema(highs, 3)
        if len(maxima) < 2:
            return None
        
        # Check last two maxima
        peak1_idx, peak2_idx = maxima[-2], maxima[-1]
        peak1, peak2 = highs[peak1_idx], highs[peak2_idx]
        
        # Peaks should be within 2% of each other
        if abs(peak1 - peak2) / peak1 > 0.02:
            return None
        
        # There should be a valley between them (at least 3% lower)
        valley = min(highs[peak1_idx:peak2_idx+1]) if peak2_idx > peak1_idx else peak1
        if (peak1 - valley) / peak1 < 0.03:
            return None
        
        current = highs[-1]
        target = valley - (peak1 - valley)  # Measured move
        
        return DetectedPattern(
            pattern_type=PatternType.DOUBLE_TOP,
            confidence=75,
            direction="bearish",
            target_price=target,
            stop_loss=peak1 * 1.01,
            current_price=current,
            expected_move_pct=((current - target) / current) * 100
        )
    
    def _detect_double_bottom(self, symbol: str) -> Optional[DetectedPattern]:
        """Detect double bottom pattern (bullish)"""
        lows = self._get_lows(symbol)
        if len(lows) < 20:
            return None
        
        _, minima = self._find_local_extrema(lows, 3)
        if len(minima) < 2:
            return None
        
        # Check last two minima
        trough1_idx, trough2_idx = minima[-2], minima[-1]
        trough1, trough2 = lows[trough1_idx], lows[trough2_idx]
        
        # Troughs should be within 2% of each other
        if abs(trough1 - trough2) / trough1 > 0.02:
            return None
        
        # There should be a peak between them (at least 3% higher)
        peak = max(lows[trough1_idx:trough2_idx+1]) if trough2_idx > trough1_idx else trough1
        if (peak - trough1) / trough1 < 0.03:
            return None
        
        current = lows[-1]
        target = peak + (peak - trough1)  # Measured move
        
        return DetectedPattern(
            pattern_type=PatternType.DOUBLE_BOTTOM,
            confidence=75,
            direction="bullish",
            target_price=target,
            stop_loss=trough1 * 0.99,
            current_price=current,
            expected_move_pct=((target - current) / current) * 100
        )
    
    def _detect_head_and_shoulders(self, symbol: str) -> Optional[DetectedPattern]:
        """Detect head and shoulders pattern (bearish)"""
        highs = self._get_highs(symbol)
        if len(highs) < 30:
            return None
        
        maxima, _ = self._find_local_extrema(highs, 4)
        if len(maxima) < 3:
            return None
        
        # Get last three peaks
        left_idx, head_idx, right_idx = maxima[-3], maxima[-2], maxima[-1]
        left, head, right = highs[left_idx], highs[head_idx], highs[right_idx]
        
        # Head must be higher than shoulders
        if not (head > left and head > right):
            return None
        
        # Shoulders should be roughly equal (within 5%)
        if abs(left - right) / left > 0.05:
            return None
        
        # Calculate neckline (average of valleys)
        neckline = min(highs[left_idx:right_idx+1])
        
        current = highs[-1]
        target = neckline - (head - neckline)
        
        return DetectedPattern(
            pattern_type=PatternType.HEAD_AND_SHOULDERS,
            confidence=80,
            direction="bearish",
            target_price=target,
            stop_loss=head * 1.01,
            current_price=current,
            expected_move_pct=((current - target) / current) * 100
        )
    
    def _detect_triangle(self, symbol: str) -> Optional[DetectedPattern]:
        """Detect triangle pattern (continuation)"""
        closes = self._get_closes(symbol)
        if len(closes) < 20:
            return None
        
        # Get price range over time
        recent = closes[-20:]
        early_range = max(recent[:10]) - min(recent[:10])
        late_range = max(recent[-10:]) - min(recent[-10:])
        
        # Triangle: range should be contracting
        if late_range >= early_range * 0.7:
            return None
        
        # Determine direction based on trend
        avg_early = np.mean(recent[:10])
        avg_late = np.mean(recent[-10:])
        
        if avg_late > avg_early * 1.02:
            direction = "bullish"
            pattern = PatternType.ASCENDING_TRIANGLE
        elif avg_late < avg_early * 0.98:
            direction = "bearish"
            pattern = PatternType.DESCENDING_TRIANGLE
        else:
            direction = "neutral"
            pattern = PatternType.TRIANGLE
        
        current = closes[-1]
        expected_move = early_range  # Breakout target
        
        return DetectedPattern(
            pattern_type=pattern,
            confidence=65,
            direction=direction,
            target_price=current + expected_move if direction == "bullish" else current - expected_move,
            current_price=current,
            expected_move_pct=(expected_move / current) * 100
        )
    
    def _detect_flag(self, symbol: str) -> Optional[DetectedPattern]:
        """Detect bull/bear flag pattern"""
        closes = self._get_closes(symbol)
        if len(closes) < 30:
            return None
        
        # Flag pole: strong move in first 10 candles
        pole = closes[-30:-20]
        flag = closes[-20:]
        
        pole_change = (pole[-1] - pole[0]) / pole[0]
        flag_change = (flag[-1] - flag[0]) / flag[0]
        
        # Bull flag: strong up move, slight downward consolidation
        if pole_change > 0.05 and -0.03 < flag_change < 0.01:
            return DetectedPattern(
                pattern_type=PatternType.BULL_FLAG,
                confidence=70,
                direction="bullish",
                target_price=closes[-1] + (pole[-1] - pole[0]),
                current_price=closes[-1],
                expected_move_pct=pole_change * 100
            )
        
        # Bear flag: strong down move, slight upward consolidation
        if pole_change < -0.05 and -0.01 < flag_change < 0.03:
            return DetectedPattern(
                pattern_type=PatternType.BEAR_FLAG,
                confidence=70,
                direction="bearish",
                target_price=closes[-1] - (pole[0] - pole[-1]),
                current_price=closes[-1],
                expected_move_pct=abs(pole_change) * 100
            )
        
        return None
    
    def analyze(self, symbol: str) -> List[DetectedPattern]:
        """Run all pattern detection on a symbol"""
        patterns = []
        
        detectors = [
            self._detect_double_top,
            self._detect_double_bottom,
            self._detect_head_and_shoulders,
            self._detect_triangle,
            self._detect_flag
        ]
        
        for detector in detectors:
            try:
                pattern = detector(symbol)
                if pattern:
                    patterns.append(pattern)
            except Exception as e:
                logger.debug(f"Pattern detection error: {e}")
        
        # Sort by confidence
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        
        # Store detected patterns
        self.detected_patterns[symbol] = patterns
        
        if patterns:
            logger.info(f"📊 {symbol}: Detected {len(patterns)} patterns, best: {patterns[0].pattern_type.value} ({patterns[0].confidence}%)")
        
        return patterns
    
    def get_best_pattern(self, symbol: str) -> Optional[DetectedPattern]:
        """Get highest confidence pattern for symbol"""
        patterns = self.analyze(symbol)
        return patterns[0] if patterns else None
    
    def format_telegram_alert(self, pattern: DetectedPattern, symbol: str) -> str:
        """Format pattern as Telegram message"""
        direction_emoji = {
            "bullish": "📈",
            "bearish": "📉",
            "neutral": "➖"
        }
        
        pattern_names = {
            PatternType.DOUBLE_TOP: "Double Top",
            PatternType.DOUBLE_BOTTOM: "Double Bottom", 
            PatternType.HEAD_AND_SHOULDERS: "Head & Shoulders",
            PatternType.ASCENDING_TRIANGLE: "Ascending Triangle",
            PatternType.DESCENDING_TRIANGLE: "Descending Triangle",
            PatternType.BULL_FLAG: "Bull Flag",
            PatternType.BEAR_FLAG: "Bear Flag",
            PatternType.TRIANGLE: "Triangle",
        }
        
        emoji = direction_emoji.get(pattern.direction, "❓")
        name = pattern_names.get(pattern.pattern_type, pattern.pattern_type.value)
        
        return f"""
📊 <b>PATTERN DETECTED / ПАТТЕРН</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪙 <b>Token:</b> #{symbol}
🔷 <b>Pattern:</b> {name}
🎯 <b>Direction:</b> {pattern.direction.upper()}
📊 <b>Confidence:</b> {pattern.confidence:.0f}%

<b>📍 Levels:</b>
• Current: ${pattern.current_price:.6f}
• Target: ${pattern.target_price:.6f} ({pattern.expected_move_pct:+.1f}%)
{f'• Stop Loss: ${pattern.stop_loss:.6f}' if pattern.stop_loss else ''}

<i>Pattern detected via Chart AI</i>
"""


# Convenience instance
chart_pattern_cnn = ChartPatternCNN()

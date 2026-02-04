"""
MEXC Pump Monitor - Candlestick Patterns Detector
Детекция свечных паттернов для умных уровней
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CandlePattern(Enum):
    """Типы свечных паттернов"""
    # Разворотные
    PIN_BAR_BULLISH = "PIN_BAR_BULLISH"
    PIN_BAR_BEARISH = "PIN_BAR_BEARISH"
    HAMMER = "HAMMER"
    HANGING_MAN = "HANGING_MAN"
    INVERTED_HAMMER = "INVERTED_HAMMER"
    ENGULFING_BULLISH = "ENGULFING_BULLISH"
    ENGULFING_BEARISH = "ENGULFING_BEARISH"
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    
    # Продолжения
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"
    MARUBOZU_BULLISH = "MARUBOZU_BULLISH"
    MARUBOZU_BEARISH = "MARUBOZU_BEARISH"
    
    # Нерешительность
    DOJI = "DOJI"
    LONG_LEGGED_DOJI = "LONG_LEGGED_DOJI"


@dataclass
class DetectedPattern:
    """Обнаруженный паттерн"""
    pattern_type: CandlePattern
    confidence: int  # 0-100
    price_level: float  # Уровень паттерна
    signal: str  # 'BULLISH', 'BEARISH', 'NEUTRAL'
    description: str


class CandlestickPatternDetector:
    """
    Детектор свечных паттернов
    """
    
    def __init__(self):
        self.min_body_ratio = 0.3  # Минимальное соотношение тела к диапазону
        self.min_shadow_ratio = 0.6  # Минимальное соотношение тени к диапазону
    
    def detect_patterns(self, candles: List[Dict]) -> List[DetectedPattern]:
        """
        Обнаружить паттерны в последних свечах
        
        Args:
            candles: Список свечей [{'open', 'high', 'low', 'close', 'volume'}]
        
        Returns:
            Список обнаруженных паттернов
        """
        if len(candles) < 3:
            return []
        
        patterns = []
        
        # Односвечные паттерны
        if len(candles) >= 1:
            single_patterns = self._detect_single_candle_patterns(candles[-1])
            patterns.extend(single_patterns)
        
        # Двусвечные паттерны
        if len(candles) >= 2:
            double_patterns = self._detect_double_candle_patterns(candles[-2], candles[-1])
            patterns.extend(double_patterns)
        
        # Трехсвечные паттерны
        if len(candles) >= 3:
            triple_patterns = self._detect_triple_candle_patterns(candles[-3], candles[-2], candles[-1])
            patterns.extend(triple_patterns)
        
        return patterns
    
    def _detect_single_candle_patterns(self, candle: Dict) -> List[DetectedPattern]:
        """Обнаружить односвечные паттерны"""
        patterns = []
        
        open_price = candle['open']
        high = candle['high']
        low = candle['low']
        close = candle['close']
        
        body = abs(close - open_price)
        range_size = high - low
        upper_shadow = high - max(open_price, close)
        lower_shadow = min(open_price, close) - low
        
        if range_size == 0:
            return patterns
        
        body_ratio = body / range_size
        upper_shadow_ratio = upper_shadow / range_size
        lower_shadow_ratio = lower_shadow / range_size
        
        is_bullish = close > open_price
        
        # Pin Bar (длинная тень, маленькое тело)
        if body_ratio < 0.3:
            if lower_shadow_ratio > 0.6:
                # Бычий Pin Bar
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.PIN_BAR_BULLISH,
                    confidence=75,
                    price_level=low,
                    signal='BULLISH',
                    description=f"Pin Bar (бычий) - нижняя тень {lower_shadow_ratio*100:.0f}%"
                ))
            elif upper_shadow_ratio > 0.6:
                # Медвежий Pin Bar
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.PIN_BAR_BEARISH,
                    confidence=75,
                    price_level=high,
                    signal='BEARISH',
                    description=f"Pin Bar (медвежий) - верхняя тень {upper_shadow_ratio*100:.0f}%"
                ))
        
        # Hammer (после падения)
        if not is_bullish and lower_shadow_ratio > 0.6 and body_ratio < 0.4:
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.HAMMER,
                confidence=70,
                price_level=low,
                signal='BULLISH',
                description="Hammer - разворот вверх"
            ))
        
        # Hanging Man (на хаях)
        if is_bullish and lower_shadow_ratio > 0.6 and body_ratio < 0.4:
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.HANGING_MAN,
                confidence=70,
                price_level=high,
                signal='BEARISH',
                description="Hanging Man - возможный разворот вниз"
            ))
        
        # Inverted Hammer
        if not is_bullish and upper_shadow_ratio > 0.6 and body_ratio < 0.4:
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.INVERTED_HAMMER,
                confidence=65,
                price_level=high,
                signal='BULLISH',
                description="Inverted Hammer - возможный разворот вверх"
            ))
        
        # Marubozu (без теней)
        if body_ratio > 0.9:
            if is_bullish:
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.MARUBOZU_BULLISH,
                    confidence=80,
                    price_level=close,
                    signal='BULLISH',
                    description="Marubozu бычий - сильное доминирование покупателей"
                ))
            else:
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.MARUBOZU_BEARISH,
                    confidence=80,
                    price_level=close,
                    signal='BEARISH',
                    description="Marubozu медвежий - сильное доминирование продавцов"
                ))
        
        # Doji (открытие = закрытие)
        if body_ratio < 0.1:
            if upper_shadow_ratio > 0.4 and lower_shadow_ratio > 0.4:
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.LONG_LEGGED_DOJI,
                    confidence=60,
                    price_level=(high + low) / 2,
                    signal='NEUTRAL',
                    description="Long Legged Doji - нерешительность рынка"
                ))
            else:
                patterns.append(DetectedPattern(
                    pattern_type=CandlePattern.DOJI,
                    confidence=50,
                    price_level=(high + low) / 2,
                    signal='NEUTRAL',
                    description="Doji - нерешительность"
                ))
        
        return patterns
    
    def _detect_double_candle_patterns(
        self,
        candle1: Dict,
        candle2: Dict
    ) -> List[DetectedPattern]:
        """Обнаружить двусвечные паттерны"""
        patterns = []
        
        # Engulfing
        body1 = abs(candle1['close'] - candle1['open'])
        body2 = abs(candle2['close'] - candle2['open'])
        
        is_bullish_1 = candle1['close'] > candle1['open']
        is_bullish_2 = candle2['close'] > candle2['open']
        
        # Бычье поглощение
        if not is_bullish_1 and is_bullish_2:
            if candle2['open'] < candle1['close'] and candle2['close'] > candle1['open']:
                if body2 > body1 * 1.2:
                    patterns.append(DetectedPattern(
                        pattern_type=CandlePattern.ENGULFING_BULLISH,
                        confidence=80,
                        price_level=candle2['close'],
                        signal='BULLISH',
                        description="Бычье поглощение - разворот вверх"
                    ))
        
        # Медвежье поглощение
        if is_bullish_1 and not is_bullish_2:
            if candle2['open'] > candle1['close'] and candle2['close'] < candle1['open']:
                if body2 > body1 * 1.2:
                    patterns.append(DetectedPattern(
                        pattern_type=CandlePattern.ENGULFING_BEARISH,
                        confidence=80,
                        price_level=candle2['close'],
                        signal='BEARISH',
                        description="Медвежье поглощение - разворот вниз"
                    ))
        
        # Inside Bar
        if (candle2['high'] < candle1['high'] and 
            candle2['low'] > candle1['low']):
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.INSIDE_BAR,
                confidence=60,
                price_level=(candle2['high'] + candle2['low']) / 2,
                signal='NEUTRAL',
                description="Inside Bar - сжатие перед движением"
            ))
        
        # Outside Bar
        if (candle2['high'] > candle1['high'] and 
            candle2['low'] < candle1['low']):
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.OUTSIDE_BAR,
                confidence=70,
                price_level=(candle2['high'] + candle2['low']) / 2,
                signal='NEUTRAL',
                description="Outside Bar - рост волатильности"
            ))
        
        return patterns
    
    def _detect_triple_candle_patterns(
        self,
        candle1: Dict,
        candle2: Dict,
        candle3: Dict
    ) -> List[DetectedPattern]:
        """Обнаружить трехсвечные паттерны"""
        patterns = []
        
        body1 = abs(candle1['close'] - candle1['open'])
        body2 = abs(candle2['close'] - candle2['open'])
        body3 = abs(candle3['close'] - candle3['open'])
        
        is_bullish_1 = candle1['close'] > candle1['open']
        is_bullish_2 = candle2['close'] > candle2['open']
        is_bullish_3 = candle3['close'] > candle3['open']
        
        # Morning Star (утренняя звезда)
        if (not is_bullish_1 and 
            body2 < body1 * 0.5 and body2 < body3 * 0.5 and
            is_bullish_3 and
            candle3['close'] > (candle1['open'] + candle1['close']) / 2):
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.MORNING_STAR,
                confidence=85,
                price_level=candle3['close'],
                signal='BULLISH',
                description="Morning Star - сильный разворот вверх"
            ))
        
        # Evening Star (вечерняя звезда)
        if (is_bullish_1 and
            body2 < body1 * 0.5 and body2 < body3 * 0.5 and
            not is_bullish_3 and
            candle3['close'] < (candle1['open'] + candle1['close']) / 2):
            patterns.append(DetectedPattern(
                pattern_type=CandlePattern.EVENING_STAR,
                confidence=85,
                price_level=candle3['close'],
                signal='BEARISH',
                description="Evening Star - сильный разворот вниз"
            ))
        
        return patterns

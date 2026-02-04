"""
MEXC Pump Monitor - Advanced Pattern Detector
Определение графических паттернов и свечных формаций
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Типы графических паттернов"""
    # Разворотные
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    INVERSE_HEAD_SHOULDERS = "INVERSE_HEAD_SHOULDERS"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIPLE_TOP = "TRIPLE_TOP"
    TRIPLE_BOTTOM = "TRIPLE_BOTTOM"
    
    # Продолжения
    FLAG = "FLAG"
    PENNANT = "PENNANT"
    RECTANGLE = "RECTANGLE"
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    SYMMETRIC_TRIANGLE = "SYMMETRIC_TRIANGLE"
    
    # Свечные
    PIN_BAR = "PIN_BAR"
    ENGULFING = "ENGULFING"
    DOJI = "DOJI"
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"


@dataclass
class DetectedPattern:
    """Обнаруженный паттерн"""
    pattern_type: PatternType
    symbol: str
    confidence: int  # 0-100
    price_level: float  # Ключевой уровень паттерна
    target_price: Optional[float] = None
    invalidation_price: Optional[float] = None
    timestamp: int = 0


class AdvancedPatternDetector:
    """
    Продвинутый детектор графических паттернов
    """
    
    def __init__(self):
        self.candle_history: Dict[str, deque] = {}
        self.detected_patterns: Dict[str, List[DetectedPattern]] = {}
        self.max_history = 200
    
    def add_candle(self, symbol: str, open_price: float, high: float, low: float, close: float, volume: float):
        """Добавить свечу"""
        if symbol not in self.candle_history:
            self.candle_history[symbol] = deque(maxlen=self.max_history)
        
        self.candle_history[symbol].append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    def detect_patterns(self, symbol: str) -> List[DetectedPattern]:
        """Обнаружить все паттерны для символа"""
        if symbol not in self.candle_history:
            return []
        
        candles = list(self.candle_history[symbol])
        if len(candles) < 20:
            return []
        
        patterns = []
        
        # Разворотные паттерны
        patterns.extend(self._detect_head_shoulders(symbol, candles))
        patterns.extend(self._detect_double_top_bottom(symbol, candles))
        patterns.extend(self._detect_triple_top_bottom(symbol, candles))
        
        # Свечные паттерны
        patterns.extend(self._detect_candle_patterns(symbol, candles))
        
        # Паттерны продолжения
        patterns.extend(self._detect_continuation_patterns(symbol, candles))
        
        self.detected_patterns[symbol] = patterns
        return patterns
    
    def _detect_head_shoulders(self, symbol: str, candles: List[Dict]) -> List[DetectedPattern]:
        """Обнаружить голову и плечи"""
        patterns = []
        
        if len(candles) < 30:
            return patterns
        
        # Найти локальные максимумы
        highs = []
        for i in range(3, len(candles) - 3):
            if (candles[i]['high'] > candles[i-1]['high'] and
                candles[i]['high'] > candles[i-2]['high'] and
                candles[i]['high'] > candles[i+1]['high'] and
                candles[i]['high'] > candles[i+2]['high']):
                highs.append((i, candles[i]['high']))
        
        if len(highs) < 3:
            return patterns
        
        # Искать паттерн: левое плечо < голова > правое плечо
        for i in range(len(highs) - 2):
            left_shoulder = highs[i]
            head = highs[i+1]
            right_shoulder = highs[i+2]
            
            # Проверка структуры
            if (head[1] > left_shoulder[1] and 
                head[1] > right_shoulder[1] and
                abs(left_shoulder[1] - right_shoulder[1]) / left_shoulder[1] < 0.02):  # Плечи примерно равны
                
                # Найти линию шеи (минимум между головой и правым плечом)
                neck_start = head[0]
                neck_end = right_shoulder[0]
                neck_lows = [candles[j]['low'] for j in range(neck_start, neck_end)]
                if neck_lows:
                    neckline = min(neck_lows)
                    
                    # Цель = расстояние от головы до шеи, отложенное от шеи вниз
                    target = neckline - (head[1] - neckline)
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.HEAD_SHOULDERS,
                        symbol=symbol,
                        confidence=75,
                        price_level=neckline,
                        target_price=target,
                        invalidation_price=head[1] * 1.01,
                        timestamp=int(time.time() * 1000)
                    ))
        
        return patterns
    
    def _detect_double_top_bottom(self, symbol: str, candles: List[Dict]) -> List[DetectedPattern]:
        """Обнаружить двойную вершину/дно"""
        patterns = []
        
        if len(candles) < 20:
            return patterns
        
        # Двойная вершина
        highs = []
        for i in range(2, len(candles) - 2):
            if candles[i]['high'] == max([candles[j]['high'] for j in range(i-2, i+3)]):
                highs.append((i, candles[i]['high']))
        
        for i in range(len(highs) - 1):
            h1 = highs[i]
            h2 = highs[i+1]
            
            # Два максимума примерно на одном уровне
            if abs(h1[1] - h2[1]) / h1[1] < 0.01:  # В пределах 1%
                # Найти минимум между ними (линия шеи)
                mid_lows = [candles[j]['low'] for j in range(h1[0], h2[0])]
                if mid_lows:
                    neckline = min(mid_lows)
                    target = neckline - (h1[1] - neckline)
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.DOUBLE_TOP,
                        symbol=symbol,
                        confidence=70,
                        price_level=neckline,
                        target_price=target,
                        invalidation_price=h1[1] * 1.01,
                        timestamp=int(time.time() * 1000)
                    ))
        
        # Двойное дно (аналогично)
        lows = []
        for i in range(2, len(candles) - 2):
            if candles[i]['low'] == min([candles[j]['low'] for j in range(i-2, i+3)]):
                lows.append((i, candles[i]['low']))
        
        for i in range(len(lows) - 1):
            l1 = lows[i]
            l2 = lows[i+1]
            
            if abs(l1[1] - l2[1]) / l1[1] < 0.01:
                mid_highs = [candles[j]['high'] for j in range(l1[0], l2[0])]
                if mid_highs:
                    neckline = max(mid_highs)
                    target = neckline + (neckline - l1[1])
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.DOUBLE_BOTTOM,
                        symbol=symbol,
                        confidence=70,
                        price_level=neckline,
                        target_price=target,
                        invalidation_price=l1[1] * 0.99,
                        timestamp=int(time.time() * 1000)
                    ))
        
        return patterns
    
    def _detect_candle_patterns(self, symbol: str, candles: List[Dict]) -> List[DetectedPattern]:
        """Обнаружить свечные паттерны"""
        patterns = []
        
        if len(candles) < 3:
            return patterns
        
        # Анализ последних свечей
        for i in range(max(0, len(candles) - 10), len(candles)):
            if i < 2:
                continue
            
            current = candles[i]
            prev = candles[i-1]
            
            # Pin Bar
            body = abs(current['close'] - current['open'])
            upper_shadow = current['high'] - max(current['open'], current['close'])
            lower_shadow = min(current['open'], current['close']) - current['low']
            
            if body > 0:
                if upper_shadow > body * 2 and lower_shadow < body * 0.5:
                    # Медвежий пин-бар
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.PIN_BAR,
                        symbol=symbol,
                        confidence=60,
                        price_level=current['high'],
                        timestamp=int(time.time() * 1000)
                    ))
                elif lower_shadow > body * 2 and upper_shadow < body * 0.5:
                    # Бычий пин-бар
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.PIN_BAR,
                        symbol=symbol,
                        confidence=60,
                        price_level=current['low'],
                        timestamp=int(time.time() * 1000)
                    ))
            
            # Engulfing
            if i >= 1:
                prev_body = abs(prev['close'] - prev['open'])
                current_body = abs(current['close'] - current['open'])
                
                # Бычье поглощение
                if (prev['close'] < prev['open'] and  # Предыдущая медвежья
                    current['close'] > current['open'] and  # Текущая бычья
                    current['open'] < prev['close'] and  # Открытие ниже закрытия предыдущей
                    current['close'] > prev['open']):  # Закрытие выше открытия предыдущей
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.ENGULFING,
                        symbol=symbol,
                        confidence=65,
                        price_level=current['close'],
                        timestamp=int(time.time() * 1000)
                    ))
                
                # Медвежье поглощение
                elif (prev['close'] > prev['open'] and
                      current['close'] < current['open'] and
                      current['open'] > prev['close'] and
                      current['close'] < prev['open']):
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.ENGULFING,
                        symbol=symbol,
                        confidence=65,
                        price_level=current['close'],
                        timestamp=int(time.time() * 1000)
                    ))
            
            # Inside Bar
            if i >= 1:
                if (current['high'] < prev['high'] and
                    current['low'] > prev['low']):
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.INSIDE_BAR,
                        symbol=symbol,
                        confidence=55,
                        price_level=(current['high'] + current['low']) / 2,
                        timestamp=int(time.time() * 1000)
                    ))
        
        return patterns
    
    def _detect_triple_top_bottom(self, symbol: str, candles: List[Dict]) -> List[DetectedPattern]:
        """Обнаружить тройную вершину/дно"""
        patterns = []
        
        if len(candles) < 30:
            return patterns
        
        # Тройная вершина
        highs = []
        for i in range(2, len(candles) - 2):
            if candles[i]['high'] == max([candles[j]['high'] for j in range(i-2, i+3)]):
                highs.append((i, candles[i]['high']))
        
        for i in range(len(highs) - 2):
            h1, h2, h3 = highs[i], highs[i+1], highs[i+2]
            tolerance = 0.01  # 1%
            
            if (abs(h1[1] - h2[1]) / h1[1] < tolerance and
                abs(h2[1] - h3[1]) / h2[1] < tolerance):
                # Три примерно равных максимума
                mid_lows = [candles[j]['low'] for j in range(h1[0], h3[0])]
                if mid_lows:
                    neckline = min(mid_lows)
                    target = neckline - (h1[1] - neckline)
                    
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.TRIPLE_TOP,
                        symbol=symbol,
                        confidence=80,
                        price_level=neckline,
                        target_price=target,
                        invalidation_price=h1[1] * 1.01,
                        timestamp=int(time.time() * 1000)
                    ))
        
        return patterns
    
    def _detect_continuation_patterns(self, symbol: str, candles: List[Dict]) -> List[DetectedPattern]:
        """Обнаружить паттерны продолжения (флаги, вымпелы)"""
        patterns = []
        
        if len(candles) < 15:
            return patterns
        
        # Флаг: короткая консолидация после импульса
        # Ищем сильный импульс, затем консолидацию
        for i in range(10, len(candles) - 5):
            # Проверяем импульс
            impulse_start = candles[i-5]
            impulse_end = candles[i]
            impulse_pct = abs(impulse_end['close'] - impulse_start['close']) / impulse_start['close']
            
            if impulse_pct > 0.05:  # Импульс >5%
                # Проверяем консолидацию (флаг)
                consolidation = candles[i:i+5]
                min_low = min([c['low'] for c in consolidation])
                consolidation_range = (max([c['high'] for c in consolidation]) - 
                                      min_low) / min_low if min_low > 0 else 1.0
                
                if consolidation_range < 0.02:  # Узкий диапазон <2%
                    # Флаг обнаружен
                    patterns.append(DetectedPattern(
                        pattern_type=PatternType.FLAG,
                        symbol=symbol,
                        confidence=65,
                        price_level=(consolidation[0]['high'] + consolidation[0]['low']) / 2,
                        timestamp=int(time.time() * 1000)
                    ))
        
        return patterns

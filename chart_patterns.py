"""
MEXC Pump Monitor - Chart Pattern Detection
Детекция классических графических фигур
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChartPattern(Enum):
    """Классические графические фигуры"""
    # Разворотные
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    INVERSE_HEAD_SHOULDERS = "INVERSE_HEAD_SHOULDERS"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIPLE_TOP = "TRIPLE_TOP"
    TRIPLE_BOTTOM = "TRIPLE_BOTTOM"
    
    # Продолжение
    ASCENDING_TRIANGLE = "ASCENDING_TRIANGLE"
    DESCENDING_TRIANGLE = "DESCENDING_TRIANGLE"
    SYMMETRICAL_TRIANGLE = "SYMMETRICAL_TRIANGLE"
    FLAG = "FLAG"
    PENNANT = "PENNANT"
    RECTANGLE = "RECTANGLE"
    
    # Разворотные (продолжение)
    CUP_HANDLE = "CUP_HANDLE"
    ROUNDED_TOP = "ROUNDED_TOP"
    ROUNDED_BOTTOM = "ROUNDED_BOTTOM"
    WEDGE_ASCENDING = "WEDGE_ASCENDING"
    WEDGE_DESCENDING = "WEDGE_DESCENDING"
    DIAMOND = "DIAMOND"
    MEGAPHONE = "MEGAPHONE"


@dataclass
class DetectedChartPattern:
    """Обнаруженная графическая фигура"""
    pattern: ChartPattern
    symbol: str
    timestamp: int
    confidence: int  # 0-100
    is_bullish: bool  # True для бычьих, False для медвежьих
    target_price: Optional[float] = None
    stop_price: Optional[float] = None
    neckline: Optional[float] = None
    notes: str = ""


class ChartPatternDetector:
    """
    Детектор классических графических фигур
    """
    
    def __init__(self):
        self.patterns_history: Dict[str, List[DetectedChartPattern]] = {}
        self.max_history = 50
    
    def analyze_chart(self, candles: List[dict], symbol: str) -> List[DetectedChartPattern]:
        """
        Проанализировать график на классические фигуры
        
        Args:
            candles: Список свечей
            symbol: Торговая пара
        
        Returns:
            Список обнаруженных фигур
        """
        if len(candles) < 20:
            return []
        
        patterns = []
        
        # 1. Двойная вершина
        double_top = self._detect_double_top(candles)
        if double_top:
            patterns.append(double_top)
        
        # 2. Двойное дно
        double_bottom = self._detect_double_bottom(candles)
        if double_bottom:
            patterns.append(double_bottom)
        
        # 3. Голова и плечи
        hns = self._detect_head_shoulders(candles)
        if hns:
            patterns.append(hns)
        
        # 4. Треугольники
        triangles = self._detect_triangles(candles)
        patterns.extend(triangles)
        
        # 5. Флаги и вымпелы
        flags = self._detect_flags_pennants(candles)
        patterns.extend(flags)
        
        # Сохранить в историю
        if symbol not in self.patterns_history:
            self.patterns_history[symbol] = []
        
        self.patterns_history[symbol].extend(patterns)
        if len(self.patterns_history[symbol]) > self.max_history:
            self.patterns_history[symbol] = self.patterns_history[symbol][-self.max_history:]
        
        return patterns
    
    def _detect_double_top(self, candles: List[dict]) -> Optional[DetectedChartPattern]:
        """Обнаружить двойную вершину"""
        if len(candles) < 20:
            return None
        
        # Найти локальные максимумы
        highs = []
        for i in range(3, len(candles) - 3):
            if candles[i]['high'] == max(c['high'] for c in candles[i-3:i+4]):
                highs.append((i, candles[i]['high']))
        
        if len(highs) < 2:
            return None
        
        # Проверить последние два максимума
        h1_idx, h1_price = highs[-2]
        h2_idx, h2_price = highs[-1]
        
        # Разница должна быть небольшой (< 2%)
        price_diff = abs(h1_price - h2_price) / max(h1_price, h2_price) * 100
        if price_diff > 2:
            return None
        
        # Найти минимум между вершинами (линия шеи)
        neckline = min(c['low'] for c in candles[h1_idx:h2_idx+1])
        
        # Объем должен падать на второй вершине
        vol1 = candles[h1_idx]['volume']
        vol2 = candles[h2_idx]['volume']
        volume_decline = (vol1 - vol2) / vol1 * 100 if vol1 > 0 else 0
        
        confidence = 70
        if volume_decline > 20:
            confidence = 85
        
        # Цель = расстояние от вершин до линии шеи
        target = neckline - (h1_price - neckline)
        
        return DetectedChartPattern(
            pattern=ChartPattern.DOUBLE_TOP,
            symbol="",
            timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
            confidence=confidence,
            is_bullish=False,
            target_price=target,
            stop_price=h1_price * 1.02,  # Выше вершин
            neckline=neckline,
            notes=f"Volume decline: {volume_decline:.1f}%"
        )
    
    def _detect_double_bottom(self, candles: List[dict]) -> Optional[DetectedChartPattern]:
        """Обнаружить двойное дно"""
        if len(candles) < 20:
            return None
        
        # Найти локальные минимумы
        lows = []
        for i in range(3, len(candles) - 3):
            if candles[i]['low'] == min(c['low'] for c in candles[i-3:i+4]):
                lows.append((i, candles[i]['low']))
        
        if len(lows) < 2:
            return None
        
        l1_idx, l1_price = lows[-2]
        l2_idx, l2_price = lows[-1]
        
        price_diff = abs(l1_price - l2_price) / max(l1_price, l2_price) * 100
        if price_diff > 2:
            return None
        
        # Линия шеи (максимум между днами)
        neckline = max(c['high'] for c in candles[l1_idx:l2_idx+1])
        
        # Объем должен расти на втором дне
        vol1 = candles[l1_idx]['volume']
        vol2 = candles[l2_idx]['volume']
        volume_increase = (vol2 - vol1) / vol1 * 100 if vol1 > 0 else 0
        
        confidence = 70
        if volume_increase > 20:
            confidence = 85
        
        target = neckline + (neckline - l1_price)
        
        return DetectedChartPattern(
            pattern=ChartPattern.DOUBLE_BOTTOM,
            symbol="",
            timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
            confidence=confidence,
            is_bullish=True,
            target_price=target,
            stop_price=l1_price * 0.98,  # Ниже дна
            neckline=neckline,
            notes=f"Volume increase: {volume_increase:.1f}%"
        )
    
    def _detect_head_shoulders(self, candles: List[dict]) -> Optional[DetectedChartPattern]:
        """Обнаружить голову и плечи"""
        if len(candles) < 30:
            return None
        
        # Найти 3 максимума
        highs = []
        for i in range(5, len(candles) - 5):
            if candles[i]['high'] == max(c['high'] for c in candles[i-5:i+6]):
                highs.append((i, candles[i]['high']))
        
        if len(highs) < 3:
            return None
        
        # Последние 3 максимума
        left_shoulder = highs[-3]
        head = highs[-2]
        right_shoulder = highs[-1]
        
        # Голова должна быть выше плеч
        if not (head[1] > left_shoulder[1] and head[1] > right_shoulder[1]):
            return None
        
        # Плечи должны быть примерно на одном уровне
        shoulders_diff = abs(left_shoulder[1] - right_shoulder[1]) / max(left_shoulder[1], right_shoulder[1]) * 100
        if shoulders_diff > 3:
            return None
        
        # Линия шеи (минимумы между плечами)
        neckline1 = min(c['low'] for c in candles[left_shoulder[0]:head[0]+1])
        neckline2 = min(c['low'] for c in candles[head[0]:right_shoulder[0]+1])
        neckline = (neckline1 + neckline2) / 2
        
        # Объем должен падать
        vol_ls = candles[left_shoulder[0]]['volume']
        vol_h = candles[head[0]]['volume']
        vol_rs = candles[right_shoulder[0]]['volume']
        
        confidence = 75
        if vol_rs < vol_h < vol_ls:
            confidence = 90
        
        target = neckline - (head[1] - neckline)
        
        return DetectedChartPattern(
            pattern=ChartPattern.HEAD_SHOULDERS,
            symbol="",
            timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
            confidence=confidence,
            is_bullish=False,
            target_price=target,
            stop_price=head[1] * 1.02,
            neckline=neckline,
            notes="Head & Shoulders - разворот вниз"
        )
    
    def _detect_triangles(self, candles: List[dict]) -> List[DetectedChartPattern]:
        """Обнаружить треугольники"""
        patterns = []
        
        if len(candles) < 15:
            return patterns
        
        # Найти максимумы и минимумы
        highs = [c['high'] for c in candles[-15:]]
        lows = [c['low'] for c in candles[-15:]]
        
        # Восходящий треугольник (плоское сопротивление, растущие минимумы)
        resistance = max(highs)
        resistance_flat = max(highs) - min(highs[:8]) < max(highs) * 0.02  # Сопротивление плоское
        
        first_lows = lows[:5]
        last_lows = lows[-5:]
        ascending_lows = min(last_lows) > min(first_lows)  # Минимумы растут
        
        if resistance_flat and ascending_lows:
            patterns.append(DetectedChartPattern(
                pattern=ChartPattern.ASCENDING_TRIANGLE,
                symbol="",
                timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
                confidence=75,
                is_bullish=True,
                target_price=resistance * 1.1,  # Пробой вверх
                stop_price=min(lows) * 0.98,
                notes="Восходящий треугольник - пробой вверх"
            ))
        
        # Нисходящий треугольник (плоская поддержка, падающие максимумы)
        support = min(lows)
        support_flat = max(lows) - min(lows) < max(lows) * 0.02
        
        first_highs = highs[:5]
        last_highs = highs[-5:]
        descending_highs = max(last_highs) < max(first_highs)
        
        if support_flat and descending_highs:
            patterns.append(DetectedChartPattern(
                pattern=ChartPattern.DESCENDING_TRIANGLE,
                symbol="",
                timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
                confidence=75,
                is_bullish=False,
                target_price=support * 0.9,  # Пробой вниз
                stop_price=max(highs) * 1.02,
                notes="Нисходящий треугольник - пробой вниз"
            ))
        
        return patterns
    
    def _detect_flags_pennants(self, candles: List[dict]) -> List[DetectedChartPattern]:
        """Обнаружить флаги и вымпелы"""
        patterns = []
        
        if len(candles) < 10:
            return patterns
        
        recent = candles[-10:]
        
        # Флаг - короткая консолидация против тренда
        # Проверяем волатильность
        highs = [c['high'] for c in recent]
        lows = [c['low'] for c in recent]
        range_pct = (max(highs) - min(lows)) / min(lows) * 100
        
        if range_pct < 3:  # Низкая волатильность (консолидация)
            # Определяем направление предыдущего движения
            if len(candles) >= 20:
                prev_high = max(c['high'] for c in candles[-20:-10])
                prev_low = min(c['low'] for c in candles[-20:-10])
                
                if prev_high > max(highs):  # Предыдущее движение вверх
                    patterns.append(DetectedChartPattern(
                        pattern=ChartPattern.FLAG,
                        symbol="",
                        timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
                        confidence=70,
                        is_bullish=True,
                        target_price=max(highs) * 1.05,
                        notes="Бычий флаг - продолжение вверх"
                    ))
                elif prev_low < min(lows):  # Предыдущее движение вниз
                    patterns.append(DetectedChartPattern(
                        pattern=ChartPattern.FLAG,
                        symbol="",
                        timestamp=candles[-1].get('timestamp', int(time.time() * 1000)),
                        confidence=70,
                        is_bullish=False,
                        target_price=min(lows) * 0.95,
                        notes="Медвежий флаг - продолжение вниз"
                    ))
        
        return patterns
    
    def get_recent_patterns(self, symbol: str, limit: int = 5) -> List[DetectedChartPattern]:
        """Получить последние паттерны"""
        return self.patterns_history.get(symbol, [])[-limit:]

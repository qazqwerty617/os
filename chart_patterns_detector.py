"""
MEXC Pump Monitor - Chart Patterns Detector
Детекция классических графических фигур
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class ChartPattern(Enum):
    """Классические графические паттерны"""
    # Разворотные
    HEAD_SHOULDERS = "HEAD_SHOULDERS"
    INVERSE_HEAD_SHOULDERS = "INVERSE_HEAD_SHOULDERS"
    DOUBLE_TOP = "DOUBLE_TOP"
    DOUBLE_BOTTOM = "DOUBLE_BOTTOM"
    TRIPLE_TOP = "TRIPLE_TOP"
    TRIPLE_BOTTOM = "TRIPLE_BOTTOM"
    ROUNDED_TOP = "ROUNDED_TOP"
    ROUNDED_BOTTOM = "ROUNDED_BOTTOM"
    
    # Продолжения
    FLAG = "FLAG"
    PENNANT = "PENNANT"
    RECTANGLE = "RECTANGLE"
    TRIANGLE_ASCENDING = "TRIANGLE_ASCENDING"
    TRIANGLE_DESCENDING = "TRIANGLE_DESCENDING"
    TRIANGLE_SYMMETRIC = "TRIANGLE_SYMMETRIC"
    WEDGE_ASCENDING = "WEDGE_ASCENDING"
    WEDGE_DESCENDING = "WEDGE_DESCENDING"
    DIAMOND = "DIAMOND"
    MEGAPHONE = "MEGAPHONE"


@dataclass
class DetectedChartPattern:
    """Обнаруженный графический паттерн"""
    pattern_type: ChartPattern
    confidence: int  # 0-100
    neckline: Optional[float] = None  # Линия шеи (для H&S, двойной вершины)
    target_price: Optional[float] = None  # Целевая цена
    invalidation_price: Optional[float] = None  # Цена инвалидации
    description: str = ""


class ChartPatternsDetector:
    """
    Детектор классических графических паттернов
    """
    
    def __init__(self):
        self.patterns: Dict[str, List[DetectedChartPattern]] = {}
        self.tolerance = 0.02  # 2% толерантность для уровней
    
    def detect_patterns(self, symbol: str, prices: List[float], highs: List[float], lows: List[float]) -> List[DetectedChartPattern]:
        """
        Обнаружить графические паттерны
        
        Args:
            symbol: Торговая пара
            prices: Список цен
            highs: Список максимумов
            lows: Список минимумов
        """
        if len(prices) < 20:
            return []
        
        patterns = []
        
        # Детекторы
        detectors = [
            self._detect_double_top,
            self._detect_double_bottom,
            self._detect_head_shoulders,
            self._detect_triple_top,
            self._detect_triangle,
            self._detect_flag,
        ]
        
        for detector in detectors:
            pattern = detector(prices, highs, lows)
            if pattern:
                patterns.append(pattern)
        
        if patterns:
            self.patterns[symbol] = patterns
        
        return patterns
    
    def _detect_double_top(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить двойную вершину"""
        if len(highs) < 2:
            return None
        
        # Найти два максимума
        h1 = max(highs[-10:-5]) if len(highs) >= 10 else highs[-2]
        h2 = max(highs[-5:]) if len(highs) >= 5 else highs[-1]
        
        # Проверить что они близки (±2%)
        if abs(h1 - h2) / max(h1, h2) > self.tolerance:
            return None
        
        # Найти минимум между ними (шея)
        between_prices = [p for p in prices if min(h1, h2) * 0.95 < p < max(h1, h2) * 1.05]
        if not between_prices:
            return None
        
        neckline = min(between_prices)
        
        # Целевая цена = шея - (максимум - шея)
        target = neckline - (max(h1, h2) - neckline)
        
        # Инвалидация = выше максимума
        invalidation = max(h1, h2) * 1.01
        
        return DetectedChartPattern(
            pattern_type=ChartPattern.DOUBLE_TOP,
            confidence=75,
            neckline=neckline,
            target_price=target,
            invalidation_price=invalidation,
            description=f"Двойная вершина: максимумы ${h1:.8f} и ${h2:.8f}, шея ${neckline:.8f}"
        )
    
    def _detect_double_bottom(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить двойное дно"""
        if len(lows) < 2:
            return None
        
        l1 = min(lows[-10:-5]) if len(lows) >= 10 else lows[-2]
        l2 = min(lows[-5:]) if len(lows) >= 5 else lows[-1]
        
        if abs(l1 - l2) / max(l1, l2) > self.tolerance:
            return None
        
        between_prices = [p for p in prices if min(l1, l2) * 0.95 < p < max(l1, l2) * 1.05]
        if not between_prices:
            return None
        
        neckline = max(between_prices)
        target = neckline + (neckline - min(l1, l2))
        invalidation = min(l1, l2) * 0.99
        
        return DetectedChartPattern(
            pattern_type=ChartPattern.DOUBLE_BOTTOM,
            confidence=75,
            neckline=neckline,
            target_price=target,
            invalidation_price=invalidation,
            description=f"Двойное дно: минимумы ${l1:.8f} и ${l2:.8f}, шея ${neckline:.8f}"
        )
    
    def _detect_head_shoulders(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить голову и плечи"""
        if len(highs) < 3:
            return None
        
        # Найти три максимума
        recent_highs = sorted(highs[-15:], reverse=True)[:3]
        if len(recent_highs) < 3:
            return None
        
        # Проверить структуру: левое плечо < голова > правое плечо
        left_shoulder = recent_highs[1]  # Второй по высоте
        head = recent_highs[0]  # Самый высокий
        right_shoulder = recent_highs[2]  # Третий по высоте
        
        if not (left_shoulder < head and right_shoulder < head):
            return None
        
        # Проверить что плечи примерно на одном уровне
        if abs(left_shoulder - right_shoulder) / max(left_shoulder, right_shoulder) > self.tolerance * 2:
            return None
        
        # Найти шею (минимум между плечами)
        neckline = min(lows[-15:])
        target = neckline - (head - neckline)
        invalidation = head * 1.01
        
        return DetectedChartPattern(
            pattern_type=ChartPattern.HEAD_SHOULDERS,
            confidence=80,
            neckline=neckline,
            target_price=target,
            invalidation_price=invalidation,
            description=f"Голова и плечи: голова ${head:.8f}, шея ${neckline:.8f}"
        )
    
    def _detect_triple_top(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить тройную вершину"""
        if len(highs) < 3:
            return None
        
        # Найти три максимума примерно на одном уровне
        recent_highs = sorted(highs[-20:], reverse=True)[:3]
        if len(recent_highs) < 3:
            return None
        
        # Проверить что все три близки
        avg_high = sum(recent_highs) / len(recent_highs)
        if any(abs(h - avg_high) / avg_high > self.tolerance for h in recent_highs):
            return None
        
        neckline = min(lows[-20:])
        target = neckline - (avg_high - neckline)
        invalidation = max(recent_highs) * 1.01
        
        return DetectedChartPattern(
            pattern_type=ChartPattern.TRIPLE_TOP,
            confidence=85,
            neckline=neckline,
            target_price=target,
            invalidation_price=invalidation,
            description=f"Тройная вершина: максимумы ~${avg_high:.8f}, шея ${neckline:.8f}"
        )
    
    def _detect_triangle(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить треугольник"""
        if len(highs) < 5 or len(lows) < 5:
            return None
        
        recent_highs = highs[-10:]
        recent_lows = lows[-10:]
        
        # Восходящий треугольник: плоское сопротивление, растущие минимумы
        if len(recent_highs) >= 3 and len(recent_lows) >= 3:
            avg_high = sum(recent_highs[-3:]) / 3
            high_variance = max(recent_highs[-3:]) - min(recent_highs[-3:])
            high_variance_pct = high_variance / avg_high * 100
            
            if high_variance_pct < 1.0:  # Плоское сопротивление
                if recent_lows[-1] > recent_lows[-3]:  # Растущие минимумы
                    return DetectedChartPattern(
                        pattern_type=ChartPattern.TRIANGLE_ASCENDING,
                        confidence=70,
                        target_price=avg_high * 1.05,  # Пробой вверх
                        invalidation_price=min(recent_lows[-3:]) * 0.98,
                        description=f"Восходящий треугольник: сопротивление ${avg_high:.8f}"
                    )
        
        # Нисходящий треугольник: плоская поддержка, падающие максимумы
        if len(recent_highs) >= 3 and len(recent_lows) >= 3:
            avg_low = sum(recent_lows[-3:]) / 3
            low_variance = max(recent_lows[-3:]) - min(recent_lows[-3:])
            low_variance_pct = low_variance / avg_low * 100
            
            if low_variance_pct < 1.0:  # Плоская поддержка
                if recent_highs[-1] < recent_highs[-3]:  # Падающие максимумы
                    return DetectedChartPattern(
                        pattern_type=ChartPattern.TRIANGLE_DESCENDING,
                        confidence=70,
                        target_price=avg_low * 0.95,  # Пробой вниз
                        invalidation_price=max(recent_highs[-3:]) * 1.02,
                        description=f"Нисходящий треугольник: поддержка ${avg_low:.8f}"
                    )
        
        return None
    
    def _detect_flag(
        self,
        prices: List[float],
        highs: List[float],
        lows: List[float]
    ) -> Optional[DetectedChartPattern]:
        """Обнаружить флаг"""
        if len(prices) < 10:
            return None
        
        # Флаг: короткая консолидация после импульса
        first_half = prices[:len(prices)//2]
        second_half = prices[len(prices)//2:]
        
        # Проверить импульс в первой половине
        first_change = (first_half[-1] - first_half[0]) / first_half[0] * 100
        if abs(first_change) < 5:  # Нет импульса
            return None
        
        # Проверить консолидацию во второй половине
        second_range = (max(second_half) - min(second_half)) / min(second_half) * 100
        if second_range > 3:  # Слишком большая волатильность
            return None
        
        # Цель = размер древка (импульса)
        pole_size = abs(first_change)
        direction = 1 if first_change > 0 else -1
        target = prices[-1] * (1 + direction * pole_size / 100)
        
        return DetectedChartPattern(
            pattern_type=ChartPattern.FLAG,
            confidence=65,
            target_price=target,
            invalidation_price=prices[-1] * (1 - direction * 0.02),
            description=f"Флаг: импульс {first_change:.1f}%, цель ${target:.8f}"
        )

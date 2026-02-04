"""
MEXC Pump Monitor - Candle Pattern Detection
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
    HAMMER = "HAMMER"  # Молот
    HANGING_MAN = "HANGING_MAN"  # Повешенный
    INVERTED_HAMMER = "INVERTED_HAMMER"  # Перевернутый молот
    SHOOTING_STAR = "SHOOTING_STAR"  # Падающая звезда
    DOJI = "DOJI"  # Доджи
    PIN_BAR = "PIN_BAR"  # Пин-бар
    
    # Поглощения
    BULLISH_ENGULFING = "BULLISH_ENGULFING"
    BEARISH_ENGULFING = "BEARISH_ENGULFING"
    
    # Звезды
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    
    # Продолжение
    MARUBOZU = "MARUBOZU"
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"


@dataclass
class DetectedPattern:
    """Обнаруженный паттерн"""
    pattern: CandlePattern
    symbol: str
    timestamp: int
    confidence: int  # 0-100
    price: float
    is_bullish: bool  # True для бычьих, False для медвежьих
    target_price: Optional[float] = None
    stop_price: Optional[float] = None


class CandlePatternDetector:
    """
    Детектор свечных паттернов
    """
    
    def __init__(self):
        self.patterns_history: Dict[str, List[DetectedPattern]] = {}
        self.max_history = 50
    
    def analyze_candles(self, candles: List[dict], symbol: str) -> List[DetectedPattern]:
        """
        Проанализировать свечи на паттерны
        
        Args:
            candles: Список свечей [{'open', 'high', 'low', 'close', 'volume'}]
            symbol: Торговая пара
        
        Returns:
            Список обнаруженных паттернов
        """
        if len(candles) < 3:
            return []
        
        patterns = []
        
        # Анализируем последние 5 свечей
        for i in range(max(2, len(candles) - 5), len(candles)):
            # Одиночные паттерны
            single = self._detect_single_candle_pattern(candles[i], i, candles)
            if single:
                patterns.append(single)
            
            # Двойные паттерны
            if i >= 1:
                double = self._detect_double_candle_pattern(candles[i-1], candles[i], i, candles)
                if double:
                    patterns.append(double)
            
            # Тройные паттерны
            if i >= 2:
                triple = self._detect_triple_candle_pattern(candles[i-2], candles[i-1], candles[i], i, candles)
                if triple:
                    patterns.append(triple)
        
        # Сохранить в историю
        if symbol not in self.patterns_history:
            self.patterns_history[symbol] = []
        
        self.patterns_history[symbol].extend(patterns)
        if len(self.patterns_history[symbol]) > self.max_history:
            self.patterns_history[symbol] = self.patterns_history[symbol][-self.max_history:]
        
        return patterns
    
    def _detect_single_candle_pattern(self, candle: dict, index: int, all_candles: List[dict]) -> Optional[DetectedPattern]:
        """Обнаружить одиночные свечные паттерны"""
        open_p = candle['open']
        high = candle['high']
        low = candle['low']
        close = candle['close']
        
        body = abs(close - open_p)
        upper_shadow = high - max(open_p, close)
        lower_shadow = min(open_p, close) - low
        total_range = high - low
        
        if total_range == 0:
            return None
        
        # Доджи
        if body / total_range < 0.1:
            return DetectedPattern(
                pattern=CandlePattern.DOJI,
                symbol="",
                timestamp=candle.get('timestamp', int(time.time() * 1000)),
                confidence=70,
                price=close,
                is_bullish=None  # Нейтральный
            )
        
        # Молот (длинная нижняя тень, маленькое тело)
        if lower_shadow > body * 2 and upper_shadow < body * 0.5:
            return DetectedPattern(
                pattern=CandlePattern.HAMMER,
                symbol="",
                timestamp=candle.get('timestamp', int(time.time() * 1000)),
                confidence=75,
                price=close,
                is_bullish=True,
                stop_price=low,
                target_price=close + (close - low) * 2
            )
        
        # Повешенный (как молот, но на хаях)
        if lower_shadow > body * 2 and upper_shadow < body * 0.5:
            # Проверяем контекст - если цена на хаях
            if index >= 5:
                recent_highs = [c['high'] for c in all_candles[index-5:index]]
                if close >= max(recent_highs) * 0.95:
                    return DetectedPattern(
                        pattern=CandlePattern.HANGING_MAN,
                        symbol="",
                        timestamp=candle.get('timestamp', int(time.time() * 1000)),
                        confidence=70,
                        price=close,
                        is_bullish=False,
                        stop_price=high,
                        target_price=close - (close - low) * 2
                    )
        
        # Пин-бар (очень длинная тень в одну сторону)
        if upper_shadow > body * 3 and lower_shadow < body * 0.3:
            # Медвежий пин-бар
            return DetectedPattern(
                pattern=CandlePattern.PIN_BAR,
                symbol="",
                timestamp=candle.get('timestamp', int(time.time() * 1000)),
                confidence=80,
                price=close,
                is_bullish=False,
                stop_price=high,
                target_price=close - (high - close) * 2
            )
        elif lower_shadow > body * 3 and upper_shadow < body * 0.3:
            # Бычий пин-бар
            return DetectedPattern(
                pattern=CandlePattern.PIN_BAR,
                symbol="",
                timestamp=candle.get('timestamp', int(time.time() * 1000)),
                confidence=80,
                price=close,
                is_bullish=True,
                stop_price=low,
                target_price=close + (close - low) * 2
            )
        
        # Marubozu (без теней)
        if upper_shadow < total_range * 0.05 and lower_shadow < total_range * 0.05:
            return DetectedPattern(
                pattern=CandlePattern.MARUBOZU,
                symbol="",
                timestamp=candle.get('timestamp', int(time.time() * 1000)),
                confidence=85,
                price=close,
                is_bullish=close > open_p,
                stop_price=low if close > open_p else high,
                target_price=close + (close - open_p) * 2 if close > open_p else close - (open_p - close) * 2
            )
        
        return None
    
    def _detect_double_candle_pattern(self, prev: dict, curr: dict, index: int, all_candles: List[dict]) -> Optional[DetectedPattern]:
        """Обнаружить двойные свечные паттерны"""
        # Бычье поглощение
        if (prev['close'] < prev['open'] and  # Предыдущая медвежья
            curr['close'] > curr['open'] and  # Текущая бычья
            curr['open'] < prev['close'] and  # Открытие ниже закрытия предыдущей
            curr['close'] > prev['open']):  # Закрытие выше открытия предыдущей
            
            return DetectedPattern(
                pattern=CandlePattern.BULLISH_ENGULFING,
                symbol="",
                timestamp=curr.get('timestamp', int(time.time() * 1000)),
                confidence=80,
                price=curr['close'],
                is_bullish=True,
                stop_price=prev['low'],
                target_price=curr['close'] + (curr['close'] - prev['low']) * 1.5
            )
        
        # Медвежье поглощение
        if (prev['close'] > prev['open'] and  # Предыдущая бычья
            curr['close'] < curr['open'] and  # Текущая медвежья
            curr['open'] > prev['close'] and  # Открытие выше закрытия предыдущей
            curr['close'] < prev['open']):  # Закрытие ниже открытия предыдущей
            
            return DetectedPattern(
                pattern=CandlePattern.BEARISH_ENGULFING,
                symbol="",
                timestamp=curr.get('timestamp', int(time.time() * 1000)),
                confidence=80,
                price=curr['close'],
                is_bullish=False,
                stop_price=prev['high'],
                target_price=curr['close'] - (prev['high'] - curr['close']) * 1.5
            )
        
        # Inside Bar
        if (curr['high'] < prev['high'] and curr['low'] > prev['low']):
            return DetectedPattern(
                pattern=CandlePattern.INSIDE_BAR,
                symbol="",
                timestamp=curr.get('timestamp', int(time.time() * 1000)),
                confidence=60,
                price=curr['close'],
                is_bullish=None
            )
        
        # Outside Bar
        if (curr['high'] > prev['high'] and curr['low'] < prev['low']):
            return DetectedPattern(
                pattern=CandlePattern.OUTSIDE_BAR,
                symbol="",
                timestamp=curr.get('timestamp', int(time.time() * 1000)),
                confidence=70,
                price=curr['close'],
                is_bullish=curr['close'] > prev['close']
            )
        
        return None
    
    def _detect_triple_candle_pattern(self, first: dict, second: dict, third: dict, index: int, all_candles: List[dict]) -> Optional[DetectedPattern]:
        """Обнаружить тройные свечные паттерны"""
        # Утренняя звезда (разворот вверх)
        if (first['close'] < first['open'] and  # Первая медвежья
            abs(second['close'] - second['open']) / (second['high'] - second['low'] + 0.0001) < 0.3 and  # Вторая маленькая
            third['close'] > third['open'] and  # Третья бычья
            third['close'] > (first['open'] + first['close']) / 2):  # Третья закрывается выше середины первой
            
            return DetectedPattern(
                pattern=CandlePattern.MORNING_STAR,
                symbol="",
                timestamp=third.get('timestamp', int(time.time() * 1000)),
                confidence=85,
                price=third['close'],
                is_bullish=True,
                stop_price=first['low'],
                target_price=third['close'] + (third['close'] - first['low']) * 1.5
            )
        
        # Вечерняя звезда (разворот вниз)
        if (first['close'] > first['open'] and  # Первая бычья
            abs(second['close'] - second['open']) / (second['high'] - second['low'] + 0.0001) < 0.3 and  # Вторая маленькая
            third['close'] < third['open'] and  # Третья медвежья
            third['close'] < (first['open'] + first['close']) / 2):  # Третья закрывается ниже середины первой
            
            return DetectedPattern(
                pattern=CandlePattern.EVENING_STAR,
                symbol="",
                timestamp=third.get('timestamp', int(time.time() * 1000)),
                confidence=85,
                price=third['close'],
                is_bullish=False,
                stop_price=first['high'],
                target_price=third['close'] - (first['high'] - third['close']) * 1.5
            )
        
        return None
    
    def get_recent_patterns(self, symbol: str, limit: int = 5) -> List[DetectedPattern]:
        """Получить последние паттерны для символа"""
        return self.patterns_history.get(symbol, [])[-limit:]

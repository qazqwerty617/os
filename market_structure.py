"""
MEXC Pump Monitor - Market Structure Analysis
Анализ структуры рынка (HH, HL, LH, LL, BOS, CHoCH, MSS)
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import deque
from enum import Enum

logger = logging.getLogger(__name__)


class StructureType(Enum):
    """Тип структуры рынка"""
    BULLISH = "BULLISH"  # HH, HL
    BEARISH = "BEARISH"  # LH, LL
    NEUTRAL = "NEUTRAL"
    REVERSAL = "REVERSAL"  # CHoCH или MSS


@dataclass
class StructurePoint:
    """Точка структуры"""
    price: float
    point_type: str  # 'HH', 'HL', 'LH', 'LL'
    timestamp: int
    strength: int  # 0-100


@dataclass
class MarketStructure:
    """Структура рынка"""
    symbol: str
    current_structure: StructureType
    last_hh: Optional[float] = None
    last_hl: Optional[float] = None
    last_lh: Optional[float] = None
    last_ll: Optional[float] = None
    bos_detected: bool = False
    choch_detected: bool = False
    mss_detected: bool = False
    timestamp: int = 0


class MarketStructureAnalyzer:
    """
    Анализатор структуры рынка
    Определяет HH, HL, LH, LL, BOS, CHoCH, MSS
    """
    
    def __init__(self):
        self.candle_history: Dict[str, deque] = {}
        self.structure_points: Dict[str, List[StructurePoint]] = {}
        self.current_structure: Dict[str, MarketStructure] = {}
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
            'volume': volume,
            'timestamp': int(time.time() * 1000)
        })
        
        # Обновить структуру
        if len(self.candle_history[symbol]) >= 10:
            self._update_structure(symbol)
    
    def _update_structure(self, symbol: str):
        """Обновить структуру рынка"""
        candles = list(self.candle_history[symbol])
        
        # Найти swing highs и swing lows
        swing_highs = []
        swing_lows = []
        
        for i in range(3, len(candles) - 3):
            # Swing High
            if (candles[i]['high'] > candles[i-1]['high'] and
                candles[i]['high'] > candles[i-2]['high'] and
                candles[i]['high'] > candles[i+1]['high'] and
                candles[i]['high'] > candles[i+2]['high']):
                swing_highs.append((i, candles[i]['high']))
            
            # Swing Low
            if (candles[i]['low'] < candles[i-1]['low'] and
                candles[i]['low'] < candles[i-2]['low'] and
                candles[i]['low'] < candles[i+1]['low'] and
                candles[i]['low'] < candles[i+2]['low']):
                swing_lows.append((i, candles[i]['low']))
        
        # Определить структуру
        structure_points = []
        
        # Анализ максимумов
        for i in range(1, len(swing_highs)):
            prev_high = swing_highs[i-1][1]
            curr_high = swing_highs[i][1]
            
            if curr_high > prev_high:
                structure_points.append(StructurePoint(
                    price=curr_high,
                    point_type='HH',
                    timestamp=swing_highs[i][0],
                    strength=80
                ))
            elif curr_high < prev_high:
                structure_points.append(StructurePoint(
                    price=curr_high,
                    point_type='LH',
                    timestamp=swing_highs[i][0],
                    strength=80
                ))
        
        # Анализ минимумов
        for i in range(1, len(swing_lows)):
            prev_low = swing_lows[i-1][1]
            curr_low = swing_lows[i][1]
            
            if curr_low > prev_low:
                structure_points.append(StructurePoint(
                    price=curr_low,
                    point_type='HL',
                    timestamp=swing_lows[i][0],
                    strength=80
                ))
            elif curr_low < prev_low:
                structure_points.append(StructurePoint(
                    price=curr_low,
                    point_type='LL',
                    timestamp=swing_lows[i][0],
                    strength=80
                ))
        
        self.structure_points[symbol] = structure_points[-10:]  # Последние 10
        
        # Определить текущую структуру
        if len(structure_points) >= 2:
            last_points = structure_points[-2:]
            
            # Бычья структура: HH и HL
            if any(p.point_type == 'HH' for p in last_points) and any(p.point_type == 'HL' for p in last_points):
                structure_type = StructureType.BULLISH
            # Медвежья структура: LH и LL
            elif any(p.point_type == 'LH' for p in last_points) and any(p.point_type == 'LL' for p in last_points):
                structure_type = StructureType.BEARISH
            # Разворот
            elif any(p.point_type in ['LH', 'LL'] for p in last_points) and len([p for p in structure_points if p.point_type in ['HH', 'HL']]) > 0:
                structure_type = StructureType.REVERSAL
            else:
                structure_type = StructureType.NEUTRAL
            
            # Определить BOS (Break of Structure)
            bos = False
            if structure_type == StructureType.BEARISH and swing_lows:
                # Пробой последнего LL
                last_ll = min([p.price for p in structure_points if p.point_type == 'LL'])
                if candles[-1]['low'] < last_ll:
                    bos = True
            
            # Определить CHoCH (Change of Character)
            choch = False
            if len(structure_points) >= 3:
                # Смена с бычьей на медвежью или наоборот
                recent_types = [p.point_type for p in structure_points[-3:]]
                if 'HH' in recent_types and 'LH' in recent_types:
                    choch = True
                elif 'LL' in recent_types and 'HL' in recent_types:
                    choch = True
            
            self.current_structure[symbol] = MarketStructure(
                symbol=symbol,
                current_structure=structure_type,
                last_hh=max([p.price for p in structure_points if p.point_type == 'HH'], default=None),
                last_hl=max([p.price for p in structure_points if p.point_type == 'HL'], default=None),
                last_lh=min([p.price for p in structure_points if p.point_type == 'LH'], default=None),
                last_ll=min([p.price for p in structure_points if p.point_type == 'LL'], default=None),
                bos_detected=bos,
                choch_detected=choch,
                mss_detected=bos and choch,
                timestamp=int(time.time() * 1000)
            )
    
    def get_structure(self, symbol: str) -> Optional[MarketStructure]:
        """Получить текущую структуру"""
        return self.current_structure.get(symbol)
    
    def is_bullish_structure(self, symbol: str) -> bool:
        """Проверить, бычья ли структура"""
        structure = self.current_structure.get(symbol)
        return structure and structure.current_structure == StructureType.BULLISH
    
    def is_bearish_structure(self, symbol: str) -> bool:
        """Проверить, медвежья ли структура"""
        structure = self.current_structure.get(symbol)
        return structure and structure.current_structure == StructureType.BEARISH

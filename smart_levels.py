"""
MEXC Pump Monitor - Smart Levels Calculator
Умная система расчета стоп-лоссов и тейк-профитов на основе графического анализа
Использует: паттерны, market structure, order blocks, FVG, liquidity zones
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
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
    TRIANGLE_ASCENDING = "TRIANGLE_ASCENDING"
    TRIANGLE_DESCENDING = "TRIANGLE_DESCENDING"
    TRIANGLE_SYMMETRIC = "TRIANGLE_SYMMETRIC"
    
    # Свечные
    PIN_BAR = "PIN_BAR"
    ENGULFING_BULLISH = "ENGULFING_BULLISH"
    ENGULFING_BEARISH = "ENGULFING_BEARISH"
    MORNING_STAR = "MORNING_STAR"
    EVENING_STAR = "EVENING_STAR"
    INSIDE_BAR = "INSIDE_BAR"
    OUTSIDE_BAR = "OUTSIDE_BAR"


class MarketStructure(Enum):
    """Структура рынка"""
    UPTREND = "UPTREND"  # HH, HL
    DOWNTREND = "DOWNTREND"  # LH, LL
    RANGE = "RANGE"
    BOS_UP = "BOS_UP"  # Break of Structure вверх
    BOS_DOWN = "BOS_DOWN"  # Break of Structure вниз
    CHoCH = "CHoCH"  # Change of Character


@dataclass
class PriceLevel:
    """Уровень цены"""
    price: float
    strength: float  # 0-100, сила уровня
    level_type: str  # 'support', 'resistance', 'order_block', 'fvg', 'liquidity'
    touched_count: int = 0
    last_touched: int = 0
    volume_at_level: float = 0


@dataclass
class OrderBlock:
    """Order Block - зона входа крупного капитала"""
    price_low: float
    price_high: float
    is_bullish: bool
    strength: float  # 0-100
    volume: float
    timestamp: int


@dataclass
class FairValueGap:
    """Fair Value Gap - ценовой дисбаланс"""
    price_low: float
    price_high: float
    filled: bool = False
    timestamp: int = 0


@dataclass
class SmartLevels:
    """Умные уровни для входа/выхода"""
    symbol: str
    
    # Entry
    entry_optimal: float
    entry_zone_low: float
    entry_zone_high: float
    
    # Stop Loss (динамический)
    stop_loss: float
    stop_loss_reason: str  # Почему именно этот уровень
    stop_loss_strength: float  # Сила уровня (0-100)
    
    # Take Profit (динамический, несколько уровней)
    take_profit_1: float
    take_profit_1_reason: str
    take_profit_1_strength: float
    
    take_profit_2: float
    take_profit_2_reason: str
    take_profit_2_strength: float
    
    take_profit_3: float
    take_profit_3_reason: str
    take_profit_3_strength: float
    
    # Risk/Reward
    risk_pct: float
    reward_1_pct: float
    reward_2_pct: float
    reward_3_pct: float
    rr_ratio_1: float
    rr_ratio_2: float
    rr_ratio_3: float
    
    # Market context
    market_structure: str
    detected_patterns: List[str] = field(default_factory=list)
    key_levels: List[PriceLevel] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fvgs: List[FairValueGap] = field(default_factory=list)
    
    # Рекомендации
    confidence: int = 0  # 0-100
    recommended_size_pct: float = 1.0
    warnings: List[str] = field(default_factory=list)


class SmartLevelsCalculator:
    """
    Умный калькулятор уровней на основе графического анализа
    """
    
    def __init__(self):
        # История для анализа
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.max_history = 500
        
        # Обнаруженные уровни
        self.support_levels: Dict[str, List[PriceLevel]] = {}
        self.resistance_levels: Dict[str, List[PriceLevel]] = {}
        self.order_blocks: Dict[str, List[OrderBlock]] = {}
        self.fvgs: Dict[str, List[FairValueGap]] = {}
        
        # Market structure
        self.market_structure: Dict[str, MarketStructure] = {}
        self.highs: Dict[str, List[float]] = {}
        self.lows: Dict[str, List[float]] = {}
        
        # Order Book Analyzer
        try:
            from orderbook_analyzer import OrderBookAnalyzer
            self.orderbook_analyzer = OrderBookAnalyzer()
        except ImportError:
            self.orderbook_analyzer = None
        
    def record_candle(
        self,
        symbol: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        timestamp: int = None
    ):
        """Записать свечу для анализа"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.max_history)
            self.volume_history[symbol] = deque(maxlen=self.max_history)
            self.highs[symbol] = []
            self.lows[symbol] = []
        
        candle = {
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            'timestamp': timestamp
        }
        
        self.price_history[symbol].append(candle)
        self.volume_history[symbol].append(volume)
        
        # Обновить структуру рынка
        self._update_market_structure(symbol, high, low, close)
        
        # Обновить уровни
        self._update_levels(symbol, high, low, close, volume)
        
        # Обнаружить паттерны
        self._detect_patterns(symbol)
        
        # Обнаружить Order Blocks
        self._detect_order_blocks(symbol)
        
        # Обнаружить FVG
        self._detect_fvg(symbol)
    
    async def calculate_smart_levels(
        self,
        symbol: str,
        current_price: float,
        side: str = 'SHORT',  # 'SHORT' or 'LONG'
        pump_size_pct: float = 0,
        client = None
    ) -> Optional[SmartLevels]:
        """
        Рассчитать умные уровни для входа/выхода
        
        Args:
            symbol: Торговая пара
            current_price: Текущая цена
            side: Направление сделки
            pump_size_pct: Размер пампы в %
        
        Returns:
            SmartLevels с динамическими уровнями
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 20:
            return None
        
        history = list(self.price_history[symbol])
        recent = history[-50:]  # Последние 50 свечей
        
        # 1. Определить структуру рынка
        market_structure = self._get_market_structure(symbol, recent)
        
        # 2. Найти ключевые уровни (включая order book)
        key_levels = self._find_key_levels(symbol, current_price, side)
        
        # 2.1. Добавить уровни из order book (если доступен) - ПРИОРИТЕТНЫЕ
        orderbook_clusters = []
        if self.orderbook_analyzer and client:
            try:
                orderbook = await self.orderbook_analyzer.get_orderbook(symbol, client)
                if orderbook:
                    clusters = self.orderbook_analyzer.find_liquidity_clusters(orderbook, current_price)
                    # Преобразовать кластеры в PriceLevel с высоким приоритетом
                    for cluster in clusters[:5]:  # Топ 5 кластеров
                        level = PriceLevel(
                            price=(cluster.price_low + cluster.price_high) / 2,
                            strength=min(100, cluster.strength + 20),  # Бонус за order book
                            level_type='support' if cluster.is_support else 'resistance',
                            volume_at_level=cluster.total_liquidity
                        )
                        key_levels.append(level)
                        orderbook_clusters.append(cluster)
                    # Пересортировать
                    key_levels.sort(key=lambda x: x.strength, reverse=True)
            except Exception as e:
                logger.debug(f"Orderbook analysis failed for {symbol}: {e}")
        
        # 3. Найти Order Blocks
        relevant_ob = self._get_relevant_order_blocks(symbol, current_price, side)
        
        # 4. Найти FVG
        relevant_fvg = self._get_relevant_fvgs(symbol, current_price, side)
        
        # 5. Рассчитать Entry
        entry_optimal, entry_zone = self._calculate_entry(
            current_price, key_levels, relevant_ob, side
        )
        
        # 6. Рассчитать Stop Loss (на основе уровней, паттернов, структуры)
        stop_loss, stop_reason, stop_strength = self._calculate_stop_loss(
            entry_optimal, key_levels, relevant_ob, market_structure, side, symbol
        )
        
        # 7. Рассчитать Take Profits (на основе уровней, структуры, паттернов)
        tp1, tp1_reason, tp1_strength = self._calculate_take_profit_1(
            entry_optimal, key_levels, market_structure, side, symbol
        )
        tp2, tp2_reason, tp2_strength = self._calculate_take_profit_2(
            entry_optimal, key_levels, market_structure, side, tp1, symbol
        )
        tp3, tp3_reason, tp3_strength = self._calculate_take_profit_3(
            entry_optimal, key_levels, market_structure, side, tp2, symbol
        )
        
        # 8. Рассчитать Risk/Reward
        risk_pct = abs((stop_loss - entry_optimal) / entry_optimal * 100)
        reward_1_pct = abs((entry_optimal - tp1) / entry_optimal * 100) if side == 'SHORT' else abs((tp1 - entry_optimal) / entry_optimal * 100)
        reward_2_pct = abs((entry_optimal - tp2) / entry_optimal * 100) if side == 'SHORT' else abs((tp2 - entry_optimal) / entry_optimal * 100)
        reward_3_pct = abs((entry_optimal - tp3) / entry_optimal * 100) if side == 'SHORT' else abs((tp3 - entry_optimal) / entry_optimal * 100)
        
        rr_1 = reward_1_pct / risk_pct if risk_pct > 0 else 0
        rr_2 = reward_2_pct / risk_pct if risk_pct > 0 else 0
        rr_3 = reward_3_pct / risk_pct if risk_pct > 0 else 0
        
        # 9. Обнаружить паттерны
        detected_patterns = self._get_detected_patterns(symbol)
        
        # 10. Рассчитать уверенность
        confidence = self._calculate_confidence(
            key_levels, relevant_ob, market_structure, detected_patterns, stop_strength
        )
        
        # 11. Рекомендации по размеру
        recommended_size = self._calculate_recommended_size(confidence, rr_1, stop_strength)
        
        # 12. Предупреждения
        warnings = self._generate_warnings(
            risk_pct, rr_1, stop_strength, key_levels, market_structure
        )
        
        return SmartLevels(
            symbol=symbol,
            entry_optimal=entry_optimal,
            entry_zone_low=entry_zone[0],
            entry_zone_high=entry_zone[1],
            stop_loss=stop_loss,
            stop_loss_reason=stop_reason,
            stop_loss_strength=stop_strength,
            take_profit_1=tp1,
            take_profit_1_reason=tp1_reason,
            take_profit_1_strength=tp1_strength,
            take_profit_2=tp2,
            take_profit_2_reason=tp2_reason,
            take_profit_2_strength=tp2_strength,
            take_profit_3=tp3,
            take_profit_3_reason=tp3_reason,
            take_profit_3_strength=tp3_strength,
            risk_pct=risk_pct,
            reward_1_pct=reward_1_pct,
            reward_2_pct=reward_2_pct,
            reward_3_pct=reward_3_pct,
            rr_ratio_1=rr_1,
            rr_ratio_2=rr_2,
            rr_ratio_3=rr_3,
            market_structure=market_structure.value if isinstance(market_structure, MarketStructure) else str(market_structure),
            detected_patterns=detected_patterns,
            key_levels=key_levels,
            order_blocks=relevant_ob,
            fvgs=relevant_fvg,
            confidence=confidence,
            recommended_size_pct=recommended_size,
            warnings=warnings
        )
    
    def _update_market_structure(self, symbol: str, high: float, low: float, close: float):
        """Обновить структуру рынка (HH, HL, LH, LL)"""
        if len(self.highs[symbol]) == 0:
            self.highs[symbol].append(high)
            self.lows[symbol].append(low)
            return
        
        # Определить локальные экстремумы
        if len(self.price_history[symbol]) >= 3:
            candles = list(self.price_history[symbol])
            prev_high = candles[-2]['high']
            prev_low = candles[-2]['low']
            
            # Локальный максимум
            if high > prev_high and high > candles[-3]['high']:
                self.highs[symbol].append(high)
                if len(self.highs[symbol]) > 20:
                    self.highs[symbol] = self.highs[symbol][-20:]
            
            # Локальный минимум
            if low < prev_low and low < candles[-3]['low']:
                self.lows[symbol].append(low)
                if len(self.lows[symbol]) > 20:
                    self.lows[symbol] = self.lows[symbol][-20:]
    
    def _get_market_structure(self, symbol: str, recent: List) -> MarketStructure:
        """Определить структуру рынка"""
        if len(self.highs[symbol]) < 2 or len(self.lows[symbol]) < 2:
            return MarketStructure.RANGE
        
        highs = self.highs[symbol][-3:]
        lows = self.lows[symbol][-3:]
        
        # Uptrend: HH и HL
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
                return MarketStructure.UPTREND
        
        # Downtrend: LH и LL
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
                return MarketStructure.DOWNTREND
        
        # BOS (Break of Structure)
        if len(highs) >= 2:
            if highs[-1] > max(highs[:-1]):
                return MarketStructure.BOS_UP
            if lows[-1] < min(lows[:-1]):
                return MarketStructure.BOS_DOWN
        
        return MarketStructure.RANGE
    
    def _update_levels(self, symbol: str, high: float, low: float, close: float, volume: float):
        """Обновить уровни поддержки/сопротивления"""
        tolerance = 0.002  # 0.2% толерантность
        
        # Обновить поддержки
        if symbol not in self.support_levels:
            self.support_levels[symbol] = []
        
        # Найти ближайшую поддержку
        for support in self.support_levels[symbol]:
            if abs(low - support.price) / support.price < tolerance:
                support.touched_count += 1
                support.last_touched = int(time.time() * 1000)
                support.volume_at_level += volume
                support.strength = min(100, support.strength + 5)
                return
        
        # Новая поддержка
        if len(self.support_levels[symbol]) < 10:
            self.support_levels[symbol].append(PriceLevel(
                price=low,
                strength=30,
                level_type='support',
                touched_count=1,
                last_touched=int(time.time() * 1000),
                volume_at_level=volume
            ))
        
        # Обновить сопротивления
        if symbol not in self.resistance_levels:
            self.resistance_levels[symbol] = []
        
        for resistance in self.resistance_levels[symbol]:
            if abs(high - resistance.price) / resistance.price < tolerance:
                resistance.touched_count += 1
                resistance.last_touched = int(time.time() * 1000)
                resistance.volume_at_level += volume
                resistance.strength = min(100, resistance.strength + 5)
                return
        
        if len(self.resistance_levels[symbol]) < 10:
            self.resistance_levels[symbol].append(PriceLevel(
                price=high,
                strength=30,
                level_type='resistance',
                touched_count=1,
                last_touched=int(time.time() * 1000),
                volume_at_level=volume
            ))
    
    def _find_key_levels(
        self,
        symbol: str,
        current_price: float,
        side: str
    ) -> List[PriceLevel]:
        """Найти ключевые уровни для сделки"""
        key_levels = []
        
        # Для SHORT: ищем сопротивления выше
        if side == 'SHORT':
            for resistance in self.resistance_levels.get(symbol, []):
                if resistance.price > current_price:
                    # Рассчитать силу уровня
                    distance_pct = (resistance.price - current_price) / current_price * 100
                    if distance_pct < 10:  # Только близкие уровни
                        key_levels.append(resistance)
            
            # Добавить поддержки ниже (для TP)
            for support in self.support_levels.get(symbol, []):
                if support.price < current_price:
                    key_levels.append(support)
        else:  # LONG
            for support in self.support_levels.get(symbol, []):
                if support.price < current_price:
                    distance_pct = (current_price - support.price) / current_price * 100
                    if distance_pct < 10:
                        key_levels.append(support)
            
            for resistance in self.resistance_levels.get(symbol, []):
                if resistance.price > current_price:
                    key_levels.append(resistance)
        
        # Сортировать по силе
        key_levels.sort(key=lambda x: x.strength, reverse=True)
        return key_levels[:5]  # Топ 5 уровней
    
    def _detect_order_blocks(self, symbol: str):
        """Обнаружить Order Blocks"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 10:
            return
        
        history = list(self.price_history[symbol])
        
        if symbol not in self.order_blocks:
            self.order_blocks[symbol] = []
        
        # Ищем последнюю бычью/медвежью свечу перед импульсом
        for i in range(len(history) - 5, max(0, len(history) - 50), -1):
            if i < 3:
                continue
            
            candle = history[i]
            next_candle = history[i + 1]
            
            # Бычий Order Block: бычья свеча перед ростом
            if candle['close'] > candle['open']:
                if next_candle['close'] > candle['close'] * 1.02:  # Импульс вверх
                    ob = OrderBlock(
                        price_low=candle['low'],
                        price_high=candle['high'],
                        is_bullish=True,
                        strength=min(100, candle['volume'] / 1000000 * 50),  # Упрощенная формула
                        volume=candle['volume'],
                        timestamp=candle['timestamp']
                    )
                    # Проверить, нет ли уже такого OB
                    if not any(abs(ob.price_low - existing.price_low) / existing.price_low < 0.01 
                              for existing in self.order_blocks[symbol]):
                        self.order_blocks[symbol].append(ob)
            
            # Медвежий Order Block: медвежья свеча перед падением
            elif candle['close'] < candle['open']:
                if next_candle['close'] < candle['close'] * 0.98:  # Импульс вниз
                    ob = OrderBlock(
                        price_low=candle['low'],
                        price_high=candle['high'],
                        is_bullish=False,
                        strength=min(100, candle['volume'] / 1000000 * 50),
                        volume=candle['volume'],
                        timestamp=candle['timestamp']
                    )
                    if not any(abs(ob.price_low - existing.price_low) / existing.price_low < 0.01 
                              for existing in self.order_blocks[symbol]):
                        self.order_blocks[symbol].append(ob)
        
        # Ограничить количество
        if len(self.order_blocks[symbol]) > 20:
            self.order_blocks[symbol] = self.order_blocks[symbol][-20:]
    
    def _detect_fvg(self, symbol: str):
        """Обнаружить Fair Value Gaps"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 3:
            return
        
        history = list(self.price_history[symbol])
        
        if symbol not in self.fvgs:
            self.fvgs[symbol] = []
        
        # FVG: разрыв между свечами
        for i in range(len(history) - 2):
            candle1 = history[i]
            candle2 = history[i + 1]
            candle3 = history[i + 2]
            
            # Бычий FVG: нижняя тень свечи 2 выше максимума свечи 1
            if candle2['low'] > candle1['high']:
                fvg = FairValueGap(
                    price_low=candle1['high'],
                    price_high=candle2['low'],
                    filled=False,
                    timestamp=candle2['timestamp']
                )
                # Проверить, заполнен ли
                if candle3['low'] <= fvg.price_high:
                    fvg.filled = True
                
                if not any(abs(fvg.price_low - existing.price_low) / existing.price_low < 0.01 
                          for existing in self.fvgs[symbol]):
                    self.fvgs[symbol].append(fvg)
            
            # Медвежий FVG: верхняя тень свечи 2 ниже минимума свечи 1
            elif candle2['high'] < candle1['low']:
                fvg = FairValueGap(
                    price_low=candle2['high'],
                    price_high=candle1['low'],
                    filled=False,
                    timestamp=candle2['timestamp']
                )
                if candle3['high'] >= fvg.price_low:
                    fvg.filled = True
                
                if not any(abs(fvg.price_low - existing.price_low) / existing.price_low < 0.01 
                          for existing in self.fvgs[symbol]):
                    self.fvgs[symbol].append(fvg)
        
        # Ограничить количество
        if len(self.fvgs[symbol]) > 15:
            self.fvgs[symbol] = self.fvgs[symbol][-15:]
    
    def _get_relevant_order_blocks(
        self,
        symbol: str,
        current_price: float,
        side: str
    ) -> List[OrderBlock]:
        """Получить релевантные Order Blocks"""
        if symbol not in self.order_blocks:
            return []
        
        relevant = []
        for ob in self.order_blocks[symbol]:
            if side == 'SHORT':
                # Для шорта ищем медвежьи OB выше цены
                if not ob.is_bullish and ob.price_low > current_price:
                    distance = (ob.price_low - current_price) / current_price * 100
                    if distance < 5:  # В пределах 5%
                        relevant.append(ob)
            else:  # LONG
                # Для лонга ищем бычьи OB ниже цены
                if ob.is_bullish and ob.price_high < current_price:
                    distance = (current_price - ob.price_high) / current_price * 100
                    if distance < 5:
                        relevant.append(ob)
        
        return sorted(relevant, key=lambda x: x.strength, reverse=True)[:3]
    
    def _get_relevant_fvgs(
        self,
        symbol: str,
        current_price: float,
        side: str
    ) -> List[FairValueGap]:
        """Получить релевантные FVG"""
        if symbol not in self.fvgs:
            return []
        
        relevant = []
        for fvg in self.fvgs[symbol]:
            if not fvg.filled:
                if fvg.price_low <= current_price <= fvg.price_high:
                    relevant.append(fvg)
        
        return relevant[:3]
    
    def _calculate_entry(
        self,
        current_price: float,
        key_levels: List[PriceLevel],
        order_blocks: List[OrderBlock],
        side: str
    ) -> Tuple[float, Tuple[float, float]]:
        """Рассчитать оптимальный вход"""
        # Приоритет: Order Block > Ключевой уровень > Текущая цена
        
        if order_blocks:
            # Использовать Order Block
            ob = order_blocks[0]
            if side == 'SHORT':
                entry = ob.price_high  # Вход на верхней границе OB
            else:
                entry = ob.price_low  # Вход на нижней границе OB
        elif key_levels:
            # Использовать ближайший уровень
            level = key_levels[0]
            entry = level.price
        else:
            entry = current_price
        
        # Entry zone: ±0.5% от оптимального входа
        zone_low = entry * 0.995
        zone_high = entry * 1.005
        
        return entry, (zone_low, zone_high)
    
    def _calculate_stop_loss(
        self,
        entry: float,
        key_levels: List[PriceLevel],
        order_blocks: List[OrderBlock],
        market_structure: MarketStructure,
        side: str,
        symbol: str = ""
    ) -> Tuple[float, str, float]:
        """Рассчитать Stop Loss на основе уровней"""
        # Приоритет: Графический паттерн > Order Block > Сопротивление/Поддержка > Структура
        
        if side == 'SHORT':
            # Для шорта стоп выше входа
            candidates = []
            
            # 0. Графические паттерны (самый высокий приоритет)
            if hasattr(self, 'detected_chart_patterns'):
                chart_patterns = self.detected_chart_patterns.get(symbol, [])
                for pattern in chart_patterns:
                    if pattern.invalidation_price and pattern.invalidation_price > entry:
                        candidates.append((
                            pattern.invalidation_price,
                            f"{pattern.pattern_type.value} инвалидация",
                            pattern.confidence
                        ))
            
            # 1. Order Block выше
            for ob in order_blocks:
                if ob.price_high > entry:
                    candidates.append((ob.price_high * 1.002, f"Order Block выше ({ob.strength:.0f})", ob.strength))
            
            # 2. Сопротивление выше (приоритет order book кластерам)
            for level in key_levels:
                if level.level_type == 'resistance' and level.price > entry:
                    distance = (level.price - entry) / entry * 100
                    if 3 < distance < 15:  # Расширено для мемкоинов (было 2-8%)
                        # Бонус за order book уровень
                        reason = f"Сопротивление ({level.strength:.0f})"
                        if level.volume_at_level > 0:
                            reason = f"Order Book кластер ({level.strength:.0f})"
                        candidates.append((level.price * 1.001, reason, level.strength))
            
            # 3. Структура (HH для шорта)
            if market_structure == MarketStructure.UPTREND:
                symbol_highs = self.highs.get(symbol, [])
                if symbol_highs:
                    recent_high = max(symbol_highs[-3:])
                    if recent_high > entry:
                        candidates.append((recent_high * 1.001, "Higher High (структура)", 70))
            
            # Выбрать лучший (ближайший сильный уровень)
            if candidates:
                candidates.sort(key=lambda x: (x[0] - entry) / entry)  # По расстоянию
                best = candidates[0]
                return best[0], best[1], best[2]
            
            # Fallback: 5% выше входа (для волатильных мемкоинов)
            return entry * 1.05, "Фиксированный 5%", 50
        
        else:  # LONG
            candidates = []
            
            # 0. Графические паттерны
            if hasattr(self, 'detected_chart_patterns'):
                chart_patterns = self.detected_chart_patterns.get(symbol, [])
                for pattern in chart_patterns:
                    if pattern.invalidation_price and pattern.invalidation_price < entry:
                        candidates.append((
                            pattern.invalidation_price,
                            f"{pattern.pattern_type.value} инвалидация",
                            pattern.confidence
                        ))
            
            # 1. Order Block ниже
            for ob in order_blocks:
                if ob.price_low < entry:
                    candidates.append((ob.price_low * 0.998, f"Order Block ниже ({ob.strength:.0f})", ob.strength))
            
            # 2. Поддержка ниже
            for level in key_levels:
                if level.level_type == 'support' and level.price < entry:
                    distance = (entry - level.price) / entry * 100
                    if 3 < distance < 15:  # Расширено для мемкоинов
                        candidates.append((level.price * 0.999, f"Поддержка ({level.strength:.0f})", level.strength))
            
            # 3. Структура (LL для лонга)
            if market_structure == MarketStructure.DOWNTREND:
                symbol_lows = self.lows.get(symbol, [])
                if symbol_lows:
                    recent_low = min(symbol_lows[-3:])
                    if recent_low < entry:
                        candidates.append((recent_low * 0.999, "Lower Low (структура)", 70))
            
            if candidates:
                candidates.sort(key=lambda x: (entry - x[0]) / entry)  # По расстоянию
                best = candidates[0]
                return best[0], best[1], best[2]
            
            return entry * 0.95, "Фиксированный 5%", 50
    
    def _calculate_take_profit_1(
        self,
        entry: float,
        key_levels: List[PriceLevel],
        market_structure: MarketStructure,
        side: str,
        symbol: str = ""
    ) -> Tuple[float, str, float]:
        """Рассчитать первый Take Profit"""
        if side == 'SHORT':
            # 0. Графические паттерны (приоритет)
            if hasattr(self, 'detected_chart_patterns'):
                chart_patterns = self.detected_chart_patterns.get(symbol, [])
                for pattern in chart_patterns:
                    if pattern.target_price and pattern.target_price < entry:
                        distance = (entry - pattern.target_price) / entry * 100
                        if 2 < distance < 20:
                            return pattern.target_price, f"{pattern.pattern_type.value} цель", pattern.confidence
            
            # 1. Ищем поддержку ниже (приоритет order book)
            for level in key_levels:
                if level.level_type == 'support' and level.price < entry:
                    distance = (entry - level.price) / entry * 100
                    if 2 < distance < 15:  # Разумное расстояние
                        reason = f"Поддержка ({level.strength:.0f})"
                        if level.volume_at_level > 0:
                            reason = f"Order Book кластер ({level.strength:.0f})"
                        return level.price * 0.999, reason, level.strength
            
            # Fallback: 1.5x от риска
            return entry * 0.985, "1.5R от риска", 60
        
        else:  # LONG
            for level in key_levels:
                if level.level_type == 'resistance' and level.price > entry:
                    distance = (level.price - entry) / entry * 100
                    if 2 < distance < 15:
                        return level.price * 1.001, f"Сопротивление ({level.strength:.0f})", level.strength
            
            return entry * 1.015, "1.5R от риска", 60
    
    def _calculate_take_profit_2(
        self,
        entry: float,
        key_levels: List[PriceLevel],
        market_structure: MarketStructure,
        side: str,
        tp1: float,
        symbol: str = ""
    ) -> Tuple[float, str, float]:
        """Рассчитать второй Take Profit"""
        if side == 'SHORT':
            # Ищем следующую поддержку ниже TP1
            for level in key_levels:
                if level.level_type == 'support' and level.price < tp1:
                    return level.price * 0.999, f"Следующая поддержка ({level.strength:.0f})", level.strength
            
            # Fallback: 2.5x от риска
            return entry * 0.975, "2.5R от риска", 50
        
        else:
            for level in key_levels:
                if level.level_type == 'resistance' and level.price > tp1:
                    return level.price * 1.001, f"Следующее сопротивление ({level.strength:.0f})", level.strength
            
            return entry * 1.025, "2.5R от риска", 50
    
    def _calculate_take_profit_3(
        self,
        entry: float,
        key_levels: List[PriceLevel],
        market_structure: MarketStructure,
        side: str,
        tp2: float,
        symbol: str = ""
    ) -> Tuple[float, str, float]:
        """Рассчитать третий Take Profit"""
        if side == 'SHORT':
            # Ищем следующую поддержку ниже TP2
            for level in key_levels:
                if level.level_type == 'support' and level.price < tp2:
                    return level.price * 0.999, f"Сильная поддержка ({level.strength:.0f})", level.strength
            
            # Fallback: 4x от риска
            return entry * 0.96, "4R от риска", 40
        
        else:
            for level in key_levels:
                if level.level_type == 'resistance' and level.price > tp2:
                    return level.price * 1.001, f"Сильное сопротивление ({level.strength:.0f})", level.strength
            
            return entry * 1.04, "4R от риска", 40
    
    def _detect_patterns(self, symbol: str):
        """Обнаружить графические паттерны"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 3:
            return
        
        # 1. Свечные паттерны
        from candlestick_patterns import CandlestickPatternDetector
        
        candle_detector = CandlestickPatternDetector()
        candles = [
            {
                'open': c['open'],
                'high': c['high'],
                'low': c['low'],
                'close': c['close'],
                'volume': c.get('volume', 0)
            }
            for c in list(self.price_history[symbol])[-20:]
        ]
        candle_patterns = candle_detector.detect_patterns(candles)
        
        # 2. Графические паттерны
        try:
            from chart_patterns_detector import ChartPatternsDetector
            
            chart_detector = ChartPatternsDetector()
            prices = [c['close'] for c in list(self.price_history[symbol])]
            highs = self.highs.get(symbol, [])
            lows = self.lows.get(symbol, [])
            chart_patterns = chart_detector.detect_patterns(symbol, prices, highs, lows)
        except ImportError:
            chart_patterns = []
        
        # Сохранить все паттерны
        if not hasattr(self, 'detected_patterns'):
            self.detected_patterns = {}
        if not hasattr(self, 'detected_chart_patterns'):
            self.detected_chart_patterns = {}
        
        self.detected_patterns[symbol] = candle_patterns
        self.detected_chart_patterns[symbol] = chart_patterns
    
    def _get_detected_patterns(self, symbol: str) -> List[str]:
        """Получить обнаруженные паттерны"""
        patterns = []
        
        # Свечные паттерны
        if hasattr(self, 'detected_patterns'):
            candle_patterns = self.detected_patterns.get(symbol, [])
            patterns.extend([p.pattern_type.value for p in candle_patterns if p.confidence >= 70])
        
        # Графические паттерны
        if hasattr(self, 'detected_chart_patterns'):
            chart_patterns = self.detected_chart_patterns.get(symbol, [])
            patterns.extend([p.pattern_type.value for p in chart_patterns if p.confidence >= 70])
        
        return patterns
    
    def _calculate_confidence(
        self,
        key_levels: List[PriceLevel],
        order_blocks: List[OrderBlock],
        market_structure: MarketStructure,
        patterns: List[str],
        stop_strength: float
    ) -> int:
        """Рассчитать уверенность в сделке"""
        confidence = 50  # Базовая
        
        # Бонусы
        if key_levels:
            confidence += min(20, sum(level.strength for level in key_levels[:3]) / 10)
        
        if order_blocks:
            confidence += min(15, sum(ob.strength for ob in order_blocks) / 10)
        
        if market_structure in [MarketStructure.BOS_DOWN, MarketStructure.DOWNTREND]:
            confidence += 10
        
        if patterns:
            confidence += min(10, len(patterns) * 2)
        
        confidence += stop_strength / 2
        
        return min(100, int(confidence))
    
    def _calculate_recommended_size(
        self,
        confidence: int,
        rr_ratio: float,
        stop_strength: float
    ) -> float:
        """Рассчитать рекомендуемый размер позиции"""
        base_size = 1.0  # 1% базовый
        
        # Модификаторы
        if confidence >= 90:
            base_size *= 1.5
        elif confidence >= 80:
            base_size *= 1.2
        elif confidence < 70:
            base_size *= 0.7
        
        if rr_ratio >= 3:
            base_size *= 1.3
        elif rr_ratio >= 2:
            base_size *= 1.1
        
        if stop_strength >= 80:
            base_size *= 1.2
        
        return min(3.0, max(0.25, base_size))  # От 0.25% до 3%
    
    def _generate_warnings(
        self,
        risk_pct: float,
        rr_ratio: float,
        stop_strength: float,
        key_levels: List[PriceLevel],
        market_structure: MarketStructure
    ) -> List[str]:
        """Сгенерировать предупреждения"""
        warnings = []
        
        if risk_pct > 5:
            warnings.append(f"Высокий риск: {risk_pct:.1f}%")
        
        if rr_ratio < 1.5:
            warnings.append(f"Низкий R:R: 1:{rr_ratio:.1f}")
        
        if stop_strength < 60:
            warnings.append("Слабый уровень стоп-лосса")
        
        if not key_levels:
            warnings.append("Недостаточно ключевых уровней")
        
        if market_structure == MarketStructure.UPTREND:
            warnings.append("Внимание: восходящий тренд (для шорта)")
        
        return warnings

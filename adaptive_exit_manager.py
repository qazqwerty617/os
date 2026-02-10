"""
Adaptive Exit Manager - Интеллектуальная система управления стопами и тейками
Использует: ATR, Footprint анализ, Market Structure, Liquidity Zones, Volume Delta
"""

import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AssetClass(Enum):
    """Класс актива по волатильности"""
    BLUE_CHIP = "blue_chip"      # BTC, ETH - низкая волатильность
    MID_CAP = "mid_cap"          # SOL, AVAX, LINK - средняя
    MEMECOIN = "memecoin"        # PEPE, WIF, BONK - высокая
    SHITCOIN = "shitcoin"        # Топ 100-500 на CoinMarketCap
    MICRO_CAP = "micro_cap"      # Говно-койны 500к-5млн капа - экстремальная волатильность
    NANOCAP = "nanocap"          # Совсем новые листинги <500к - максимальный риск


class ExitPhase(Enum):
    """Фаза выхода из позиции"""
    EARLY = "early"              # Первые 30 сек - высокий риск
    ESTABLISHED = "established" # 30 сек - 3 мин - стандартная фаза  
    MATURE = "mature"           # 3-10 мин - удержание
    LATE = "late"               # >10 мин - агрессивные стопы


class StopType(Enum):
    """Тип стоп-лосса"""
    TECHNICAL = "technical"      # На основе уровней
    ATR_BASED = "atr"           # На основе ATR
    STRUCTURE = "structure"     # Break of Structure
    TIME_BASED = "time"         # Временной стоп
    VOLATILITY = "volatility"   # Адаптивный к волатильности


@dataclass
class ExitLevel:
    """Уровень выхода"""
    price: float
    size_pct: float             # % позиции для закрытия
    trigger_reason: str
    confidence: float           # 0-100
    is_trailing: bool = False
    trailing_distance_pct: float = 0


@dataclass
class AdaptiveExitPlan:
    """Адаптивный план выхода"""
    symbol: str
    side: str                   # 'LONG' или 'SHORT'
    entry_price: float
    entry_time: datetime
    
    # Уровни (обязательные)
    stop_loss: ExitLevel
    take_profits: List[ExitLevel]
    
    # Адаптивные параметры (обязательные)
    asset_class: AssetClass
    current_phase: ExitPhase
    atr_14: float
    volatility_1m: float        # 1-минутная волатильность
    volatility_5m: float        # 5-минутная волатильность
    
    # Аналитика (обязательные)
    volume_profile_poc: float   # Point of Control
    delta_structure: str        # 'bullish', 'bearish', 'neutral'
    
    # Опциональные поля с default
    trailing_levels: List[ExitLevel] = field(default_factory=list)
    liquidation_clusters: List[float] = field(default_factory=list)
    structure_points: List['MarketStructurePoint'] = field(default_factory=list)
    
    # Динамические обновления
    last_update: datetime = field(default_factory=datetime.now)
    revision_count: int = 0
    
    # Статистика
    current_pnl_pct: float = 0
    max_pnl_pct: float = 0      # Для trailing
    drawdown_from_max: float = 0


@dataclass
class FootprintData:
    """Footprint анализ (дельта объема)"""
    bid_volume: float
    ask_volume: float
    delta: float                # bid - ask
    delta_pct: float            # delta / total
    imbalance_ratio: float      # bid/ask или ask/bid
    aggressive_buyers: bool
    aggressive_sellers: bool
    absorption_detected: bool    # Крупный объем без движения цены


@dataclass
class MarketStructurePoint:
    """Точка структуры рынка"""
    price: float
    type: str                   # 'BSL', 'SSL', 'BOS', 'CHoCH', 'EQH', 'EQL'
    strength: float             # 0-100
    liquidity_sweep: bool       # Подтвержденный sweep
    mitigation_zone: Tuple[float, float]  # Зона для стопа


class AdaptiveExitManager:
    """
    Интеллектуальный менеджер выходов из позиций
    
    Особенности:
    - Индивидуальный расчет для каждой монеты
    - Footprint анализ (дельта объема)
    - Динамический ATR-based стоп
    - 3 фазы trailing stop
    - Частичное закрытие с наращиванием (pyramiding)
    - Учет liquidation clusters
    - Временные стопы для мемкоинов
    """
    
    # Классификация активов
    BLUE_CHIPS = {'BTC', 'ETH'}
    MID_CAPS = {'SOL', 'AVAX', 'LINK', 'DOT', 'UNI', 'AAVE', 'SNX', 'CRV', 
                'SUSHI', '1INCH', 'DYDX', 'APE', 'GMT', 'IMX', 'RNDR'}
    
    # Параметры по классам активов - настроены под говно-койны
    ASSET_PARAMS = {
        AssetClass.BLUE_CHIP: {
            'atr_multiplier': 2.0,
            'base_stop_pct': 0.8,
            'tp1_pct': 1.5,
            'tp2_pct': 3.0,
            'tp3_pct': 5.0,
            'trailing_start_pct': 2.0,
            'trailing_step_pct': 0.3,
            'max_hold_minutes': 60,
            'revision_interval_sec': 60
        },
        AssetClass.MID_CAP: {
            'atr_multiplier': 2.5,
            'base_stop_pct': 1.5,
            'tp1_pct': 3.0,
            'tp2_pct': 6.0,
            'tp3_pct': 10.0,
            'trailing_start_pct': 4.0,
            'trailing_step_pct': 0.5,
            'max_hold_minutes': 30,
            'revision_interval_sec': 30
        },
        AssetClass.MEMECOIN: {
            'atr_multiplier': 3.5,
            'base_stop_pct': 3.0,
            'tp1_pct': 6.0,
            'tp2_pct': 12.0,
            'tp3_pct': 20.0,
            'trailing_start_pct': 8.0,
            'trailing_step_pct': 1.0,
            'max_hold_minutes': 15,
            'revision_interval_sec': 15
        },
        AssetClass.SHITCOIN: {
            'atr_multiplier': 5.0,
            'base_stop_pct': 5.0,
            'tp1_pct': 10.0,
            'tp2_pct': 20.0,
            'tp3_pct': 35.0,
            'trailing_start_pct': 15.0,
            'trailing_step_pct': 2.0,
            'max_hold_minutes': 10,
            'revision_interval_sec': 10
        },
        AssetClass.MICRO_CAP: {
            'atr_multiplier': 8.0,        # Огромный ATR для волатильности
            'base_stop_pct': 8.0,         # 8% стоп минимум
            'tp1_pct': 15.0,              # 15% первый тейк
            'tp2_pct': 30.0,              # 30% второй
            'tp3_pct': 50.0,              # 50% третий - ловим памп
            'trailing_start_pct': 25.0,   # Трейлинг после 25% профита
            'trailing_step_pct': 3.0,     # Шаг 3%
            'max_hold_minutes': 5,        # Макс 5 минут удержания!
            'revision_interval_sec': 5,   # Обновление каждые 5 сек
            'rug_pull_detection': True,   # Включаем детекцию rug pull
            'rapid_exit_threshold': 10,   # Быстрый выход при 10% против нас
            'partial_tp1': 50,            # 50% на первом тейке (быстрее фиксируем)
            'partial_tp2': 30,            # 30% на втором
            'partial_tp3': 20,          # 20% на третьем
        },
        AssetClass.NANOCAP: {
            'atr_multiplier': 12.0,       # Максимальный ATR
            'base_stop_pct': 12.0,        # 12% стоп
            'tp1_pct': 20.0,              # 20% первый тейк
            'tp2_pct': 40.0,              # 40% второй
            'tp3_pct': 80.0,              # 80% третий - если взлетит
            'trailing_start_pct': 35.0,   # Трейлинг после 35%
            'trailing_step_pct': 5.0,     # Шаг 5%
            'max_hold_minutes': 3,        # Макс 3 минуты!
            'revision_interval_sec': 3,   # Обновление каждые 3 сек
            'rug_pull_detection': True,
            'rapid_exit_threshold': 8,    # Выход при 8% против
            'partial_tp1': 60,            # 60% сразу забираем
            'partial_tp2': 25,            # 25% на втором
            'partial_tp3': 15,            # 15% остаток
            'panic_exit_enabled': True,   # Паник выход при резком развороте
        }
    }
    
    def __init__(self):
        self.active_plans: Dict[str, AdaptiveExitPlan] = {}
        self.price_history: Dict[str, List[Tuple[float, float]]] = {}  # (price, volume)
        self.footprint_data: Dict[str, FootprintData] = {}
        self.structure_points: Dict[str, List[MarketStructurePoint]] = {}
        
    def classify_asset(self, symbol: str, volatility_24h: float = 0, 
                       market_cap: float = 0, volume_24h: float = 0) -> AssetClass:
        """Классифицировать актив по волатильности и параметрам"""
        base = symbol.replace('USDT', '').replace('_', '')
        
        # Если есть market_cap - используем его
        if market_cap > 0:
            if market_cap < 500000:  # <500k
                return AssetClass.NANOCAP
            elif market_cap < 5000000:  # 500k - 5M
                return AssetClass.MICRO_CAP
            elif market_cap < 50000000:  # 5M - 50M
                return AssetClass.SHITCOIN
            elif market_cap < 1000000000:  # 50M - 1B
                return AssetClass.MEMECOIN
            else:
                return AssetClass.MID_CAP if base not in self.BLUE_CHIPS else AssetClass.BLUE_CHIP
        
        # По волатильности 24h
        if volatility_24h > 300:
            return AssetClass.NANOCAP
        elif volatility_24h > 150:
            return AssetClass.MICRO_CAP
        elif volatility_24h > 80:
            return AssetClass.SHITCOIN
        
        # По известным символам
        if base in self.BLUE_CHIPS:
            return AssetClass.BLUE_CHIP
        elif base in self.MID_CAPS:
            return AssetClass.MID_CAP
        
        # По объему (если есть)
        if volume_24h > 0:
            if volume_24h < 100000:  # <100k за 24h
                return AssetClass.NANOCAP
            elif volume_24h < 1000000:  # <1M
                return AssetClass.MICRO_CAP
            elif volume_24h < 10000000:  # <10M
                return AssetClass.SHITCOIN
        
        # По длине символа (часто новые говно-койны имеют длинные названия)
        if len(base) > 6:
            return AssetClass.MICRO_CAP
        
        # Дефолт для неизвестных - считаем говно-койном
        return AssetClass.MICRO_CAP
    
    def calculate_atr(self, prices: List[float], period: int = 14) -> float:
        """Расчет Average True Range"""
        if len(prices) < period + 1:
            return prices[-1] * 0.02  # Fallback 2%
        
        tr_values = []
        for i in range(1, len(prices)):
            tr = abs(prices[i] - prices[i-1])
            tr_values.append(tr)
        
        if len(tr_values) >= period:
            atr = np.mean(tr_values[-period:])
            return atr
        
        return np.mean(tr_values) if tr_values else prices[-1] * 0.02
    
    def analyze_footprint(self, symbol: str, orderbook_data: dict, 
                         recent_trades: List[dict]) -> FootprintData:
        """Анализ дельты объема (footprint)"""
        bid_volume = 0
        ask_volume = 0
        
        for trade in recent_trades[-50:]:  # Последние 50 трейдов
            if trade.get('is_buyer_maker', False):
                bid_volume += float(trade.get('quote_qty', 0))
            else:
                ask_volume += float(trade.get('quote_qty', 0))
        
        total_volume = bid_volume + ask_volume
        delta = bid_volume - ask_volume
        delta_pct = (delta / total_volume * 100) if total_volume > 0 else 0
        
        # Определяем агрессивных участников
        aggressive_buyers = delta_pct > 20 and ask_volume > bid_volume * 1.5
        aggressive_sellers = delta_pct < -20 and bid_volume > ask_volume * 1.5
        
        # Проверка на абсорбцию
        absorption_detected = (
            total_volume > 100000 and 
            abs(delta_pct) < 5  # Большой объем, но цена не движется
        )
        
        return FootprintData(
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            delta=delta,
            delta_pct=delta_pct,
            imbalance_ratio=max(bid_volume, ask_volume) / min(bid_volume, ask_volume) if min(bid_volume, ask_volume) > 0 else 1,
            aggressive_buyers=aggressive_buyers,
            aggressive_sellers=aggressive_sellers,
            absorption_detected=absorption_detected
        )
    
    def find_liquidity_clusters(self, symbol: str, price: float, 
                                orderbook: dict) -> List[Tuple[float, float, str]]:
        """Найти кластеры ликвидности для стопов и тейков"""
        clusters = []
        
        if not orderbook:
            return clusters
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        # Ищем накопление ликвидности
        for i, (p, qty) in enumerate(bids[:20]):
            p, qty = float(p), float(qty)
            cumulative = sum(float(b[1]) for b in bids[i:i+3])
            if cumulative > 5:  # Большой объем
                distance = (price - p) / price * 100
                if 1 < distance < 15:
                    clusters.append((p, cumulative, 'bid_cluster'))
        
        for i, (p, qty) in enumerate(asks[:20]):
            p, qty = float(p), float(qty)
            cumulative = sum(float(a[1]) for a in asks[i:i+3])
            if cumulative > 5:
                distance = (p - price) / price * 100
                if 1 < distance < 15:
                    clusters.append((p, cumulative, 'ask_cluster'))
        
        return sorted(clusters, key=lambda x: x[1], reverse=True)
    
    def detect_structure_points(self, symbol: str, highs: List[float], 
                                lows: List[float], prices: List[float]) -> List[MarketStructurePoint]:
        """Обнаружить точки структуры рынка (BSL/SSL, BOS, CHoCH)"""
        points = []
        
        if len(highs) < 3 or len(lows) < 3:
            return points
        
        # Swing Highs/Lows
        swing_highs = []
        swing_lows = []
        
        for i in range(1, len(highs) - 1):
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                swing_highs.append((i, highs[i]))
        
        for i in range(1, len(lows) - 1):
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                swing_lows.append((i, lows[i]))
        
        # BOS (Break of Structure)
        if len(swing_highs) >= 2:
            if swing_highs[-1][1] > swing_highs[-2][1]:
                points.append(MarketStructurePoint(
                    price=swing_highs[-2][1],
                    type='BOS_UP',
                    strength=80,
                    liquidity_sweep=False,
                    mitigation_zone=(swing_highs[-2][1] * 0.998, swing_highs[-2][1] * 1.002)
                ))
        
        if len(swing_lows) >= 2:
            if swing_lows[-1][1] < swing_lows[-2][1]:
                points.append(MarketStructurePoint(
                    price=swing_lows[-2][1],
                    type='BOS_DOWN',
                    strength=80,
                    liquidity_sweep=False,
                    mitigation_zone=(swing_lows[-2][1] * 0.998, swing_lows[-2][1] * 1.002)
                ))
        
        # BSL/SSL (Buy/Sell Side Liquidity)
        if swing_highs:
            eq_high = max([h[1] for h in swing_highs[-3:]])
            touches = sum(1 for h in swing_highs[-5:] if abs(h[1] - eq_high) / eq_high < 0.005)
            if touches >= 2:
                points.append(MarketStructurePoint(
                    price=eq_high * 1.002,
                    type='BSL',
                    strength=90,
                    liquidity_sweep=True,
                    mitigation_zone=(eq_high * 0.998, eq_high * 1.005)
                ))
        
        if swing_lows:
            eq_low = min([l[1] for l in swing_lows[-3:]])
            touches = sum(1 for l in swing_lows[-5:] if abs(l[1] - eq_low) / eq_low < 0.005)
            if touches >= 2:
                points.append(MarketStructurePoint(
                    price=eq_low * 0.998,
                    type='SSL',
                    strength=90,
                    liquidity_sweep=True,
                    mitigation_zone=(eq_low * 0.995, eq_low * 1.002)
                ))
        
        return points
    
    def calculate_volatility(self, prices: List[float], window: int = 20) -> Tuple[float, float]:
        """Расчет волатильности (1m и 5m)"""
        if len(prices) < window:
            return 0, 0
        
        returns = [abs(prices[i] - prices[i-1]) / prices[i-1] * 100 
                   for i in range(1, len(prices))]
        
        vol_1m = np.mean(returns[-5:]) * 100 if len(returns) >= 5 else 0
        vol_5m = np.mean(returns[-20:]) * 100 if len(returns) >= 20 else 0
        
        return vol_1m, vol_5m
    
    async def create_exit_plan(self, symbol: str, side: str, entry_price: float,
                              price_history: List[float], orderbook: dict = None,
                              recent_trades: List[dict] = None,
                              pump_size_pct: float = 0,
                              smart_levels: dict = None) -> AdaptiveExitPlan:
        """
        Создать адаптивный план выхода с учетом размера пампа и уровней
        
        Args:
            symbol: Торговая пара
            side: 'LONG' или 'SHORT'
            entry_price: Цена входа
            price_history: История цен
            orderbook: Данные ордербука
            recent_trades: Недавние сделки
            pump_size_pct: Размер пампа в % (критически важно для расчета!)
            smart_levels: Умные уровни из smart_levels.py
        """
        
        # 1. Классифицируем актив с учетом пампа
        vol_1m, vol_5m = self.calculate_volatility(price_history)
        
        # Если памп большой - повышаем класс волатильности
        adjusted_vol = vol_5m + pump_size_pct * 0.5
        asset_class = self.classify_asset(symbol, volatility_24h=adjusted_vol)
        
        # Получаем базовые параметры
        params = self.ASSET_PARAMS[asset_class].copy()
        
        # === ДИНАМИЧЕСКАЯ АДАПТАЦИЯ НА ОСНОВЕ ПАМПА ===
        if pump_size_pct > 0:
            # Чем больше памп - тем шире стоп и тейки
            pump_multiplier = min(3.0, 1.0 + pump_size_pct / 50)  # 1.0 - 3.0x
            
            params['atr_multiplier'] *= pump_multiplier
            params['base_stop_pct'] *= pump_multiplier
            params['tp1_pct'] *= pump_multiplier
            params['tp2_pct'] *= pump_multiplier  
            params['tp3_pct'] *= pump_multiplier
            
            logger.info(f"📊 {symbol}: Pump {pump_size_pct:.1f}% detected, multiplier: {pump_multiplier:.2f}x")
        
        # 2. Расчет ATR
        atr = self.calculate_atr(price_history)
        atr_pct = atr / entry_price * 100
        
        # 3. Footprint анализ
        footprint = None
        if recent_trades:
            footprint = self.analyze_footprint(symbol, orderbook, recent_trades)
        
        # 4. Точки структуры
        # Извлекаем highs и lows из истории
        highs = []
        lows = []
        for i in range(1, len(price_history) - 1):
            if price_history[i] > price_history[i-1] and price_history[i] > price_history[i+1]:
                highs.append(price_history[i])
            if price_history[i] < price_history[i-1] and price_history[i] < price_history[i+1]:
                lows.append(price_history[i])
        
        structure_points = self.detect_structure_points(symbol, highs, lows, price_history)
        
        # 5. Ликвидность
        liq_clusters = []
        if orderbook:
            liq_clusters = self.find_liquidity_clusters(symbol, entry_price, orderbook)
        
        # 6. Расчет стопа
        stop_price, stop_reason, stop_confidence = self._calculate_smart_stop(
            symbol, side, entry_price, atr_pct, params, 
            structure_points, liq_clusters, footprint
        )
        
        # 7. Расчет тейков
        tps = self._calculate_smart_tps(
            symbol, side, entry_price, stop_price, params,
            structure_points, liq_clusters, price_history
        )
        
        # === ИСПОЛЬЗУЕМ SMART_LEVELS ЕСЛИ ДОСТУПНЫ ===
        if smart_levels:
            logger.info(f"🎯 {symbol}: Using smart_levels from market analysis")
            
            # Переопределяем стоп на основе smart_levels если он сильнее
            if smart_levels.get('stop_loss'):
                sl_from_smart = smart_levels['stop_loss']
                current_sl_distance = abs(stop_price - entry_price) / entry_price * 100
                smart_sl_distance = abs(sl_from_smart - entry_price) / entry_price * 100
                
                # Берем более консервативный (ближайший) стоп
                if smart_sl_distance < current_sl_distance * 1.2:  # Допуск 20%
                    stop_price = sl_from_smart
                    stop_reason = smart_levels.get('stop_loss_reason', 'SmartLevels')
                    stop_confidence = smart_levels.get('stop_loss_strength', 80)
                    logger.info(f"   Using smart SL: ${stop_price:.6f} ({stop_reason})")
            
            # Переопределяем тейки если есть
            if smart_levels.get('take_profit_1'):
                tps[0].price = smart_levels['take_profit_1']
                tps[0].trigger_reason = smart_levels.get('take_profit_1_reason', 'SmartLevels TP1')
                tps[0].confidence = smart_levels.get('take_profit_1_strength', 85)
                logger.info(f"   Using smart TP1: ${tps[0].price:.6f}")
            
            if smart_levels.get('take_profit_2') and len(tps) > 1:
                tps[1].price = smart_levels['take_profit_2']
                tps[1].trigger_reason = smart_levels.get('take_profit_2_reason', 'SmartLevels TP2')
                tps[1].confidence = smart_levels.get('take_profit_2_strength', 75)
                logger.info(f"   Using smart TP2: ${tps[1].price:.6f}")
        
        # 8. Trailing уровни
        trailings = self._calculate_trailing_levels(
            side, entry_price, params, tps
        )
        
        # 9. Определение фазы
        phase = ExitPhase.EARLY
        
        # 10. Дельта структуры
        delta_struct = 'neutral'
        if footprint:
            if footprint.delta_pct > 15:
                delta_struct = 'bullish'
            elif footprint.delta_pct < -15:
                delta_struct = 'bearish'
        
        plan = AdaptiveExitPlan(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=ExitLevel(
                price=stop_price,
                size_pct=100,
                trigger_reason=stop_reason,
                confidence=stop_confidence
            ),
            take_profits=tps,
            trailing_levels=trailings,
            asset_class=asset_class,
            current_phase=phase,
            atr_14=atr_pct,
            volatility_1m=vol_1m,
            volatility_5m=vol_5m,
            volume_profile_poc=0,
            delta_structure=delta_struct,
            liquidation_clusters=[c[0] for c in liq_clusters[:3]],
            structure_points=structure_points  # Сохраняем для динамического пересчета
        )
        
        self.active_plans[symbol] = plan
        
        logger.info(f"🎯 Adaptive plan created for {symbol} ({asset_class.value})")
        logger.info(f"   SL: ${stop_price:.6f} ({stop_reason})")
        logger.info(f"   TPs: {', '.join([f'${tp.price:.6f}' for tp in tps])}")
        
        return plan
    
    def _calculate_smart_stop(self, symbol: str, side: str, entry: float,
                              atr_pct: float, params: dict,
                              structure_points: List[MarketStructurePoint],
                              liq_clusters: List[Tuple[float, float, str]],
                              footprint: Optional[FootprintData]) -> Tuple[float, str, float]:
        """Умный расчет стопа с приоритетами"""
        
        candidates = []
        
        if side == 'SHORT':
            # 1. Структурные уровни (BOS/CHoCH выше)
            for point in structure_points:
                if point.price > entry and point.type in ['BOS_UP', 'BSL']:
                    candidates.append((
                        point.mitigation_zone[1],
                        f"Structure {point.type}",
                        point.strength
                    ))
            
            # 2. Ликвидность выше
            for price, size, cluster_type in liq_clusters:
                if price > entry and cluster_type == 'ask_cluster':
                    candidates.append((
                        price * 1.001,
                        f"Liquidity cluster ({size:.1f} USDT)",
                        min(95, size * 5)
                    ))
            
            # 3. ATR-based
            atr_stop = entry * (1 + atr_pct * params['atr_multiplier'] / 100)
            candidates.append((atr_stop, f"ATR({params['atr_multiplier']}x)", 70))
            
            # 4. Фиксированный базовый
            base_stop = entry * (1 + params['base_stop_pct'] / 100)
            candidates.append((base_stop, f"Base {params['base_stop_pct']}%", 50))
            
            # Фильтруем слишком далекие и выбираем лучший
            valid = [(p, r, c) for p, r, c in candidates 
                     if p > entry and (p - entry) / entry < 0.15]  # Макс 15%
            
            if valid:
                # Сортируем по силе, берем сильнейший в разумном диапазоне
                valid.sort(key=lambda x: x[2], reverse=True)
                # Проверяем не слишком ли далеко лучший
                best = valid[0]
                if (best[0] - entry) / entry > 0.08 and len(valid) > 1:
                    # Берем второй если лучший слишком далеко (>8%)
                    return valid[1]
                return best
            
            return base_stop, "Base fallback", 40
            
        else:  # LONG
            for point in structure_points:
                if point.price < entry and point.type in ['BOS_DOWN', 'SSL']:
                    candidates.append((
                        point.mitigation_zone[0],
                        f"Structure {point.type}",
                        point.strength
                    ))
            
            for price, size, cluster_type in liq_clusters:
                if price < entry and cluster_type == 'bid_cluster':
                    candidates.append((
                        price * 0.999,
                        f"Liquidity cluster ({size:.1f} USDT)",
                        min(95, size * 5)
                    ))
            
            atr_stop = entry * (1 - atr_pct * params['atr_multiplier'] / 100)
            candidates.append((atr_stop, f"ATR({params['atr_multiplier']}x)", 70))
            
            base_stop = entry * (1 - params['base_stop_pct'] / 100)
            candidates.append((base_stop, f"Base {params['base_stop_pct']}%", 50))
            
            valid = [(p, r, c) for p, r, c in candidates 
                     if p < entry and (entry - p) / entry < 0.15]
            
            if valid:
                valid.sort(key=lambda x: x[2], reverse=True)
                best = valid[0]
                if (entry - best[0]) / entry > 0.08 and len(valid) > 1:
                    return valid[1]
                return best
            
            return base_stop, "Base fallback", 40
    
    def _calculate_smart_tps(self, symbol: str, side: str, entry: float,
                            stop: float, params: dict,
                            structure_points: List[MarketStructurePoint],
                            liq_clusters: List[Tuple[float, float, str]],
                            price_history: List[float]) -> List[ExitLevel]:
        """Умный расчет тейк-профитов с R:R ratios"""
        
        tps = []
        risk = abs(entry - stop)
        
        if side == 'SHORT':
            # TP1 - 2R с использованием структуры или ликвидности
            tp1_candidates = []
            
            for point in structure_points:
                if point.price < entry and point.type in ['SSL', 'BOS_DOWN']:
                    tp1_candidates.append((point.price, f"Structure {point.type}", point.strength))
            
            for price, size, cluster_type in liq_clusters:
                if price < entry and cluster_type == 'bid_cluster':
                    tp1_candidates.append((price, f"Liquidity", min(90, size * 3)))
            
            # Добавляем R-based
            tp1_r = entry - risk * 2
            tp1_candidates.append((tp1_r, "2R target", 60))
            
            tp1_pct = entry * (1 - params['tp1_pct'] / 100)
            tp1_candidates.append((tp1_pct, f"{params['tp1_pct']}%", 50))
            
            # Выбираем лучший TP1
            valid_tp1 = [(p, r, c) for p, r, c in tp1_candidates 
                        if p < entry and 1 < (entry - p) / entry * 100 < 15]
            
            if valid_tp1:
                valid_tp1.sort(key=lambda x: (entry - x[0]) / entry)  # Ближайший
                tp1_price, tp1_reason, tp1_conf = valid_tp1[0]
            else:
                tp1_price, tp1_reason, tp1_conf = tp1_r, "2R fallback", 50
            
            tps.append(ExitLevel(
                price=tp1_price,
                size_pct=params.get('partial_tp1', 40),  # Из конфига или дефолт 40%
                trigger_reason=tp1_reason,
                confidence=tp1_conf
            ))
            
            # TP2 - 3.5R
            tp2_r = entry - risk * 3.5
            tp2_pct = entry * (1 - params['tp2_pct'] / 100)
            tp2_price = max(tp2_r, tp2_pct) if tp2_pct > 0 else tp2_r
            
            tps.append(ExitLevel(
                price=tp2_price,
                size_pct=params.get('partial_tp2', 35),  # Из конфига или дефолт 35%
                trigger_reason="3.5R / Structure",
                confidence=65
            ))
            
            # TP3 - 6R или ликвидность
            tp3_r = entry - risk * 6
            tp3_pct = entry * (1 - params['tp3_pct'] / 100)
            
            # Ищем SSL для TP3
            ssl_candidates = [p for p in structure_points if p.type == 'SSL' and p.price < tp2_price]
            if ssl_candidates:
                tp3_price = min([p.price for p in ssl_candidates]) * 0.998
            else:
                tp3_price = min(tp3_r, tp3_pct) if tp3_pct > 0 else tp3_r
            
            tps.append(ExitLevel(
                price=tp3_price,
                size_pct=params.get('partial_tp3', 25),  # Из конфига или дефолт 25%
                trigger_reason="6R / SSL",
                confidence=55,
                is_trailing=True,  # Включаем trailing после TP3
                trailing_distance_pct=params['trailing_step_pct']
            ))
            
        else:  # LONG
            # Аналогично для лонга
            tp1_candidates = []
            
            for point in structure_points:
                if point.price > entry and point.type in ['BSL', 'BOS_UP']:
                    tp1_candidates.append((point.price, f"Structure {point.type}", point.strength))
            
            for price, size, cluster_type in liq_clusters:
                if price > entry and cluster_type == 'ask_cluster':
                    tp1_candidates.append((price, f"Liquidity", min(90, size * 3)))
            
            tp1_r = entry + risk * 2
            tp1_candidates.append((tp1_r, "2R target", 60))
            
            tp1_pct = entry * (1 + params['tp1_pct'] / 100)
            tp1_candidates.append((tp1_pct, f"{params['tp1_pct']}%", 50))
            
            valid_tp1 = [(p, r, c) for p, r, c in tp1_candidates 
                        if p > entry and 1 < (p - entry) / entry * 100 < 15]
            
            if valid_tp1:
                valid_tp1.sort(key=lambda x: (x[0] - entry) / entry)
                tp1_price, tp1_reason, tp1_conf = valid_tp1[0]
            else:
                tp1_price, tp1_reason, tp1_conf = tp1_r, "2R fallback", 50
            
            tps.append(ExitLevel(
                price=tp1_price,
                size_pct=params.get('partial_tp1', 40),
                trigger_reason=tp1_reason,
                confidence=tp1_conf
            ))
            
            tp2_r = entry + risk * 3.5
            tp2_pct = entry * (1 + params['tp2_pct'] / 100)
            tp2_price = min(tp2_r, tp2_pct) if tp2_pct > 0 else tp2_r
            
            tps.append(ExitLevel(
                price=tp2_price,
                size_pct=params.get('partial_tp2', 35),
                trigger_reason="3.5R / Structure",
                confidence=65
            ))
            
            tp3_r = entry + risk * 6
            tp3_pct = entry * (1 + params['tp3_pct'] / 100)
            
            bsl_candidates = [p for p in structure_points if p.type == 'BSL' and p.price > tp2_price]
            if bsl_candidates:
                tp3_price = max([p.price for p in bsl_candidates]) * 1.002
            else:
                tp3_price = max(tp3_r, tp3_pct) if tp3_pct > 0 else tp3_r
            
            tps.append(ExitLevel(
                price=tp3_price,
                size_pct=params.get('partial_tp3', 25),
                trigger_reason="6R / BSL",
                confidence=55,
                is_trailing=True,
                trailing_distance_pct=params['trailing_step_pct']
            ))
        
        return tps
    
    def _calculate_trailing_levels(self, side: str, entry: float, 
                                   params: dict, tps: List[ExitLevel]) -> List[ExitLevel]:
        """Расчет уровней для trailing stop"""
        trailings = []
        
        # Phase 1: После TP1 - стоп на breakeven
        trailings.append(ExitLevel(
            price=entry,
            size_pct=0,  # Просто перемещаем стоп
            trigger_reason="Breakeven after TP1",
            confidence=90,
            is_trailing=False
        ))
        
        # Phase 2: После TP2 - trailing с шагом
        if len(tps) >= 2:
            trail_stop = tps[1].price  # За TP2
            trailings.append(ExitLevel(
                price=trail_stop,
                size_pct=0,
                trigger_reason=f"Trailing after TP2 ({params['trailing_step_pct']}%)",
                confidence=80,
                is_trailing=True,
                trailing_distance_pct=params['trailing_step_pct']
            ))
        
        return trailings
    
    async def recalculate_levels(self, symbol: str, current_price: float,
                                   new_structure_points: List[MarketStructurePoint] = None,
                                   new_liq_clusters: List[Tuple[float, float, str]] = None) -> Optional[AdaptiveExitPlan]:
        """
        Динамический пересчет уровней на основе текущей ситуации
        Вызывается при значительном изменении цены или при появлении новых уровней
        """
        plan = self.active_plans.get(symbol)
        if not plan:
            return None
        
        params = self.ASSET_PARAMS[plan.asset_class]
        
        # Обновляем структурные точки если есть новые
        if new_structure_points:
            plan.structure_points = new_structure_points
        
        # Обновляем кластеры ликвидности
        if new_liq_clusters:
            plan.liquidation_clusters = [c[0] for c in new_liq_clusters[:3]]
        
        # === ДИНАМИЧЕСКАЯ КОРРЕКТИРОВКА СТОПА ===
        # Если цена ушла далеко от входа - корректируем стоп на основе ближайших уровней
        current_pnl = abs(plan.current_pnl_pct)
        
        if current_pnl > 2:  # Если уже есть 2%+ движение
            # Ищем ближайший сильный уровень для стопа
            if plan.side == 'SHORT':
                # Для шорта ищем ближайшее сопротивление выше текущей цены
                best_stop = None
                best_distance = float('inf')
                
                for point in plan.structure_points:
                    if point.price > current_price and point.type in ['BOS_UP', 'BSL']:
                        distance = (point.price - current_price) / current_price * 100
                        if distance < best_distance and 1 < distance < 12:
                            best_distance = distance
                            best_stop = point
                
                if best_stop and best_stop.price < plan.stop_loss.price:
                    # Новый стоп ближе и лучше - обновляем
                    old_sl = plan.stop_loss.price
                    plan.stop_loss.price = best_stop.price * 1.002
                    plan.stop_loss.trigger_reason = f"Dynamic SL update ({best_stop.type})"
                    logger.info(f"🔄 {symbol}: SL adjusted ${old_sl:.6f} -> ${plan.stop_loss.price:.6f} ({best_stop.type})")
            
            else:  # LONG
                best_stop = None
                best_distance = float('inf')
                
                for point in plan.structure_points:
                    if point.price < current_price and point.type in ['BOS_DOWN', 'SSL']:
                        distance = (current_price - point.price) / current_price * 100
                        if distance < best_distance and 1 < distance < 12:
                            best_distance = distance
                            best_stop = point
                
                if best_stop and best_stop.price > plan.stop_loss.price:
                    old_sl = plan.stop_loss.price
                    plan.stop_loss.price = best_stop.price * 0.998
                    plan.stop_loss.trigger_reason = f"Dynamic SL update ({best_stop.type})"
                    logger.info(f"🔄 {symbol}: SL adjusted ${old_sl:.6f} -> ${plan.stop_loss.price:.6f} ({best_stop.type})")
        
        # === КОРРЕКТИРОВКА ТЕЙКОВ ===
        # Если есть неактивированные тейки - обновляем их на основе новых уровней
        for i, tp in enumerate(plan.take_profits):
            if hasattr(tp, '_hit') and tp._hit:
                continue  # Уже сработал - пропускаем
            
            if plan.side == 'SHORT':
                # Ищем лучшую поддержку ниже текущей цены
                best_tp = None
                best_distance = float('inf')
                
                for point in plan.structure_points:
                    if point.price < current_price and point.type in ['SSL', 'BOS_DOWN']:
                        distance = (current_price - point.price) / current_price * 100
                        # Оптимальная дистанция для тейка: 3-10%
                        if 3 < distance < 10 and distance < best_distance:
                            best_distance = distance
                            best_tp = point
                
                if best_tp and abs(best_tp.price - tp.price) / tp.price > 0.02:  # Разница > 2%
                    old_tp = tp.price
                    tp.price = best_tp.price * 0.998
                    tp.trigger_reason = f"Dynamic TP{i+1} ({best_tp.type})"
                    logger.info(f"🔄 {symbol}: TP{i+1} adjusted ${old_tp:.6f} -> ${tp.price:.6f} ({best_tp.type})")
            
            else:  # LONG
                best_tp = None
                best_distance = float('inf')
                
                for point in plan.structure_points:
                    if point.price > current_price and point.type in ['BSL', 'BOS_UP']:
                        distance = (point.price - current_price) / current_price * 100
                        if 3 < distance < 10 and distance < best_distance:
                            best_distance = distance
                            best_tp = point
                
                if best_tp and abs(best_tp.price - tp.price) / tp.price > 0.02:
                    old_tp = tp.price
                    tp.price = best_tp.price * 1.002
                    tp.trigger_reason = f"Dynamic TP{i+1} ({best_tp.type})"
                    logger.info(f"🔄 {symbol}: TP{i+1} adjusted ${old_tp:.6f} -> ${tp.price:.6f} ({best_tp.type})")
        
        plan.last_update = datetime.now()
        plan.revision_count += 1
        
        return plan
    
    async def update_plan(self, symbol: str, current_price: float,
                         orderbook: dict = None, 
                         recent_trades: List[dict] = None,
                         should_recalculate: bool = False) -> Optional[AdaptiveExitPlan]:
        """
        Обновить план на основе текущих условий
        should_recalculate=True для форсированного пересчета уровней
        """
        
        plan = self.active_plans.get(symbol)
        if not plan:
            return None
        
        # Обновляем P&L
        if plan.side == 'SHORT':
            plan.current_pnl_pct = (plan.entry_price - current_price) / plan.entry_price * 100
        else:
            plan.current_pnl_pct = (current_price - plan.entry_price) / plan.entry_price * 100
        
        # Обновляем максимум
        if plan.current_pnl_pct > plan.max_pnl_pct:
            plan.max_pnl_pct = plan.current_pnl_pct
        plan.drawdown_from_max = plan.max_pnl_pct - plan.current_pnl_pct
        
        # Проверяем фазу
        elapsed = (datetime.now() - plan.entry_time).total_seconds()
        if elapsed < 30:
            plan.current_phase = ExitPhase.EARLY
        elif elapsed < 180:
            plan.current_phase = ExitPhase.ESTABLISHED
        elif elapsed < 600:
            plan.current_phase = ExitPhase.MATURE
        else:
            plan.current_phase = ExitPhase.LATE
        
        # Обновляем footprint если есть данные
        if recent_trades:
            footprint = self.analyze_footprint(symbol, orderbook, recent_trades)
            
            # Корректировка на основе дельты
            if footprint.absorption_detected:
                logger.info(f"⚠️ {symbol}: Absorption detected at ${current_price}")
                # Можно закрыть часть позиции раньше
        
        # === ДИНАМИЧЕСКИЙ ПЕРЕСЧЕТ УРОВНЕЙ ===
        # Пересчитываем если:
        # 1. Форсированный пересчет запрошен
        # 2. Цена ушла далеко от входа (>3%)
        # 3. Давно не обновляли (>30 сек)
        time_since_update = (datetime.now() - plan.last_update).total_seconds()
        
        if should_recalculate or abs(plan.current_pnl_pct) > 3 or time_since_update > 30:
            # Ищем новые уровни если есть ордербук
            new_clusters = []
            if orderbook:
                new_clusters = self.find_liquidity_clusters(symbol, current_price, orderbook)
            
            await self.recalculate_levels(symbol, current_price, new_liq_clusters=new_clusters)
        
        plan.last_update = datetime.now()
        plan.revision_count += 1
        
        return plan
    
    def check_exits(self, symbol: str, current_price: float) -> Optional[Tuple[str, float, ExitLevel]]:
        """Проверить нужно ли выходить с детекцией rug pull для говно-койнов"""
        
        plan = self.active_plans.get(symbol)
        if not plan:
            return None
        
        params = self.ASSET_PARAMS[plan.asset_class]
        
        # === RUG PULL DETECTION для MICRO_CAP и NANOCAP ===
        if plan.asset_class in [AssetClass.MICRO_CAP, AssetClass.NANOCAP]:
            # Проверяем резкий дамп после входа
            if plan.side == 'SHORT':
                # Для шорта rug pull = резкий памп вверх
                if plan.current_pnl_pct < -8:  # Быстрый памп против нас
                    # Проверяем скорость изменения цены
                    price_velocity = abs(plan.current_pnl_pct - (plan.drawdown_from_max + plan.current_pnl_pct))
                    if price_velocity > 5:  # Более 5% за короткое время
                        logger.warning(f"🚨 {symbol}: RUG PULL DETECTED (pump)! Velocity: {price_velocity:.1f}%")
                        return ('RUG_PULL_PANIC_EXIT', current_price, ExitLevel(
                            price=current_price,
                            size_pct=100,
                            trigger_reason=f"Rug pull pump detected ({price_velocity:.1f}% velocity)",
                            confidence=95
                        ))
            else:
                # Для лонга rug pull = резкий дамп вниз
                if plan.current_pnl_pct < -5:  # Быстрый дамп
                    price_velocity = abs(plan.current_pnl_pct)
                    if price_velocity > 8:
                        logger.warning(f"🚨 {symbol}: RUG PULL DETECTED (dump)! Velocity: {price_velocity:.1f}%")
                        return ('RUG_PULL_PANIC_EXIT', current_price, ExitLevel(
                            price=current_price,
                            size_pct=100,
                            trigger_reason=f"Rug pull dump detected ({price_velocity:.1f}% velocity)",
                            confidence=95
                        ))
            
            # Rapid exit при превышении порога
            rapid_threshold = params.get('rapid_exit_threshold', 10)
            if plan.current_pnl_pct < -rapid_threshold:
                logger.warning(f"⚠️ {symbol}: Rapid exit triggered ({plan.current_pnl_pct:.1f}% < -{rapid_threshold}%)")
                return ('RAPID_EXIT', current_price, ExitLevel(
                    price=current_price,
                    size_pct=100,
                    trigger_reason=f"Rapid exit threshold ({rapid_threshold}%)",
                    confidence=85
                ))
            
            # Panic exit при резком развороте
            if params.get('panic_exit_enabled', False):
                # Проверяем drawdown от максимума
                if plan.drawdown_from_max > 12:  # Откат от максимума более 12%
                    logger.warning(f"🚨 {symbol}: Panic exit (drawdown {plan.drawdown_from_max:.1f}%)")
                    return ('PANIC_EXIT', current_price, ExitLevel(
                        price=current_price,
                        size_pct=100,
                        trigger_reason=f"Panic exit (drawdown {plan.drawdown_from_max:.1f}%)",
                        confidence=90
                    ))
        
        # === ОБЫЧНАЯ ПРОВЕРКА СТОПА ===
        if plan.side == 'SHORT':
            if current_price >= plan.stop_loss.price:
                return ('STOP_LOSS', current_price, plan.stop_loss)
        else:
            if current_price <= plan.stop_loss.price:
                return ('STOP_LOSS', current_price, plan.stop_loss)
        
        # === ПРОВЕРКА ТЕЙКОВ ===
        for i, tp in enumerate(plan.take_profits):
            hit = False
            if plan.side == 'SHORT':
                if current_price <= tp.price and not hasattr(tp, '_hit'):
                    hit = True
            else:
                if current_price >= tp.price and not hasattr(tp, '_hit'):
                    hit = True
            
            if hit:
                tp._hit = True
                return (f'TAKE_PROFIT_{i+1}', current_price, tp)
        
        # === AGGRESSIVE DRAWDOWN CHECK для всех ===
        if plan.drawdown_from_max > params.get('trailing_start_pct', 8) * 0.5:  # 50% от trailing старта
            logger.info(f"⚠️ {symbol}: Drawdown {plan.drawdown_from_max:.2f}% from max")
            # Для говно-койнов - агрессивный выход
            if plan.asset_class in [AssetClass.MICRO_CAP, AssetClass.NANOCAP] and plan.drawdown_from_max > 8:
                return ('AGGRESSIVE_DRAWDOWN_EXIT', current_price, ExitLevel(
                    price=current_price,
                    size_pct=50,  # Закрываем половину
                    trigger_reason=f"Aggressive drawdown ({plan.drawdown_from_max:.1f}%)",
                    confidence=75
                ))
        
        # === ВРЕМЕННОЙ СТОП ===
        if plan.current_phase == ExitPhase.LATE:
            elapsed = (datetime.now() - plan.entry_time).total_seconds() / 60
            
            if elapsed > params['max_hold_minutes']:
                # Закрываем по времени
                return ('TIME_EXIT', current_price, ExitLevel(
                    price=current_price,
                    size_pct=100,
                    trigger_reason=f"Time limit ({params['max_hold_minutes']} min)",
                    confidence=70
                ))
        
        return None
    
    def get_position_adjustment(self, symbol: str, current_price: float) -> Optional[Tuple[str, float]]:
        """Рекомендация по корректировке позиции (добавление/уменьшение)"""
        
        plan = self.active_plans.get(symbol)
        if not plan:
            return None
        
        # Проверяем условия для добавления
        if plan.current_phase == ExitPhase.ESTABLISHED:
            if plan.current_pnl_pct > 1 and plan.current_pnl_pct < 3:
                # Цена идет в нашу сторону, можно добавить
                if plan.delta_structure == ('bullish' if plan.side == 'LONG' else 'bearish'):
                    return ('ADD_POSITION', 0.5)  # Добавить 50% от начальной
        
        # Проверяем условия для частичного закрытия
        if plan.current_phase == ExitPhase.EARLY:
            if plan.current_pnl_pct < -1:
                # Ранний убыток - закрыть часть
                return ('REDUCE_POSITION', 0.5)
        
        return None
    
    def remove_plan(self, symbol: str):
        """Удалить план после закрытия позиции"""
        if symbol in self.active_plans:
            plan = self.active_plans[symbol]
            logger.info(f"🗑️ Plan removed for {symbol}. Revisions: {plan.revision_count}")
            del self.active_plans[symbol]


# Глобальный инстанс
exit_manager = AdaptiveExitManager()

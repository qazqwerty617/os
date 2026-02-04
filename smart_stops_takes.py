"""
MEXC Pump Monitor - Smart Stops & Takes Calculator
Умный расчет стоп-лоссов и тейк-профитов на основе графического анализа
"""

import time
import logging
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass

from smart_levels import SmartLevelsDetector, OrderBlock, FairValueGap
from pattern_detector_advanced import AdvancedPatternDetector, DetectedPattern
from market_structure import MarketStructureAnalyzer, MarketStructure

logger = logging.getLogger(__name__)


@dataclass
class SmartStopTake:
    """Умные стоп-лосс и тейк-профиты"""
    symbol: str
    entry_price: float
    side: str  # 'LONG' or 'SHORT'
    
    # Стоп-лоссы (от ближайшего к дальнему)
    stop_loss_tight: float  # Тесный стоп (на Order Block или уровне)
    stop_loss_normal: float  # Нормальный стоп (за уровнем)
    stop_loss_wide: float  # Широкий стоп (за несколькими уровнями)
    
    # Тейк-профиты
    take_profit_1: float  # Первый TP (ближайший уровень/Order Block)
    take_profit_2: float  # Второй TP (следующий уровень)
    take_profit_3: float  # Третий TP (дальний уровень/паттерн)
    
    # Метрики
    risk_tight_pct: float
    risk_normal_pct: float
    risk_wide_pct: float
    reward_1_pct: float
    reward_2_pct: float
    reward_3_pct: float
    rr_ratio_1: float
    rr_ratio_2: float
    rr_ratio_3: float
    
    # Обоснование
    stop_reason: str
    tp1_reason: str
    tp2_reason: str
    tp3_reason: str
    
    # Уровни, использованные для расчета
    used_levels: List[str] = None
    used_order_blocks: List[str] = None
    used_patterns: List[str] = None


class SmartStopsTakesCalculator:
    """
    Умный калькулятор стоп-лоссов и тейк-профитов
    Использует графический анализ, Order Blocks, FVG, Market Structure
    """
    
    def __init__(
        self,
        levels_detector: SmartLevelsDetector,
        pattern_detector: AdvancedPatternDetector,
        structure_analyzer: MarketStructureAnalyzer
    ):
        self.levels = levels_detector
        self.patterns = pattern_detector
        self.structure = structure_analyzer
        
        # Минимальные/максимальные риски
        self.min_risk_pct = 1.0  # Минимум 1% риск
        self.max_risk_pct = 8.0  # Максимум 8% риск
        self.min_rr_ratio = 1.5  # Минимум R:R 1:1.5
    
    def calculate_smart_levels(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        current_price: float
    ) -> Optional[SmartStopTake]:
        """
        Рассчитать умные стоп-лоссы и тейк-профиты
        
        Args:
            symbol: Торговая пара
            entry_price: Цена входа
            side: 'LONG' или 'SHORT'
            current_price: Текущая цена
        
        Returns:
            SmartStopTake с рассчитанными уровнями
        """
        # 1. Получить уровни поддержки/сопротивления
        support = self.levels.get_nearest_support(symbol, current_price)
        resistance = self.levels.get_nearest_resistance(symbol, current_price)
        
        # 2. Получить Order Blocks
        order_blocks = self.levels.get_relevant_order_blocks(symbol, current_price, side)
        
        # 3. Получить FVG
        fvgs = self.levels.get_relevant_fvg(symbol, current_price, side)
        
        # 4. Получить паттерны
        detected_patterns = self.patterns.detect_patterns(symbol)
        relevant_patterns = [p for p in detected_patterns if p.target_price]
        
        # 5. Получить структуру рынка
        market_structure = self.structure.get_structure(symbol)
        
        # 6. Рассчитать стоп-лоссы
        stops = self._calculate_stops(
            symbol, entry_price, side, current_price,
            support, resistance, order_blocks, market_structure
        )
        
        # 7. Рассчитать тейк-профиты
        takes = self._calculate_takes(
            symbol, entry_price, side, current_price,
            support, resistance, order_blocks, fvgs, relevant_patterns, market_structure
        )
        
        if not stops or not takes:
            return None
        
        # 8. Рассчитать метрики
        risk_tight = abs((stops['tight'] - entry_price) / entry_price * 100) if stops['tight'] else 0
        risk_normal = abs((stops['normal'] - entry_price) / entry_price * 100) if stops['normal'] else 0
        risk_wide = abs((stops['wide'] - entry_price) / entry_price * 100) if stops['wide'] else 0
        
        reward_1 = abs((entry_price - takes['tp1']) / entry_price * 100) if takes['tp1'] else 0
        reward_2 = abs((entry_price - takes['tp2']) / entry_price * 100) if takes['tp2'] else 0
        reward_3 = abs((entry_price - takes['tp3']) / entry_price * 100) if takes['tp3'] else 0
        
        rr_1 = reward_1 / risk_normal if risk_normal > 0 else 0
        rr_2 = reward_2 / risk_normal if risk_normal > 0 else 0
        rr_3 = reward_3 / risk_normal if risk_normal > 0 else 0
        
        return SmartStopTake(
            symbol=symbol,
            entry_price=entry_price,
            side=side,
            stop_loss_tight=stops['tight'],
            stop_loss_normal=stops['normal'],
            stop_loss_wide=stops['wide'],
            take_profit_1=takes['tp1'],
            take_profit_2=takes['tp2'],
            take_profit_3=takes['tp3'],
            risk_tight_pct=risk_tight,
            risk_normal_pct=risk_normal,
            risk_wide_pct=risk_wide,
            reward_1_pct=reward_1,
            reward_2_pct=reward_2,
            reward_3_pct=reward_3,
            rr_ratio_1=rr_1,
            rr_ratio_2=rr_2,
            rr_ratio_3=rr_3,
            stop_reason=stops['reason'],
            tp1_reason=takes['tp1_reason'],
            tp2_reason=takes['tp2_reason'],
            tp3_reason=takes['tp3_reason'],
            used_levels=stops.get('used_levels', []) + takes.get('used_levels', []),
            used_order_blocks=[f"{ob.block_type} @ {ob.price_low:.8f}" for ob in order_blocks[:2]],
            used_patterns=[p.pattern_type.value for p in relevant_patterns[:2]]
        )
    
    def _calculate_stops(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        current_price: float,
        support: Optional[object],
        resistance: Optional[object],
        order_blocks: List[OrderBlock],
        market_structure: Optional[MarketStructure]
    ) -> Dict:
        """Рассчитать стоп-лоссы"""
        stops = {}
        
        if side == 'SHORT':
            # Для шорта стоп выше входа
            
            # 1. Tight Stop - на ближайшем Order Block или уровне
            tight_stop = None
            tight_reason = ""
            
            # Проверить Order Blocks выше
            if order_blocks:
                bearish_blocks = [ob for ob in order_blocks if ob.block_type == 'bearish' and ob.price_high > entry_price]
                if bearish_blocks:
                    tight_stop = bearish_blocks[0].price_high * 1.002  # Немного выше Order Block
                    tight_reason = f"Order Block @ {bearish_blocks[0].price_high:.8f}"
            
            # Или на уровне сопротивления
            if not tight_stop and resistance:
                tight_stop = resistance.price * 1.002
                tight_reason = f"Resistance @ {resistance.price:.8f} (strength: {resistance.strength})"
            
            # Или на последнем HH
            if not tight_stop and market_structure and market_structure.last_hh:
                tight_stop = market_structure.last_hh * 1.002
                tight_reason = f"Last HH @ {market_structure.last_hh:.8f}"
            
            # Fallback: 2% выше входа
            if not tight_stop:
                tight_stop = entry_price * 1.02
                tight_reason = "2% above entry (default)"
            
            # 2. Normal Stop - за уровнем сопротивления
            normal_stop = None
            if resistance and hasattr(resistance, 'price'):
                normal_stop = resistance.price * 1.005  # 0.5% выше сопротивления
            elif market_structure and market_structure.last_hh:
                normal_stop = market_structure.last_hh * 1.005
            else:
                normal_stop = entry_price * 1.04  # 4% по умолчанию
            
            # 3. Wide Stop - за несколькими уровнями или 6%
            wide_stop = entry_price * 1.06  # 6% по умолчанию
            if resistance and hasattr(resistance, 'strength') and resistance.strength > 70:
                wide_stop = resistance.price * 1.01  # 1% выше сильного сопротивления
            
            stops = {
                'tight': tight_stop,
                'normal': normal_stop,
                'wide': wide_stop,
                'reason': tight_reason,
                'used_levels': [f"Resistance: {resistance.price:.8f}" if (resistance and hasattr(resistance, 'price')) else "None"]
            }
        
        else:  # LONG
            # Для лонга стоп ниже входа (аналогично, но наоборот)
            tight_stop = None
            tight_reason = ""
            
            if order_blocks:
                bullish_blocks = [ob for ob in order_blocks if ob.block_type == 'bullish' and ob.price_low < entry_price]
                if bullish_blocks:
                    tight_stop = bullish_blocks[0].price_low * 0.998
                    tight_reason = f"Order Block @ {bullish_blocks[0].price_low:.8f}"
            
            if not tight_stop and support and hasattr(support, 'price'):
                tight_stop = support.price * 0.998
                tight_reason = f"Support @ {support.price:.8f} (strength: {support.strength})"
            
            if not tight_stop and market_structure and market_structure.last_ll:
                tight_stop = market_structure.last_ll * 0.998
                tight_reason = f"Last LL @ {market_structure.last_ll:.8f}"
            
            if not tight_stop:
                tight_stop = entry_price * 0.98
                tight_reason = "2% below entry (default)"
            
            normal_stop = support.price * 0.995 if (support and hasattr(support, 'price')) else (market_structure.last_ll * 0.995 if market_structure and market_structure.last_ll else entry_price * 0.96)
            wide_stop = entry_price * 0.94 if not (support and hasattr(support, 'strength') and support.strength > 70) else support.price * 0.99
            
            stops = {
                'tight': tight_stop,
                'normal': normal_stop,
                'wide': wide_stop,
                'reason': tight_reason,
                'used_levels': [f"Support: {support.price:.8f}" if (support and hasattr(support, 'price')) else "None"]
            }
        
        return stops
    
    def _calculate_takes(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        current_price: float,
        support: Optional[object],
        resistance: Optional[object],
        order_blocks: List[OrderBlock],
        fvgs: List[FairValueGap],
        patterns: List[DetectedPattern],
        market_structure: Optional[MarketStructure]
    ) -> Dict:
        """Рассчитать тейк-профиты"""
        takes = {}
        
        if side == 'SHORT':
            # Для шорта тейки ниже входа
            
            # TP1 - ближайший уровень поддержки или Order Block
            tp1 = None
            tp1_reason = ""
            
            # Проверить Bullish Order Blocks ниже
            if order_blocks:
                bullish_blocks = [ob for ob in order_blocks if ob.block_type == 'bullish' and ob.price_low < entry_price]
                if bullish_blocks:
                    tp1 = bullish_blocks[0].price_low * 0.998  # Немного ниже Order Block
                    tp1_reason = f"Bullish Order Block @ {bullish_blocks[0].price_low:.8f}"
            
            # Или на уровне поддержки
            if not tp1 and support and hasattr(support, 'price'):
                tp1 = support.price * 0.998
                tp1_reason = f"Support @ {support.price:.8f} (strength: {support.strength})"
            
            # Или на FVG
            if not tp1 and fvgs:
                bullish_fvg = [f for f in fvgs if f.gap_type == 'bullish' and f.price_high < entry_price]
                if bullish_fvg:
                    tp1 = bullish_fvg[0].price_high * 0.998
                    tp1_reason = f"Bullish FVG @ {bullish_fvg[0].price_high:.8f}"
            
            # Или на последнем HL
            if not tp1 and market_structure and market_structure.last_hl:
                tp1 = market_structure.last_hl * 0.998
                tp1_reason = f"Last HL @ {market_structure.last_hl:.8f}"
            
            # Fallback: 3% ниже входа
            if not tp1:
                tp1 = entry_price * 0.97
                tp1_reason = "3% below entry (default)"
            
            # TP2 - следующий уровень или паттерн
            tp2 = None
            tp2_reason = ""
            
            # Проверить паттерны
            if patterns:
                bearish_patterns = [p for p in patterns if p.target_price and p.target_price < entry_price]
                if bearish_patterns:
                    tp2 = bearish_patterns[0].target_price
                    tp2_reason = f"{bearish_patterns[0].pattern_type.value} target @ {tp2:.8f}"
            
            # Или следующий уровень поддержки
            if not tp2 and support and hasattr(support, 'price'):
                # Ищем следующий уровень ниже
                tp2 = support.price * 0.95  # 5% ниже первой поддержки
                tp2_reason = f"Next support zone @ {tp2:.8f}"
            
            # Fallback: 6% ниже входа
            if not tp2:
                tp2 = entry_price * 0.94
                tp2_reason = "6% below entry (default)"
            
            # TP3 - дальний уровень или паттерн
            tp3 = None
            tp3_reason = ""
            
            if patterns and len(patterns) > 1:
                bearish_patterns = [p for p in patterns if p.target_price and p.target_price < tp2]
                if bearish_patterns:
                    tp3 = bearish_patterns[0].target_price
                    tp3_reason = f"{bearish_patterns[0].pattern_type.value} target @ {tp3:.8f}"
            
            if not tp3:
                tp3 = entry_price * 0.90  # 10% ниже входа
                tp3_reason = "10% below entry (default)"
            
            takes = {
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'tp1_reason': tp1_reason,
                'tp2_reason': tp2_reason,
                'tp3_reason': tp3_reason,
                'used_levels': [f"Support: {support.price:.8f}" if (support and hasattr(support, 'price')) else "None"]
            }
        
        else:  # LONG (аналогично, но наоборот)
            tp1 = None
            tp1_reason = ""
            
            if order_blocks:
                bearish_blocks = [ob for ob in order_blocks if ob.block_type == 'bearish' and ob.price_high > entry_price]
                if bearish_blocks:
                    tp1 = bearish_blocks[0].price_high * 1.002
                    tp1_reason = f"Bearish Order Block @ {bearish_blocks[0].price_high:.8f}"
            
            if not tp1 and resistance and hasattr(resistance, 'price'):
                tp1 = resistance.price * 1.002
                tp1_reason = f"Resistance @ {resistance.price:.8f}"
            
            if not tp1:
                tp1 = entry_price * 1.03
                tp1_reason = "3% above entry (default)"
            
            tp2 = entry_price * 1.06 if not patterns else None
            tp3 = entry_price * 1.10
            
            takes = {
                'tp1': tp1,
                'tp2': tp2,
                'tp3': tp3,
                'tp1_reason': tp1_reason,
                'tp2_reason': "6% above entry (default)",
                'tp3_reason': "10% above entry (default)",
                'used_levels': [f"Resistance: {resistance.price:.8f}" if (resistance and hasattr(resistance, 'price')) else "None"]
            }
        
        return takes

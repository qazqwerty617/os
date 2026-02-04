"""
MEXC Pump Monitor - Quick Exit System
Система быстрого выхода для мемкоинов при резких движениях
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QuickExitSignal:
    """Сигнал быстрого выхода"""
    symbol: str
    reason: str
    current_price: float
    entry_price: float
    profit_pct: float
    urgency: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    recommended_action: str


class QuickExitSystem:
    """
    Система быстрого выхода для мемкоинов
    Обнаруживает признаки разворота и рекомендует быстрый выход
    """
    
    def __init__(self):
        # Пороги для разных типов выхода
        self.volume_drop_threshold = 0.5  # Объем упал на 50%
        self.price_reversal_threshold = 3.0  # Откат 3% от максимума
        self.volume_exhaustion_threshold = 0.3  # Объем упал на 70%
        self.rsi_overbought_exit = 90  # RSI > 90 - выход
        self.profit_target_quick = 10.0  # 10% прибыль - быстрый выход
        
        # История для отслеживания
        self.price_history: Dict[str, list] = {}
        self.volume_history: Dict[str, list] = {}
        self.max_history = 20
        
        self.stats = {
            'exit_signals_generated': 0,
            'critical_exits': 0,
            'high_urgency_exits': 0
        }
    
    def record_price(self, symbol: str, price: float, volume: float, rsi: float = 0):
        """Записать цену и объем для анализа"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
            self.volume_history[symbol] = []
        
        self.price_history[symbol].append({
            'price': price,
            'volume': volume,
            'rsi': rsi,
            'timestamp': time.time()
        })
        
        # Ограничить историю
        if len(self.price_history[symbol]) > self.max_history:
            self.price_history[symbol] = self.price_history[symbol][-self.max_history:]
            self.volume_history[symbol] = self.volume_history[symbol][-self.max_history:]
    
    def check_quick_exit(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: str = 'SHORT'
    ) -> Optional[QuickExitSignal]:
        """
        Проверить условия для быстрого выхода
        
        Returns:
            QuickExitSignal или None
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 5:
            return None
        
        history = self.price_history[symbol]
        recent = history[-5:]  # Последние 5 точек
        
        # Рассчитать прибыль
        if side == 'SHORT':
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        else:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        # 1. Проверка: Достигнут целевой профит
        if profit_pct >= self.profit_target_quick:
            return QuickExitSignal(
                symbol=symbol,
                reason="PROFIT_TARGET_REACHED",
                current_price=current_price,
                entry_price=entry_price,
                profit_pct=profit_pct,
                urgency='MEDIUM',
                recommended_action=f"Take profit at {profit_pct:.1f}%"
            )
        
        # 2. Проверка: Объем упал резко (истощение)
        volumes = [h['volume'] for h in recent]
        if len(volumes) >= 3:
            avg_volume = sum(volumes[:-2]) / len(volumes[:-2])
            current_volume = volumes[-1]
            
            if avg_volume > 0 and current_volume < avg_volume * self.volume_exhaustion_threshold:
                volume_drop = (1 - current_volume / avg_volume) * 100
                return QuickExitSignal(
                    symbol=symbol,
                    reason="VOLUME_EXHAUSTION",
                    current_price=current_price,
                    entry_price=entry_price,
                    profit_pct=profit_pct,
                    urgency='HIGH',
                    recommended_action=f"Volume dropped {volume_drop:.1f}% - exit now"
                )
        
        # 3. Проверка: Разворот цены (для SHORT)
        if side == 'SHORT' and len(recent) >= 3:
            prices = [h['price'] for h in recent]
            max_price = max(prices)
            current = prices[-1]
            
            # Если цена откатилась от максимума
            if max_price > entry_price:
                reversal_pct = ((max_price - current) / max_price) * 100
                if reversal_pct < self.price_reversal_threshold and current > entry_price * 0.98:
                    return QuickExitSignal(
                        symbol=symbol,
                        reason="PRICE_REVERSAL",
                        current_price=current_price,
                        entry_price=entry_price,
                        profit_pct=profit_pct,
                        urgency='CRITICAL',
                        recommended_action=f"Price reversing - exit immediately!"
                    )
        
        # 4. Проверка: RSI экстремально перекуплен
        if recent[-1].get('rsi', 0) > self.rsi_overbought_exit:
            return QuickExitSignal(
                symbol=symbol,
                reason="RSI_EXTREME_OVERBOUGHT",
                current_price=current_price,
                entry_price=entry_price,
                profit_pct=profit_pct,
                urgency='HIGH',
                recommended_action=f"RSI {recent[-1]['rsi']:.1f} - extreme overbought"
            )
        
        # 5. Проверка: Быстрый рост объема при падении цены (для SHORT - плохо)
        if side == 'SHORT' and len(volumes) >= 3:
            price_change = ((recent[-1]['price'] - recent[-2]['price']) / recent[-2]['price']) * 100
            volume_change = ((volumes[-1] - volumes[-2]) / volumes[-2] * 100) if volumes[-2] > 0 else 0
            
            # Цена растет + объем растет = возможен разворот
            if price_change > 2 and volume_change > 50:
                return QuickExitSignal(
                    symbol=symbol,
                    reason="REVERSAL_MOMENTUM",
                    current_price=current_price,
                    entry_price=entry_price,
                    profit_pct=profit_pct,
                    urgency='CRITICAL',
                    recommended_action="Strong reversal momentum - exit now!"
                )
        
        return None
    
    def get_stats(self) -> Dict:
        """Статистика"""
        return self.stats

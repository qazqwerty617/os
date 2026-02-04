"""
MEXC Pump Monitor - Smart Partial Close
Умное частичное закрытие позиций для мемкоинов
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PartialCloseDecision:
    """Решение о частичном закрытии"""
    symbol: str
    close_pct: float  # Процент для закрытия (0-100)
    reason: str
    current_profit_pct: float
    urgency: str  # 'LOW', 'MEDIUM', 'HIGH'
    new_stop_loss: Optional[float] = None  # Новый стоп после закрытия


class SmartPartialClose:
    """
    Умная система частичного закрытия позиций
    Оптимизирована для мемкоинов (быстрые движения)
    """
    
    def __init__(self):
        # Стратегии частичного закрытия
        self.profit_levels = [
            (5.0, 25.0),   # При 5% прибыли - закрыть 25%
            (10.0, 40.0),  # При 10% - закрыть еще 40% (итого 65%)
            (20.0, 30.0),  # При 20% - закрыть еще 30% (итого 95%)
            (50.0, 5.0),   # При 50% - закрыть оставшиеся 5%
        ]
        
        # Агрессивная стратегия для больших пампов
        self.aggressive_levels = [
            (3.0, 30.0),   # При 3% - закрыть 30%
            (7.0, 40.0),   # При 7% - закрыть еще 40%
            (15.0, 25.0),  # При 15% - закрыть еще 25%
            (30.0, 5.0),   # При 30% - закрыть оставшиеся 5%
        ]
        
        # История закрытий
        self.close_history: Dict[str, list] = {}
        
        self.stats = {
            'partial_closes': 0,
            'total_profit_locked': 0.0,
            'positions_fully_closed': 0
        }
    
    def should_partial_close(
        self,
        symbol: str,
        entry_price: float,
        current_price: float,
        side: str,
        pump_size_pct: float = 0,
        remaining_pct: float = 100  # Сколько еще осталось в позиции
    ) -> Optional[PartialCloseDecision]:
        """
        Определить, нужно ли частично закрыть позицию
        
        Args:
            symbol: Символ
            entry_price: Цена входа
            current_price: Текущая цена
            side: 'LONG' или 'SHORT'
            pump_size_pct: Размер пампы (для выбора стратегии)
            remaining_pct: Сколько еще осталось в позиции (100% = полная позиция)
        
        Returns:
            PartialCloseDecision или None
        """
        if remaining_pct <= 0:
            return None
        
        # Рассчитать прибыль
        if side == 'SHORT':
            profit_pct = ((entry_price - current_price) / entry_price) * 100
        else:
            profit_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Выбрать стратегию
        if pump_size_pct >= 30:
            levels = self.aggressive_levels
        else:
            levels = self.profit_levels
        
        # Проверить каждый уровень
        for profit_threshold, close_pct in levels:
            if profit_pct >= profit_threshold:
                # Проверить, не закрывали ли уже на этом уровне
                if symbol not in self.close_history:
                    self.close_history[symbol] = []
                
                already_closed = any(
                    abs(close['profit_pct'] - profit_threshold) < 0.5
                    for close in self.close_history[symbol]
                )
                
                if not already_closed:
                    # Рассчитать реальный процент для закрытия (от оставшейся позиции)
                    actual_close_pct = min(close_pct, remaining_pct)
                    
                    # Определить urgency
                    if profit_pct >= 20:
                        urgency = 'HIGH'
                    elif profit_pct >= 10:
                        urgency = 'MEDIUM'
                    else:
                        urgency = 'LOW'
                    
                    # Рассчитать новый стоп-лосс (breakeven или небольшой профит)
                    if side == 'SHORT':
                        new_stop = entry_price * 0.98  # 2% профит защищен
                    else:
                        new_stop = entry_price * 1.02
                    
                    decision = PartialCloseDecision(
                        symbol=symbol,
                        close_pct=actual_close_pct,
                        reason=f"Profit target {profit_threshold}% reached",
                        current_profit_pct=profit_pct,
                        urgency=urgency,
                        new_stop_loss=new_stop
                    )
                    
                    # Записать в историю
                    self.close_history[symbol].append({
                        'profit_pct': profit_pct,
                        'close_pct': actual_close_pct,
                        'timestamp': time.time()
                    })
                    
                    self.stats['partial_closes'] += 1
                    
                    logger.info(
                        f"💰 PARTIAL CLOSE: {symbol} | "
                        f"Profit: {profit_pct:.1f}% | "
                        f"Close: {actual_close_pct:.0f}% | "
                        f"Reason: {decision.reason}"
                    )
                    
                    return decision
        
        return None
    
    def get_close_history(self, symbol: str) -> list:
        """Получить историю закрытий для символа"""
        return self.close_history.get(symbol, [])
    
    def reset_symbol(self, symbol: str):
        """Сбросить историю для символа (после полного закрытия)"""
        if symbol in self.close_history:
            del self.close_history[symbol]
            self.stats['positions_fully_closed'] += 1
    
    def get_stats(self) -> Dict:
        """Статистика"""
        return self.stats

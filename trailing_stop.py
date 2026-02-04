"""
MEXC Pump Monitor - Trailing Stop Loss
Адаптивные трейлинг стопы для мемкоинов
"""

import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TrailingStop:
    """Трейлинг стоп для позиции"""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    initial_stop: float
    current_stop: float
    highest_price: float  # Для LONG
    lowest_price: float   # Для SHORT
    trail_distance_pct: float  # Расстояние трейлинга в %
    activation_pct: float  # Активация после X% прибыли
    is_active: bool = False
    
    def update(self, current_price: float) -> Optional[float]:
        """
        Обновить трейлинг стоп
        
        Returns:
            Новый стоп-лосс или None если не изменился
        """
        if self.side == 'LONG':
            # Обновляем максимум
            if current_price > self.highest_price:
                self.highest_price = current_price
                
                # Проверяем активацию
                profit_pct = ((current_price - self.initial_stop) / self.initial_stop) * 100
                if profit_pct >= self.activation_pct:
                    self.is_active = True
                
                # Если активен, двигаем стоп вверх
                if self.is_active:
                    new_stop = current_price * (1 - self.trail_distance_pct / 100)
                    if new_stop > self.current_stop:
                        old_stop = self.current_stop
                        self.current_stop = new_stop
                        return new_stop
        else:  # SHORT
            # Обновляем минимум
            if current_price < self.lowest_price:
                self.lowest_price = current_price
                
                # Проверяем активацию
                profit_pct = ((self.initial_stop - current_price) / self.initial_stop) * 100
                if profit_pct >= self.activation_pct:
                    self.is_active = True
                
                # Если активен, двигаем стоп вниз
                if self.is_active:
                    new_stop = current_price * (1 + self.trail_distance_pct / 100)
                    if new_stop < self.current_stop:
                        old_stop = self.current_stop
                        self.current_stop = new_stop
                        return new_stop
        
        return None


class TrailingStopManager:
    """
    Менеджер трейлинг стопов для мемкоинов
    Адаптивные стопы, которые следуют за ценой
    """
    
    def __init__(self):
        self.trailing_stops: Dict[str, TrailingStop] = {}
        
        # Настройки для мемкоинов
        self.default_trail_distance = 3.0  # 3% для мемкоинов (было 5%)
        self.default_activation = 5.0  # Активация после 5% прибыли
        
        # Агрессивные настройки для больших пампов
        self.aggressive_trail_distance = 2.0  # 2% для мега-пампов
        self.aggressive_activation = 3.0  # Активация после 3%
    
    def add_trailing_stop(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        initial_stop: float,
        pump_size_pct: float = 0
    ):
        """Добавить трейлинг стоп для позиции"""
        # Выбираем настройки в зависимости от размера пампы
        if pump_size_pct >= 30:
            trail_distance = self.aggressive_trail_distance
            activation = self.aggressive_activation
        else:
            trail_distance = self.default_trail_distance
            activation = self.default_activation
        
        trailing = TrailingStop(
            symbol=symbol,
            side=side,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            highest_price=entry_price if side == 'LONG' else float('inf'),
            lowest_price=entry_price if side == 'SHORT' else 0,
            trail_distance_pct=trail_distance,
            activation_pct=activation
        )
        
        self.trailing_stops[symbol] = trailing
        logger.info(
            f"📌 TRAILING STOP: {symbol} {side} | "
            f"Entry: ${entry_price:.8f} | Stop: ${initial_stop:.8f} | "
            f"Trail: {trail_distance}% | Activate: {activation}%"
        )
    
    def update_price(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Обновить цену и вернуть новый стоп-лосс если изменился
        
        Returns:
            Новый стоп-лосс или None
        """
        if symbol not in self.trailing_stops:
            return None
        
        trailing = self.trailing_stops[symbol]
        new_stop = trailing.update(current_price)
        
        if new_stop:
            logger.info(
                f"📈 TRAILING UPDATED: {symbol} | "
                f"Price: ${current_price:.8f} | "
                f"New Stop: ${new_stop:.8f} | "
                f"Profit Locked: {((new_stop - trailing.initial_stop) / trailing.initial_stop * 100):+.1f}%"
            )
        
        return new_stop
    
    def remove_trailing_stop(self, symbol: str):
        """Удалить трейлинг стоп"""
        if symbol in self.trailing_stops:
            del self.trailing_stops[symbol]
    
    def get_current_stop(self, symbol: str) -> Optional[float]:
        """Получить текущий стоп-лосс"""
        trailing = self.trailing_stops.get(symbol)
        return trailing.current_stop if trailing else None
    
    def is_stop_hit(self, symbol: str, current_price: float) -> bool:
        """Проверить, сработал ли стоп-лосс"""
        trailing = self.trailing_stops.get(symbol)
        if not trailing:
            return False
        
        if trailing.side == 'LONG':
            return current_price <= trailing.current_stop
        else:  # SHORT
            return current_price >= trailing.current_stop

"""
MEXC Pump Monitor - Data Cache
Кэширование данных для ускорения обработки мемкоинов
"""

import time
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from collections import OrderedDict

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Запись в кэше"""
    data: Any
    timestamp: float
    ttl: float  # Time to live в секундах
    
    def is_expired(self) -> bool:
        """Проверить, истек ли срок действия"""
        return time.time() - self.timestamp > self.ttl


class DataCache:
    """
    Быстрый кэш для данных о ценах, объемах и индикаторах
    Оптимизирован для мемкоинов (быстрый доступ)
    """
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, CacheEntry] = OrderedDict()
        self.max_size = max_size
        
        # TTL по умолчанию для разных типов данных
        self.default_ttl = {
            'price': 1.0,      # Цены - 1 секунда
            'volume': 2.0,    # Объемы - 2 секунды
            'indicators': 5.0, # Индикаторы - 5 секунд
            'ticker': 0.5,    # Тикеры - 0.5 секунды
            'klines': 10.0    # Свечи - 10 секунд
        }
        
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0
        }
    
    def get(self, key: str, data_type: str = 'price') -> Optional[Any]:
        """
        Получить данные из кэша
        
        Args:
            key: Ключ кэша (например, 'BTC_USDT_price')
            data_type: Тип данных для определения TTL
        
        Returns:
            Данные или None если нет в кэше или истек срок
        """
        entry = self.cache.get(key)
        
        if entry is None:
            self.stats['misses'] += 1
            return None
        
        # Проверка на истечение срока
        if entry.is_expired():
            del self.cache[key]
            self.stats['misses'] += 1
            return None
        
        # Переместить в конец (LRU)
        self.cache.move_to_end(key)
        self.stats['hits'] += 1
        return entry.data
    
    def set(self, key: str, data: Any, data_type: str = 'price', ttl: Optional[float] = None):
        """
        Сохранить данные в кэш
        
        Args:
            key: Ключ кэша
            data: Данные для сохранения
            data_type: Тип данных
            ttl: Время жизни в секундах (если None, используется default для типа)
        """
        if ttl is None:
            ttl = self.default_ttl.get(data_type, 1.0)
        
        # Если кэш переполнен, удалить старейший
        if len(self.cache) >= self.max_size:
            self.cache.popitem(last=False)  # Удалить первый (старейший)
            self.stats['evictions'] += 1
        
        entry = CacheEntry(
            data=data,
            timestamp=time.time(),
            ttl=ttl
        )
        
        self.cache[key] = entry
        self.cache.move_to_end(key)  # Переместить в конец
    
    def invalidate(self, key: str):
        """Удалить запись из кэша"""
        if key in self.cache:
            del self.cache[key]
    
    def invalidate_pattern(self, pattern: str):
        """Удалить все записи, соответствующие паттерну"""
        keys_to_delete = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_delete:
            del self.cache[key]
    
    def clear(self):
        """Очистить весь кэш"""
        self.cache.clear()
    
    def cleanup_expired(self):
        """Очистить истекшие записи"""
        now = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if entry.is_expired()
        ]
        
        for key in expired_keys:
            del self.cache[key]
    
    def get_stats(self) -> Dict:
        """Статистика кэша"""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = (self.stats['hits'] / total * 100) if total > 0 else 0
        
        return {
            **self.stats,
            'hit_rate': hit_rate,
            'size': len(self.cache),
            'max_size': self.max_size
        }


# Глобальный экземпляр кэша
cache = DataCache(max_size=2000)

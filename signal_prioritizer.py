"""
MEXC Pump Monitor - Signal Prioritizer
Система приоритизации сигналов для быстрого исполнения мемкоинов
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import heapq

from signal_engine import EnhancedSignal, SignalQuality

logger = logging.getLogger(__name__)


class SignalPriority(Enum):
    """Приоритеты сигналов"""
    CRITICAL = 1  # Мега-пампы 50%+ - мгновенное исполнение
    HIGH = 2      # Сильные пампы 20%+ - быстрый вход
    MEDIUM = 3    # Обычные пампы 10%+ - стандартный вход
    LOW = 4       # Ранние пампы 3%+ - осторожный вход


@dataclass
class PrioritizedSignal:
    """Сигнал с приоритетом"""
    signal: EnhancedSignal
    priority: SignalPriority
    priority_score: float  # 0-100, выше = важнее
    timestamp: int
    estimated_profit: float = 0
    risk_score: float = 0
    
    def __lt__(self, other):
        """Для heapq - меньший приоритет = выше в очереди"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.priority_score > other.priority_score  # Больше score = выше


class SignalPrioritizer:
    """
    Система приоритизации сигналов для мемкоинов
    Обрабатывает сигналы по приоритету для максимальной скорости
    """
    
    def __init__(self, max_queue_size: int = 50):
        self.priority_queue: List[PrioritizedSignal] = []  # Min-heap
        self.processed_signals: Dict[str, int] = {}  # symbol -> timestamp
        self.max_queue_size = max_queue_size
        
        # Статистика
        self.stats = {
            'total_signals': 0,
            'critical_executed': 0,
            'high_executed': 0,
            'medium_executed': 0,
            'low_executed': 0,
            'skipped_duplicates': 0
        }
    
    def calculate_priority(self, signal: EnhancedSignal):
        """
        Рассчитать приоритет сигнала
        
        Returns:
            (Priority, Priority Score 0-100)
        """
        score = 0.0
        
        # 1. Ценовое движение (40% веса)
        price_change = signal.price_change_pct
        if price_change >= 50:
            price_score = 100
            priority = SignalPriority.CRITICAL
        elif price_change >= 20:
            price_score = 80
            priority = SignalPriority.HIGH
        elif price_change >= 10:
            price_score = 60
            priority = SignalPriority.MEDIUM
        else:
            price_score = 40
            priority = SignalPriority.LOW
        
        score += price_score * 0.4
        
        # 2. Качество сигнала (30% веса)
        quality_scores = {
            SignalQuality.S_TIER: 100,
            SignalQuality.A_TIER: 80,
            SignalQuality.B_TIER: 60,
            SignalQuality.C_TIER: 40
        }
        quality_score = quality_scores.get(signal.quality, 50)
        score += quality_score * 0.3
        
        # 3. Финальный score (20% веса)
        score += signal.final_score * 0.2
        
        # 4. Объем (10% веса)
        if signal.volume_ratio >= 10:
            vol_score = 100
        elif signal.volume_ratio >= 5:
            vol_score = 80
        elif signal.volume_ratio >= 3:
            vol_score = 60
        else:
            vol_score = 40
        score += vol_score * 0.1
        
        # Обновляем приоритет на основе финального score
        if score >= 90:
            priority = SignalPriority.CRITICAL
        elif score >= 75:
            priority = SignalPriority.HIGH
        elif score >= 60:
            priority = SignalPriority.MEDIUM
        else:
            priority = SignalPriority.LOW
        
        return priority, min(100, score)
    
    def add_signal(self, signal: EnhancedSignal) -> bool:
        """
        Добавить сигнал в очередь приоритетов
        
        Returns:
            True если добавлен, False если пропущен
        """
        # Проверка на дубликаты (в последние 2 минуты)
        now = int(time.time() * 1000)
        last_time = self.processed_signals.get(signal.symbol, 0)
        if now - last_time < 120000:  # 2 минуты
            self.stats['skipped_duplicates'] += 1
            return False
        
        # Рассчитать приоритет
        priority, priority_score = self.calculate_priority(signal)
        
        # Оценить потенциальную прибыль
        risk = abs(signal.stop_loss - signal.entry_price)
        reward = abs(signal.entry_price - signal.take_profit_1)
        estimated_profit = (reward / risk) * signal.final_score if risk > 0 else 0
        
        # Создать приоритизированный сигнал
        prioritized = PrioritizedSignal(
            signal=signal,
            priority=priority,
            priority_score=priority_score,
            timestamp=now,
            estimated_profit=estimated_profit,
            risk_score=risk / signal.entry_price * 100 if signal.entry_price > 0 else 0
        )
        
        # Добавить в очередь (min-heap)
        heapq.heappush(self.priority_queue, prioritized)
        
        # Ограничить размер очереди
        if len(self.priority_queue) > self.max_queue_size:
            heapq.heappop(self.priority_queue)  # Удалить самый низкий приоритет
        
        self.processed_signals[signal.symbol] = now
        self.stats['total_signals'] += 1
        
        logger.info(
            f"📊 PRIORITY: {signal.symbol} | "
            f"Priority: {priority.name} | Score: {priority_score:.1f} | "
            f"Change: +{signal.price_change_pct:.1f}%"
        )
        
        return True
    
    def get_next_signal(self) -> Optional[PrioritizedSignal]:
        """Получить следующий сигнал с наивысшим приоритетом"""
        if not self.priority_queue:
            return None
        
        return heapq.heappop(self.priority_queue)
    
    def get_critical_signals(self) -> List[PrioritizedSignal]:
        """Получить все критические сигналы"""
        critical = [
            ps for ps in self.priority_queue
            if ps.priority == SignalPriority.CRITICAL
        ]
        return sorted(critical, key=lambda x: x.priority_score, reverse=True)
    
    def get_queue_size(self) -> int:
        """Размер очереди"""
        return len(self.priority_queue)
    
    def clear_old_signals(self, max_age_seconds: int = 300):
        """Очистить старые сигналы (старше 5 минут)"""
        now = int(time.time() * 1000)
        cutoff = now - (max_age_seconds * 1000)
        
        # Фильтруем очередь
        self.priority_queue = [
            ps for ps in self.priority_queue
            if ps.timestamp > cutoff
        ]
        
        # Пересоздаем heap
        heapq.heapify(self.priority_queue)
    
    def get_stats(self) -> Dict:
        """Статистика"""
        return {
            **self.stats,
            'queue_size': len(self.priority_queue),
            'critical_in_queue': len([ps for ps in self.priority_queue if ps.priority == SignalPriority.CRITICAL]),
            'high_in_queue': len([ps for ps in self.priority_queue if ps.priority == SignalPriority.HIGH])
        }

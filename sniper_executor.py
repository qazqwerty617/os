"""
MEXC Pump Monitor - Sniper Executor
Мгновенное исполнение для критических сигналов мемкоинов
"""

import asyncio
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from signal_engine import EnhancedSignal
from signal_prioritizer import PrioritizedSignal, SignalPriority
from auto_trader import AutoTrader
from risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class SniperExecution:
    """Результат снайперского исполнения"""
    symbol: str
    executed: bool
    execution_time_ms: float
    entry_price: float
    order_id: Optional[str] = None
    error: Optional[str] = None


class SniperExecutor:
    """
    Снайперский исполнитель для мгновенного входа в мемкоины
    Оптимизирован для критических сигналов (50%+ пампы)
    """
    
    def __init__(
        self,
        auto_trader: AutoTrader,
        risk_manager: RiskManager,
        max_execution_time_ms: float = 500  # Максимум 500мс на исполнение
    ):
        self.auto_trader = auto_trader
        self.risk_manager = risk_manager
        self.max_execution_time_ms = max_execution_time_ms
        
        # Кэш для быстрого доступа
        self.price_cache: Dict[str, float] = {}
        self.cache_ttl = 1.0  # 1 секунда
        
        # Статистика
        self.stats = {
            'total_executions': 0,
            'successful': 0,
            'failed': 0,
            'avg_execution_time_ms': 0,
            'fastest_execution_ms': float('inf'),
            'slowest_execution_ms': 0
        }
    
    async def execute_critical_signal(
        self,
        prioritized_signal: PrioritizedSignal
    ) -> SniperExecution:
        """
        Мгновенное исполнение критического сигнала
        
        Цель: < 500мс от получения сигнала до размещения ордера
        """
        start_time = time.time()
        signal = prioritized_signal.signal
        
        try:
            # 1. Быстрая валидация (< 50мс)
            if not self._validate_signal(signal):
                return SniperExecution(
                    symbol=signal.symbol,
                    executed=False,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    entry_price=signal.entry_price,
                    error="Validation failed"
                )
            
            # 2. Получить актуальную цену (кэш или быстрый запрос)
            current_price = await self._get_current_price_fast(signal.symbol)
            if not current_price:
                return SniperExecution(
                    symbol=signal.symbol,
                    executed=False,
                    execution_time_ms=(time.time() - start_time) * 1000,
                    entry_price=signal.entry_price,
                    error="Price fetch failed"
                )
            
            # 3. Адаптировать уровни под текущую цену (если цена ушла)
            entry_price = current_price
            stop_loss = signal.stop_loss
            take_profit_1 = signal.take_profit_1
            
            # Если цена сильно ушла, пересчитываем
            price_diff_pct = abs(current_price - signal.entry_price) / signal.entry_price * 100
            if price_diff_pct > 2:  # Цена ушла больше чем на 2%
                # Пересчитываем уровни относительно текущей цены
                risk = abs(signal.stop_loss - signal.entry_price)
                stop_loss = current_price + risk if signal.stop_loss > signal.entry_price else current_price - risk
                take_profit_1 = current_price - (risk * 1.5) if signal.stop_loss > signal.entry_price else current_price + (risk * 1.5)
            
            # 4. Быстрое размещение ордера
            order = await self.auto_trader.place_short_order(
                symbol=signal.symbol,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit1=take_profit_1,
                take_profit2=signal.take_profit_2,
                confidence=signal.final_score,
                signal_source="SNIPER_CRITICAL"
            )
            
            execution_time_ms = (time.time() - start_time) * 1000
            
            if order:
                self.stats['successful'] += 1
                self._update_stats(execution_time_ms)
                
                logger.info(
                    f"🎯 SNIPER EXECUTED: {signal.symbol} | "
                    f"Time: {execution_time_ms:.0f}ms | "
                    f"Price: ${entry_price:.8f}"
                )
                
                return SniperExecution(
                    symbol=signal.symbol,
                    executed=True,
                    execution_time_ms=execution_time_ms,
                    entry_price=entry_price,
                    order_id=order.order_id
                )
            else:
                self.stats['failed'] += 1
                return SniperExecution(
                    symbol=signal.symbol,
                    executed=False,
                    execution_time_ms=execution_time_ms,
                    entry_price=entry_price,
                    error="Order placement failed"
                )
                
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            self.stats['failed'] += 1
            logger.error(f"Sniper execution error for {signal.symbol}: {e}")
            
            return SniperExecution(
                symbol=signal.symbol,
                executed=False,
                execution_time_ms=execution_time_ms,
                entry_price=signal.entry_price,
                error=str(e)
            )
        finally:
            self.stats['total_executions'] += 1
    
    def _validate_signal(self, signal: EnhancedSignal) -> bool:
        """Быстрая валидация сигнала"""
        # Проверка на критичность
        if signal.price_change_pct < 20:
            return False
        
        # Проверка качества
        if signal.quality.value not in ['S', 'A']:
            return False
        
        # Проверка score
        if signal.final_score < 75:
            return False
        
        return True
    
    async def _get_current_price_fast(self, symbol: str) -> Optional[float]:
        """Получить цену быстро (кэш или быстрый запрос)"""
        # Проверка кэша
        cached = self.price_cache.get(symbol)
        if cached and (time.time() - cached.get('timestamp', 0)) < self.cache_ttl:
            return cached['price']
        
        # Быстрый запрос (если есть доступ к клиенту)
        # В реальности здесь будет быстрый REST запрос
        # Для демо возвращаем None (будет использована цена из сигнала)
        return None
    
    def _update_stats(self, execution_time_ms: float):
        """Обновить статистику"""
        if execution_time_ms < self.stats['fastest_execution_ms']:
            self.stats['fastest_execution_ms'] = execution_time_ms
        if execution_time_ms > self.stats['slowest_execution_ms']:
            self.stats['slowest_execution_ms'] = execution_time_ms
        
        # Среднее время
        total = self.stats['total_executions']
        current_avg = self.stats['avg_execution_time_ms']
        self.stats['avg_execution_time_ms'] = (
            (current_avg * (total - 1) + execution_time_ms) / total
            if total > 0 else execution_time_ms
        )
    
    def get_stats(self) -> Dict:
        """Статистика исполнения"""
        return {
            **self.stats,
            'success_rate': (
                self.stats['successful'] / self.stats['total_executions'] * 100
                if self.stats['total_executions'] > 0 else 0
            )
        }

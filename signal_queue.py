"""
MEXC Pump Monitor - Signal Queue
Оптимизированная очередь обработки сигналов с приоритетами
"""

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import IntEnum
from collections import defaultdict

logger = logging.getLogger(__name__)


class SignalPriority(IntEnum):
    """Приоритеты сигналов"""
    CRITICAL = 0    # Mega pumps, new listings
    HIGH = 1        # Strong signals, S-tier
    MEDIUM = 2      # A/B tier signals
    LOW = 3         # C tier, informational
    BATCH = 4       # Batch processing


@dataclass(order=True)
class QueueItem:
    """Элемент очереди с приоритетом"""
    priority: int
    timestamp: float = field(compare=False)
    signal_type: str = field(compare=False)
    data: Any = field(compare=False)
    callback: Optional[Callable] = field(compare=False, default=None)


class SignalQueue:
    """
    ⚡ Async Signal Queue with Priority Processing
    
    Features:
    - Priority-based processing
    - Rate limiting
    - Batch processing for low priority
    - Dead letter queue for failed items
    - Metrics tracking
    """
    
    def __init__(
        self,
        max_workers: int = 5,
        rate_limit: float = 0.1,  # Min seconds between processing
        batch_size: int = 10,
        batch_timeout: float = 5.0
    ):
        self.max_workers = max_workers
        self.rate_limit = rate_limit
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        
        # Priority queue
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        
        # Batch queue for low priority items
        self._batch_buffer: List[QueueItem] = []
        self._last_batch_flush = time.time()
        
        # Dead letter queue
        self._dlq: List[QueueItem] = []
        self._max_dlq_size = 100
        
        # Handlers by signal type
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Worker tasks
        self._workers: List[asyncio.Task] = []
        self._running = False
        
        # Metrics
        self.metrics = {
            'total_processed': 0,
            'total_failed': 0,
            'by_priority': defaultdict(int),
            'by_type': defaultdict(int),
            'avg_processing_time': 0,
            'queue_high_water': 0
        }
        
        # Rate limiting
        self._last_process_time = 0
    
    async def start(self):
        """Запустить воркеры"""
        self._running = True
        
        # Start workers
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(worker)
        
        # Start batch processor
        batch_task = asyncio.create_task(self._batch_processor())
        self._workers.append(batch_task)
        
        logger.info(f"⚡ Signal Queue started with {self.max_workers} workers")
    
    async def stop(self):
        """Остановить очередь"""
        self._running = False
        
        # Wait for queue to empty (with timeout)
        try:
            await asyncio.wait_for(self._queue.join(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Queue stop timeout - some items may be lost")
        
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        
        logger.info(f"Signal Queue stopped. Processed: {self.metrics['total_processed']}")
    
    def register_handler(self, signal_type: str, handler: Callable):
        """Зарегистрировать обработчик для типа сигнала"""
        self._handlers[signal_type].append(handler)
        logger.debug(f"Registered handler for {signal_type}")
    
    async def put(
        self,
        signal_type: str,
        data: Any,
        priority: SignalPriority = SignalPriority.MEDIUM,
        callback: Optional[Callable] = None
    ):
        """
        Добавить сигнал в очередь
        
        Args:
            signal_type: Тип сигнала (pump, listing, whale, etc.)
            data: Данные сигнала
            priority: Приоритет обработки
            callback: Опциональный callback после обработки
        """
        item = QueueItem(
            priority=int(priority),
            timestamp=time.time(),
            signal_type=signal_type,
            data=data,
            callback=callback
        )
        
        # Batch low priority items
        if priority == SignalPriority.BATCH:
            self._batch_buffer.append(item)
            if len(self._batch_buffer) >= self.batch_size:
                await self._flush_batch()
        else:
            await self._queue.put(item)
        
        # Update high water mark
        current_size = self._queue.qsize()
        if current_size > self.metrics['queue_high_water']:
            self.metrics['queue_high_water'] = current_size
    
    async def put_critical(self, signal_type: str, data: Any):
        """Добавить критический сигнал (highest priority)"""
        await self.put(signal_type, data, SignalPriority.CRITICAL)
    
    async def put_high(self, signal_type: str, data: Any):
        """Добавить высокоприоритетный сигнал"""
        await self.put(signal_type, data, SignalPriority.HIGH)
    
    async def _worker(self, name: str):
        """Worker coroutine"""
        while self._running:
            try:
                # Get item with timeout
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Rate limiting
                now = time.time()
                elapsed = now - self._last_process_time
                if elapsed < self.rate_limit:
                    await asyncio.sleep(self.rate_limit - elapsed)
                self._last_process_time = time.time()
                
                # Process item
                start_time = time.time()
                success = await self._process_item(item)
                process_time = time.time() - start_time
                
                # Update metrics
                self.metrics['total_processed'] += 1
                self.metrics['by_priority'][item.priority] += 1
                self.metrics['by_type'][item.signal_type] += 1
                
                # Update average processing time
                n = self.metrics['total_processed']
                old_avg = self.metrics['avg_processing_time']
                self.metrics['avg_processing_time'] = old_avg + (process_time - old_avg) / n
                
                if not success:
                    self.metrics['total_failed'] += 1
                
                # Mark task done
                self._queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {name} error: {e}")
    
    async def _process_item(self, item: QueueItem) -> bool:
        """Обработать элемент очереди"""
        handlers = self._handlers.get(item.signal_type, [])
        
        if not handlers:
            # No handlers, try default
            handlers = self._handlers.get('*', [])
        
        if not handlers:
            logger.debug(f"No handlers for {item.signal_type}")
            return True
        
        success = True
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(item.data)
                else:
                    handler(item.data)
            except Exception as e:
                logger.error(f"Handler error for {item.signal_type}: {e}")
                success = False
                
                # Add to dead letter queue
                self._dlq.append(item)
                if len(self._dlq) > self._max_dlq_size:
                    self._dlq.pop(0)
        
        # Call callback if provided
        if item.callback:
            try:
                if asyncio.iscoroutinefunction(item.callback):
                    await item.callback(success, item.data)
                else:
                    item.callback(success, item.data)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        return success
    
    async def _batch_processor(self):
        """Batch processor for low priority items"""
        while self._running:
            try:
                await asyncio.sleep(1)
                
                # Check if batch should be flushed
                if self._batch_buffer:
                    time_since_last = time.time() - self._last_batch_flush
                    if time_since_last >= self.batch_timeout:
                        await self._flush_batch()
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Batch processor error: {e}")
    
    async def _flush_batch(self):
        """Flush batch buffer to main queue"""
        if not self._batch_buffer:
            return
        
        # Process batch as single item
        batch_handlers = self._handlers.get('batch', [])
        
        if batch_handlers:
            batch_data = [item.data for item in self._batch_buffer]
            for handler in batch_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(batch_data)
                    else:
                        handler(batch_data)
                except Exception as e:
                    logger.error(f"Batch handler error: {e}")
        else:
            # No batch handler, process individually
            for item in self._batch_buffer:
                item.priority = int(SignalPriority.LOW)
                await self._queue.put(item)
        
        self._batch_buffer = []
        self._last_batch_flush = time.time()
    
    def get_metrics(self) -> Dict:
        """Получить метрики"""
        return {
            **self.metrics,
            'queue_size': self._queue.qsize(),
            'batch_buffer_size': len(self._batch_buffer),
            'dlq_size': len(self._dlq),
            'workers': len(self._workers)
        }
    
    def get_dlq(self) -> List[QueueItem]:
        """Получить dead letter queue"""
        return self._dlq.copy()
    
    async def retry_dlq(self):
        """Retry items in dead letter queue"""
        items = self._dlq.copy()
        self._dlq.clear()
        
        for item in items:
            await self._queue.put(item)
        
        logger.info(f"Retrying {len(items)} items from DLQ")

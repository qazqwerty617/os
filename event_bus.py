"""
MEXC Pump Monitor - Event Bus
High-performance event-driven architecture for real-time processing
"""

import asyncio
import time
import logging
from typing import Dict, List, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import weakref

logger = logging.getLogger(__name__)


class EventType(Enum):
    """System event types"""
    # Market events
    PRICE_UPDATE = "price_update"
    VOLUME_SPIKE = "volume_spike"
    TRADE = "trade"
    
    # Detection events
    PUMP_DETECTED = "pump_detected"
    DUMP_DETECTED = "dump_detected"
    MICRO_PUMP = "micro_pump"
    
    # Whale events
    WHALE_BUY = "whale_buy"
    WHALE_SELL = "whale_sell"
    WHALE_ALERT = "whale_alert"
    
    # Liquidation events
    LIQUIDATION = "liquidation"
    CASCADE_WARNING = "cascade_warning"
    CASCADE_ACTIVE = "cascade_active"
    
    # Listing events  
    NEW_LISTING = "new_listing"
    LISTING_UPDATE = "listing_update"
    
    # Signal events
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_UPDATED = "signal_updated"
    SIGNAL_CLOSED = "signal_closed"
    
    # System events
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Event:
    """Event object"""
    type: EventType
    timestamp: int
    data: Dict[str, Any]
    source: str = "system"
    priority: int = 5  # 1-10, lower = higher priority
    
    # Metadata
    id: str = field(default_factory=lambda: f"{time.time_ns()}")
    processed: bool = False
    process_time_ms: float = 0


class EventFilter:
    """Filter for event subscriptions"""
    
    def __init__(
        self,
        event_types: Optional[Set[EventType]] = None,
        symbols: Optional[Set[str]] = None,
        min_priority: int = 10,
        sources: Optional[Set[str]] = None
    ):
        self.event_types = event_types
        self.symbols = symbols
        self.min_priority = min_priority
        self.sources = sources
    
    def matches(self, event: Event) -> bool:
        """Check if event matches filter"""
        # Event type filter
        if self.event_types and event.type not in self.event_types:
            return False
        
        # Symbol filter
        if self.symbols:
            event_symbol = event.data.get('symbol')
            if event_symbol and event_symbol not in self.symbols:
                return False
        
        # Priority filter
        if event.priority > self.min_priority:
            return False
        
        # Source filter
        if self.sources and event.source not in self.sources:
            return False
        
        return True


@dataclass
class Subscriber:
    """Event subscriber"""
    callback: Callable
    filter: Optional[EventFilter] = None
    is_async: bool = True
    name: str = "anonymous"
    
    # Stats
    events_received: int = 0
    avg_process_time_ms: float = 0


class EventBus:
    """
    High-performance async event bus
    Supports filtering, priority queuing, and async processing
    Optimized: 3 priority levels (high=1, medium=2, low=3)
    """
    
    def __init__(self, max_queue_size: int = 5000):
        # 3 priority queues instead of 10 for efficiency
        self._queues = {
            1: asyncio.Queue(maxsize=max_queue_size // 3),  # High priority
            2: asyncio.Queue(maxsize=max_queue_size // 3),  # Medium priority  
            3: asyncio.Queue(maxsize=max_queue_size // 3),  # Low priority
        }
        
        # Subscribers
        self._subscribers: List[Subscriber] = []
        
        # Event history (ring buffer)
        self._history: List[Event] = []
        self._history_max = 1000
        
        # Processing stats
        self.stats = {
            'events_published': 0,
            'events_processed': 0,
            'events_dropped': 0,
            'avg_latency_ms': 0,
            'by_type': defaultdict(int)
        }
        
        # Workers
        self._workers: List[asyncio.Task] = []
        self._running = False
    
    async def start(self, num_workers: int = 3):
        """Start event processing"""
        self._running = True
        
        # Start worker tasks
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        
        logger.info(f"⚡ EventBus started with {num_workers} workers")
    
    async def stop(self):
        """Stop event processing"""
        self._running = False
        
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        
        logger.info("EventBus stopped")
    
    def subscribe(
        self,
        callback: Callable,
        event_types: Optional[Set[EventType]] = None,
        symbols: Optional[Set[str]] = None,
        name: str = "anonymous"
    ) -> Subscriber:
        """
        Subscribe to events
        
        Args:
            callback: Function to call with event
            event_types: Filter by event types
            symbols: Filter by symbols
            name: Subscriber name for debugging
        
        Returns:
            Subscriber object
        """
        event_filter = EventFilter(
            event_types=event_types,
            symbols=symbols
        ) if event_types or symbols else None
        
        subscriber = Subscriber(
            callback=callback,
            filter=event_filter,
            is_async=asyncio.iscoroutinefunction(callback),
            name=name
        )
        
        self._subscribers.append(subscriber)
        logger.debug(f"Subscriber '{name}' registered")
        
        return subscriber
    
    def unsubscribe(self, subscriber: Subscriber):
        """Unsubscribe from events"""
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)
    
    async def publish(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: str = "system",
        priority: int = 5
    ) -> Event:
        """
        Publish an event
        
        Args:
            event_type: Type of event
            data: Event data
            source: Event source
            priority: 1-10 (lower = higher priority)
        
        Returns:
            Published event
        """
        event = Event(
            type=event_type,
            timestamp=int(time.time() * 1000),
            data=data,
            source=source,
            priority=priority
        )
        # Normalize priority to 3 levels
        normalized_priority = 1 if priority <= 2 else (2 if priority <= 5 else 3)
        
        # Add to priority queue
        queue = self._queues.get(normalized_priority, self._queues[2])
        
        try:
            queue.put_nowait(event)
            self.stats['events_published'] += 1
            self.stats['by_type'][event_type.value] += 1
        except asyncio.QueueFull:
            self.stats['events_dropped'] += 1
            logger.warning(f"Event dropped (queue full): {event_type.value}")
        
        return event
    
    async def publish_sync(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        source: str = "system"
    ):
        """Publish and immediately process (bypass queue)"""
        event = Event(
            type=event_type,
            timestamp=int(time.time() * 1000),
            data=data,
            source=source,
            priority=1
        )
        
        await self._dispatch(event)
    
    async def _worker(self, worker_id: int):
        """Event processing worker"""
        while self._running:
            try:
                # Process queues by priority
                event = await self._get_next_event()
                
                if event:
                    start = time.time()
                    await self._dispatch(event)
                    event.process_time_ms = (time.time() - start) * 1000
                    event.processed = True
                    
                    self.stats['events_processed'] += 1
                    
                    # Update avg latency
                    n = self.stats['events_processed']
                    old_avg = self.stats['avg_latency_ms']
                    self.stats['avg_latency_ms'] = old_avg + (event.process_time_ms - old_avg) / n
                    
                    # Add to history
                    self._history.append(event)
                    if len(self._history) > self._history_max:
                        self._history = self._history[-self._history_max:]
                else:
                    await asyncio.sleep(0.01)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")
                await asyncio.sleep(0.1)
    
    async def _get_next_event(self) -> Optional[Event]:
        """Get next event by priority"""
        # Check queues in priority order (1, 2, 3)
        for priority in [1, 2, 3]:
            queue = self._queues[priority]
            if not queue.empty():
                try:
                    return queue.get_nowait()
                except:
                    continue
        return None
    
    async def _dispatch(self, event: Event):
        """Dispatch event to subscribers"""
        tasks = []
        
        for subscriber in self._subscribers:
            # Check filter
            if subscriber.filter and not subscriber.filter.matches(event):
                continue
            
            try:
                if subscriber.is_async:
                    task = asyncio.create_task(subscriber.callback(event))
                    tasks.append(task)
                else:
                    subscriber.callback(event)
                
                subscriber.events_received += 1
            except Exception as e:
                logger.error(f"Subscriber '{subscriber.name}' error: {e}")
        
        # Wait for async callbacks
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_history(
        self,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[Event]:
        """Get event history"""
        events = self._history
        
        if event_type:
            events = [e for e in events if e.type == event_type]
        
        return events[-limit:]
    
    def get_stats(self) -> Dict:
        """Get bus statistics"""
        return {
            **self.stats,
            'subscribers': len(self._subscribers),
            'queue_sizes': {p: q.qsize() for p, q in self._queues.items()},
            'history_size': len(self._history)
        }


# Global event bus instance
event_bus = EventBus()


# Convenience functions
async def publish(event_type: EventType, data: Dict[str, Any], **kwargs):
    """Publish event to global bus"""
    return await event_bus.publish(event_type, data, **kwargs)


def subscribe(callback: Callable, **kwargs) -> Subscriber:
    """Subscribe to global bus"""
    return event_bus.subscribe(callback, **kwargs)


# Event creators for common events
async def emit_pump_detected(
    symbol: str,
    price: float,
    price_change_pct: float,
    tier: str,
    score: int,
    **extra
):
    """Emit pump detected event"""
    await event_bus.publish(
        EventType.PUMP_DETECTED,
        {
            'symbol': symbol,
            'price': price,
            'price_change_pct': price_change_pct,
            'tier': tier,
            'score': score,
            **extra
        },
        priority=2
    )


async def emit_whale_order(
    symbol: str,
    side: str,
    value_usd: float,
    category: str,
    **extra
):
    """Emit whale order event"""
    event_type = EventType.WHALE_BUY if side.upper() == 'BUY' else EventType.WHALE_SELL
    
    await event_bus.publish(
        event_type,
        {
            'symbol': symbol,
            'side': side,
            'value_usd': value_usd,
            'category': category,
            **extra
        },
        priority=3
    )


async def emit_new_listing(
    symbol: str,
    base_asset: str,
    initial_price: float,
    **extra
):
    """Emit new listing event"""
    await event_bus.publish(
        EventType.NEW_LISTING,
        {
            'symbol': symbol,
            'base_asset': base_asset,
            'initial_price': initial_price,
            **extra
        },
        priority=1  # Highest priority
    )


async def emit_signal(
    symbol: str,
    quality: str,
    score: int,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    **extra
):
    """Emit signal generated event"""
    await event_bus.publish(
        EventType.SIGNAL_GENERATED,
        {
            'symbol': symbol,
            'quality': quality,
            'score': score,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            **extra
        },
        priority=2
    )

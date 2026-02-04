"""
MEXC Pump Monitor - Whale Detection
Optimized large order tracking and institutional activity detection
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class WhaleCategory(Enum):
    """Whale size categories"""
    SMALL_FISH = "SMALL_FISH"      # <$10k
    DOLPHIN = "DOLPHIN"            # $10k-$50k
    WHALE = "WHALE"                # $50k-$250k
    MEGA_WHALE = "MEGA_WHALE"      # $250k-$1M
    INSTITUTION = "INSTITUTION"    # >$1M


# Category thresholds (USD)
CATEGORY_THRESHOLDS = [
    (1_000_000, WhaleCategory.INSTITUTION),
    (250_000, WhaleCategory.MEGA_WHALE),
    (50_000, WhaleCategory.WHALE),
    (10_000, WhaleCategory.DOLPHIN),
    (0, WhaleCategory.SMALL_FISH),
]


@dataclass
class LargeOrder:
    """Detected large order"""
    symbol: str
    timestamp: int
    side: OrderSide
    price: float
    quantity: float
    value_usd: float
    category: WhaleCategory
    price_impact_pct: float = 0
    depth_level: int = 0
    is_aggressive: bool = False


@dataclass
class WhaleActivity:
    """Aggregated whale activity for a symbol"""
    symbol: str
    timestamp: int
    
    whale_buys: int = 0
    whale_sells: int = 0
    mega_whale_buys: int = 0
    mega_whale_sells: int = 0
    institution_buys: int = 0
    institution_sells: int = 0
    
    buy_volume_usd: float = 0
    sell_volume_usd: float = 0
    net_flow_usd: float = 0
    
    recent_orders: List[LargeOrder] = field(default_factory=list)
    whale_pressure_score: int = 50
    
    def calculate_pressure(self):
        """Calculate whale buying/selling pressure"""
        total_buys = self.whale_buys + self.mega_whale_buys * 2 + self.institution_buys * 5
        total_sells = self.whale_sells + self.mega_whale_sells * 2 + self.institution_sells * 5
        
        total = total_buys + total_sells
        self.whale_pressure_score = int((total_buys / total) * 100) if total > 0 else 50
        self.net_flow_usd = self.buy_volume_usd - self.sell_volume_usd


@dataclass
class AccumulationZone:
    """Detected accumulation/distribution zone"""
    symbol: str
    price_low: float
    price_high: float
    total_volume_usd: float
    buy_volume_pct: float
    is_accumulation: bool
    strength: int
    first_seen: int
    last_seen: int


class WhaleDetector:
    """
    Optimized whale detection and large order tracking
    """
    
    def __init__(self):
        self.order_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.activity: Dict[str, WhaleActivity] = {}
        self.accumulation_zones: Dict[str, List[AccumulationZone]] = defaultdict(list)
        self.alerts: deque = deque(maxlen=100)
        self._whale_callbacks: List = []
        
        self.stats = {
            'orders_tracked': 0,
            'whales_detected': 0,
            'institutions_detected': 0
        }
    
    def on_whale_detected(self, callback):
        self._whale_callbacks.append(callback)
    
    @staticmethod
    def classify_order(value_usd: float) -> WhaleCategory:
        """Classify order by size"""
        for threshold, category in CATEGORY_THRESHOLDS:
            if value_usd >= threshold:
                return category
        return WhaleCategory.SMALL_FISH
    
    async def process_trade(
        self,
        symbol: str,
        price: float,
        quantity: float,
        side: str,
        timestamp: int = None
    ):
        """Process trade and detect whale activity"""
        timestamp = timestamp or int(time.time() * 1000)
        value_usd = price * quantity
        
        category = self.classify_order(value_usd)
        
        if category == WhaleCategory.SMALL_FISH:
            return
        
        order_side = OrderSide.BUY if side.upper() == 'BUY' else OrderSide.SELL
        
        order = LargeOrder(
            symbol=symbol,
            timestamp=timestamp,
            side=order_side,
            price=price,
            quantity=quantity,
            value_usd=value_usd,
            category=category,
            is_aggressive=True
        )
        
        self.order_history[symbol].append(order)
        self.stats['orders_tracked'] += 1
        
        await self._update_activity(symbol, order)
        
        if category in (WhaleCategory.WHALE, WhaleCategory.MEGA_WHALE):
            self.stats['whales_detected'] += 1
        if category == WhaleCategory.INSTITUTION:
            self.stats['institutions_detected'] += 1
        
        if category in (WhaleCategory.MEGA_WHALE, WhaleCategory.INSTITUTION):
            await self._notify_whale(order)
    
    async def _update_activity(self, symbol: str, order: LargeOrder):
        """Update aggregated activity"""
        if symbol not in self.activity:
            self.activity[symbol] = WhaleActivity(
                symbol=symbol,
                timestamp=int(time.time() * 1000)
            )
        
        a = self.activity[symbol]
        a.timestamp = int(time.time() * 1000)
        
        is_buy = order.side == OrderSide.BUY
        
        if is_buy:
            a.buy_volume_usd += order.value_usd
            if order.category == WhaleCategory.WHALE:
                a.whale_buys += 1
            elif order.category == WhaleCategory.MEGA_WHALE:
                a.mega_whale_buys += 1
            elif order.category == WhaleCategory.INSTITUTION:
                a.institution_buys += 1
        else:
            a.sell_volume_usd += order.value_usd
            if order.category == WhaleCategory.WHALE:
                a.whale_sells += 1
            elif order.category == WhaleCategory.MEGA_WHALE:
                a.mega_whale_sells += 1
            elif order.category == WhaleCategory.INSTITUTION:
                a.institution_sells += 1
        
        a.recent_orders.append(order)
        if len(a.recent_orders) > 50:
            a.recent_orders = a.recent_orders[-50:]
        
        a.calculate_pressure()
    
    async def _notify_whale(self, order: LargeOrder):
        """Notify callbacks"""
        for callback in self._whale_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(order)
                else:
                    callback(order)
            except Exception as e:
                logger.error(f"Whale callback error: {e}")
    
    def detect_accumulation_zones(
        self,
        symbol: str,
        price_data: List[Tuple[float, float, str]],
        num_zones: int = 5
    ) -> List[AccumulationZone]:
        """Detect accumulation/distribution zones"""
        if len(price_data) < 10:
            return []
        
        prices = [p[0] for p in price_data]
        min_price, max_price = min(prices), max(prices)
        price_range = max_price - min_price
        
        if price_range == 0:
            return []
        
        zone_size = price_range / num_zones
        zones = []
        now = int(time.time() * 1000)
        
        for i in range(num_zones):
            zone_low = min_price + (i * zone_size)
            zone_high = min_price + ((i + 1) * zone_size)
            
            buy_volume = sum(v for p, v, s in price_data if zone_low <= p < zone_high and s.upper() == 'BUY')
            sell_volume = sum(v for p, v, s in price_data if zone_low <= p < zone_high and s.upper() != 'BUY')
            
            total = buy_volume + sell_volume
            if total < 1000:
                continue
            
            buy_pct = (buy_volume / total) * 100
            is_accumulation = buy_pct > 55
            strength = min(100, int(abs(buy_pct - 50) * 2))
            
            zones.append(AccumulationZone(
                symbol=symbol,
                price_low=zone_low,
                price_high=zone_high,
                total_volume_usd=total,
                buy_volume_pct=buy_pct,
                is_accumulation=is_accumulation,
                strength=strength,
                first_seen=now,
                last_seen=now
            ))
        
        zones.sort(key=lambda z: z.strength, reverse=True)
        self.accumulation_zones[symbol] = zones
        return zones
    
    def get_activity(self, symbol: str) -> Optional[WhaleActivity]:
        return self.activity.get(symbol)
    
    def get_top_whale_symbols(self, limit: int = 20) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with most whale activity"""
        return sorted(
            self.activity.items(),
            key=lambda x: x[1].buy_volume_usd + x[1].sell_volume_usd,
            reverse=True
        )[:limit]
    
    def get_buy_pressure_symbols(self, min_pressure: int = 70) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with high whale buy pressure"""
        return sorted(
            [(s, a) for s, a in self.activity.items() if a.whale_pressure_score >= min_pressure],
            key=lambda x: x[1].whale_pressure_score,
            reverse=True
        )
    
    def get_sell_pressure_symbols(self, max_pressure: int = 30) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with high whale sell pressure (good for shorts)"""
        return sorted(
            [(s, a) for s, a in self.activity.items() if a.whale_pressure_score <= max_pressure],
            key=lambda x: x[1].whale_pressure_score
        )
    
    def get_recent_whale_orders(self, limit: int = 50) -> List[LargeOrder]:
        """Get most recent whale orders"""
        all_orders = []
        for orders in self.order_history.values():
            all_orders.extend(orders)
        
        all_orders.sort(key=lambda x: x.timestamp, reverse=True)
        return all_orders[:limit]

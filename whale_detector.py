"""
MEXC Pump Monitor - Whale Detection & Large Order Tracking
Detects institutional/whale activity and large order flow
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class WhaleCategory(Enum):
    """Whale size categories"""
    SMALL_FISH = "SMALL_FISH"      # < $10k
    DOLPHIN = "DOLPHIN"            # $10k - $50k
    WHALE = "WHALE"                # $50k - $250k
    MEGA_WHALE = "MEGA_WHALE"      # $250k - $1M
    INSTITUTION = "INSTITUTION"    # > $1M


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
    
    # Market impact
    price_impact_pct: float = 0
    
    # Order book position
    depth_level: int = 0  # How deep in order book
    is_aggressive: bool = False  # Market order vs limit


@dataclass
class WhaleActivity:
    """Aggregated whale activity for a symbol"""
    symbol: str
    timestamp: int
    
    # Order counts by category
    whale_buys: int = 0
    whale_sells: int = 0
    mega_whale_buys: int = 0
    mega_whale_sells: int = 0
    institution_buys: int = 0
    institution_sells: int = 0
    
    # Volume by side
    buy_volume_usd: float = 0
    sell_volume_usd: float = 0
    
    # Net flow
    net_flow_usd: float = 0
    
    # Recent large orders
    recent_orders: List[LargeOrder] = field(default_factory=list)
    
    # Scores
    whale_pressure_score: int = 50  # 0-100, >50 = buy pressure
    
    def calculate_pressure(self):
        """Calculate whale buying/selling pressure"""
        total_buys = self.whale_buys + self.mega_whale_buys * 2 + self.institution_buys * 5
        total_sells = self.whale_sells + self.mega_whale_sells * 2 + self.institution_sells * 5
        
        if total_buys + total_sells == 0:
            self.whale_pressure_score = 50
        else:
            self.whale_pressure_score = int((total_buys / (total_buys + total_sells)) * 100)
        
        self.net_flow_usd = self.buy_volume_usd - self.sell_volume_usd


@dataclass
class AccumulationZone:
    """Detected accumulation/distribution zone"""
    symbol: str
    price_low: float
    price_high: float
    total_volume_usd: float
    buy_volume_pct: float  # Percentage of buys vs sells
    is_accumulation: bool  # True = buying, False = distribution
    strength: int  # 0-100
    first_seen: int
    last_seen: int


class WhaleDetector:
    """
    Whale detection and large order flow tracking
    Identifies institutional activity and smart money flow
    """
    
    # Thresholds for whale categories (USD)
    THRESHOLDS = {
        WhaleCategory.SMALL_FISH: 10_000,
        WhaleCategory.DOLPHIN: 50_000,
        WhaleCategory.WHALE: 250_000,
        WhaleCategory.MEGA_WHALE: 1_000_000,
        WhaleCategory.INSTITUTION: float('inf')
    }
    
    def __init__(self):
        # Order history per symbol
        self.order_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        
        # Aggregated activity per symbol
        self.activity: Dict[str, WhaleActivity] = {}
        
        # Accumulation zones
        self.accumulation_zones: Dict[str, List[AccumulationZone]] = defaultdict(list)
        
        # Whale alerts
        self.alerts: deque = deque(maxlen=100)
        
        # Callbacks
        self._whale_callbacks: List = []
        
        # Statistics
        self.stats = {
            'orders_tracked': 0,
            'whales_detected': 0,
            'institutions_detected': 0
        }
    
    def on_whale_detected(self, callback):
        """Register callback for whale detection"""
        self._whale_callbacks.append(callback)
    
    def classify_order(self, value_usd: float) -> WhaleCategory:
        """Classify order by size"""
        if value_usd < self.THRESHOLDS[WhaleCategory.SMALL_FISH]:
            return WhaleCategory.SMALL_FISH
        elif value_usd < self.THRESHOLDS[WhaleCategory.DOLPHIN]:
            return WhaleCategory.DOLPHIN
        elif value_usd < self.THRESHOLDS[WhaleCategory.WHALE]:
            return WhaleCategory.WHALE
        elif value_usd < self.THRESHOLDS[WhaleCategory.MEGA_WHALE]:
            return WhaleCategory.MEGA_WHALE
        else:
            return WhaleCategory.INSTITUTION
    
    async def process_trade(
        self,
        symbol: str,
        price: float,
        quantity: float,
        side: str,
        timestamp: int = None
    ):
        """Process a trade and detect whale activity"""
        timestamp = timestamp or int(time.time() * 1000)
        value_usd = price * quantity
        
        category = self.classify_order(value_usd)
        
        # Skip small fish
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
            is_aggressive=True  # Assuming trades are aggressive
        )
        
        # Store order
        self.order_history[symbol].append(order)
        self.stats['orders_tracked'] += 1
        
        # Update activity
        await self._update_activity(symbol, order)
        
        # Track stats
        if category in [WhaleCategory.WHALE, WhaleCategory.MEGA_WHALE]:
            self.stats['whales_detected'] += 1
        if category == WhaleCategory.INSTITUTION:
            self.stats['institutions_detected'] += 1
        
        # Trigger callbacks for significant orders
        if category in [WhaleCategory.MEGA_WHALE, WhaleCategory.INSTITUTION]:
            await self._notify_whale(order)
    
    async def _update_activity(self, symbol: str, order: LargeOrder):
        """Update aggregated activity for symbol"""
        if symbol not in self.activity:
            self.activity[symbol] = WhaleActivity(
                symbol=symbol,
                timestamp=int(time.time() * 1000)
            )
        
        activity = self.activity[symbol]
        activity.timestamp = int(time.time() * 1000)
        
        # Update counts
        if order.side == OrderSide.BUY:
            activity.buy_volume_usd += order.value_usd
            if order.category == WhaleCategory.WHALE:
                activity.whale_buys += 1
            elif order.category == WhaleCategory.MEGA_WHALE:
                activity.mega_whale_buys += 1
            elif order.category == WhaleCategory.INSTITUTION:
                activity.institution_buys += 1
        else:
            activity.sell_volume_usd += order.value_usd
            if order.category == WhaleCategory.WHALE:
                activity.whale_sells += 1
            elif order.category == WhaleCategory.MEGA_WHALE:
                activity.mega_whale_sells += 1
            elif order.category == WhaleCategory.INSTITUTION:
                activity.institution_sells += 1
        
        # Keep recent orders
        activity.recent_orders.append(order)
        if len(activity.recent_orders) > 50:
            activity.recent_orders = activity.recent_orders[-50:]
        
        activity.calculate_pressure()
    
    async def _notify_whale(self, order: LargeOrder):
        """Notify callbacks about whale activity"""
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
        price_data: List[Tuple[float, float, str]],  # (price, volume, side)
        num_zones: int = 5
    ) -> List[AccumulationZone]:
        """
        Detect accumulation/distribution zones from price data
        
        Args:
            symbol: Trading pair
            price_data: List of (price, volume_usd, side) tuples
            num_zones: Number of zones to detect
        
        Returns:
            List of detected zones
        """
        if len(price_data) < 10:
            return []
        
        # Get price range
        prices = [p[0] for p in price_data]
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        
        if price_range == 0:
            return []
        
        # Divide into zones
        zone_size = price_range / num_zones
        zones = []
        
        for i in range(num_zones):
            zone_low = min_price + (i * zone_size)
            zone_high = min_price + ((i + 1) * zone_size)
            
            # Calculate volume in zone
            buy_volume = 0
            sell_volume = 0
            first_ts = None
            last_ts = None
            
            for price, volume, side in price_data:
                if zone_low <= price < zone_high:
                    if side.upper() == 'BUY':
                        buy_volume += volume
                    else:
                        sell_volume += volume
            
            total_volume = buy_volume + sell_volume
            if total_volume < 1000:  # Minimum $1000
                continue
            
            buy_pct = (buy_volume / total_volume) * 100 if total_volume > 0 else 50
            is_accumulation = buy_pct > 55  # More buying than selling
            
            strength = int(abs(buy_pct - 50) * 2)  # 0-100
            
            zone = AccumulationZone(
                symbol=symbol,
                price_low=zone_low,
                price_high=zone_high,
                total_volume_usd=total_volume,
                buy_volume_pct=buy_pct,
                is_accumulation=is_accumulation,
                strength=min(100, strength),
                first_seen=int(time.time() * 1000),
                last_seen=int(time.time() * 1000)
            )
            zones.append(zone)
        
        # Sort by strength
        zones.sort(key=lambda z: z.strength, reverse=True)
        
        self.accumulation_zones[symbol] = zones
        return zones
    
    def get_activity(self, symbol: str) -> Optional[WhaleActivity]:
        """Get whale activity for symbol"""
        return self.activity.get(symbol)
    
    def get_top_whale_symbols(self, limit: int = 20) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with most whale activity"""
        sorted_activity = sorted(
            self.activity.items(),
            key=lambda x: x[1].buy_volume_usd + x[1].sell_volume_usd,
            reverse=True
        )
        return sorted_activity[:limit]
    
    def get_buy_pressure_symbols(self, min_pressure: int = 70) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with high whale buy pressure"""
        high_pressure = [
            (s, a) for s, a in self.activity.items()
            if a.whale_pressure_score >= min_pressure
        ]
        return sorted(high_pressure, key=lambda x: x[1].whale_pressure_score, reverse=True)
    
    def get_sell_pressure_symbols(self, max_pressure: int = 30) -> List[Tuple[str, WhaleActivity]]:
        """Get symbols with high whale sell pressure (good for shorts)"""
        low_pressure = [
            (s, a) for s, a in self.activity.items()
            if a.whale_pressure_score <= max_pressure
        ]
        return sorted(low_pressure, key=lambda x: x[1].whale_pressure_score)
    
    def get_recent_whale_orders(self, limit: int = 50) -> List[LargeOrder]:
        """Get most recent whale orders across all symbols"""
        all_orders = []
        for orders in self.order_history.values():
            all_orders.extend(orders)
        
        all_orders.sort(key=lambda x: x.timestamp, reverse=True)
        return all_orders[:limit]

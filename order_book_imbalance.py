"""
MEXC Pump Monitor - Order Book Imbalance Analyzer
Analyzes bid/ask walls and market pressure
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger("OrderBookImbalance")


class PressureDirection(Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class OrderBookLevel:
    """Single price level in order book"""
    price: float
    quantity: float
    side: str  # 'bid' or 'ask'
    
    @property
    def value_usd(self) -> float:
        return self.price * self.quantity


@dataclass
class WallDetection:
    """Detected order book wall"""
    price: float
    size_usd: float
    side: str
    strength: float  # 0-100
    distance_pct: float  # Distance from current price


@dataclass
class ImbalanceResult:
    """Order book imbalance analysis result"""
    symbol: str
    timestamp: datetime
    bid_volume: float
    ask_volume: float
    imbalance_ratio: float  # >1 = more bids, <1 = more asks
    pressure: PressureDirection
    bid_walls: List[WallDetection]
    ask_walls: List[WallDetection]
    spread_pct: float
    depth_score: int  # 0-100


class OrderBookImbalance:
    """
    Order Book Imbalance Analyzer
    - Detects bid/ask walls
    - Calculates buying/selling pressure
    - Identifies support/resistance from liquidity
    """
    
    def __init__(self, wall_threshold_usd: float = 50000, depth_levels: int = 20):
        self.wall_threshold = wall_threshold_usd
        self.depth_levels = depth_levels
        self.history: Dict[str, deque] = {}  # symbol -> recent imbalances
        self.max_history = 100
        
        logger.info(f"📊 Order Book Imbalance initialized: wall threshold ${wall_threshold_usd:,.0f}")
    
    def analyze(self, symbol: str, bids: List[Tuple[float, float]], 
                asks: List[Tuple[float, float]], current_price: float) -> ImbalanceResult:
        """
        Analyze order book for imbalance
        
        Args:
            symbol: Trading pair
            bids: List of (price, quantity) tuples
            asks: List of (price, quantity) tuples
            current_price: Current market price
        """
        # Convert to OrderBookLevel objects
        bid_levels = [OrderBookLevel(p, q, 'bid') for p, q in bids[:self.depth_levels]]
        ask_levels = [OrderBookLevel(p, q, 'ask') for p, q in asks[:self.depth_levels]]
        
        # Calculate volumes
        bid_volume = sum(l.value_usd for l in bid_levels)
        ask_volume = sum(l.value_usd for l in ask_levels)
        
        # Imbalance ratio
        imbalance_ratio = bid_volume / ask_volume if ask_volume > 0 else float('inf')
        
        # Determine pressure direction
        pressure = self._calculate_pressure(imbalance_ratio)
        
        # Detect walls
        bid_walls = self._detect_walls(bid_levels, current_price, 'bid')
        ask_walls = self._detect_walls(ask_levels, current_price, 'ask')
        
        # Calculate spread
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        spread_pct = ((best_ask - best_bid) / current_price * 100) if current_price > 0 else 0
        
        # Depth score (liquidity health)
        depth_score = self._calculate_depth_score(bid_volume, ask_volume, spread_pct)
        
        result = ImbalanceResult(
            symbol=symbol,
            timestamp=datetime.now(),
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            imbalance_ratio=imbalance_ratio,
            pressure=pressure,
            bid_walls=bid_walls,
            ask_walls=ask_walls,
            spread_pct=spread_pct,
            depth_score=depth_score
        )
        
        # Store in history
        if symbol not in self.history:
            self.history[symbol] = deque(maxlen=self.max_history)
        self.history[symbol].append(result)
        
        return result
    
    def _calculate_pressure(self, ratio: float) -> PressureDirection:
        """Convert imbalance ratio to pressure direction"""
        if ratio >= 2.0:
            return PressureDirection.STRONG_BUY
        elif ratio >= 1.3:
            return PressureDirection.BUY
        elif ratio <= 0.5:
            return PressureDirection.STRONG_SELL
        elif ratio <= 0.77:
            return PressureDirection.SELL
        else:
            return PressureDirection.NEUTRAL
    
    def _detect_walls(self, levels: List[OrderBookLevel], current_price: float, 
                     side: str) -> List[WallDetection]:
        """Detect significant walls in order book"""
        walls = []
        
        for level in levels:
            if level.value_usd >= self.wall_threshold:
                distance_pct = abs(level.price - current_price) / current_price * 100
                strength = min(100, int(level.value_usd / self.wall_threshold * 50))
                
                walls.append(WallDetection(
                    price=level.price,
                    size_usd=level.value_usd,
                    side=side,
                    strength=strength,
                    distance_pct=distance_pct
                ))
        
        # Sort by size descending
        walls.sort(key=lambda w: w.size_usd, reverse=True)
        return walls[:5]  # Top 5 walls
    
    def _calculate_depth_score(self, bid_vol: float, ask_vol: float, spread: float) -> int:
        """Calculate overall liquidity/depth health score"""
        total_liquidity = bid_vol + ask_vol
        
        # Base score from liquidity
        if total_liquidity >= 1_000_000:
            score = 90
        elif total_liquidity >= 500_000:
            score = 70
        elif total_liquidity >= 100_000:
            score = 50
        elif total_liquidity >= 50_000:
            score = 30
        else:
            score = 10
        
        # Penalize wide spreads
        if spread > 0.5:
            score -= 20
        elif spread > 0.2:
            score -= 10
        
        # Penalize extreme imbalance
        ratio = bid_vol / ask_vol if ask_vol > 0 else 1
        if ratio > 3 or ratio < 0.33:
            score -= 15
        
        return max(0, min(100, score))
    
    def get_support_resistance(self, symbol: str) -> Dict[str, List[float]]:
        """Get support/resistance levels from wall history"""
        if symbol not in self.history:
            return {"support": [], "resistance": []}
        
        supports = []
        resistances = []
        
        for result in list(self.history[symbol])[-10:]:  # Last 10 snapshots
            for wall in result.bid_walls:
                if wall.strength >= 50:
                    supports.append(wall.price)
            for wall in result.ask_walls:
                if wall.strength >= 50:
                    resistances.append(wall.price)
        
        # Return unique sorted levels
        return {
            "support": sorted(set(supports), reverse=True)[:3],
            "resistance": sorted(set(resistances))[:3]
        }
    
    def get_pressure_trend(self, symbol: str, periods: int = 10) -> Optional[str]:
        """Analyze recent pressure trend"""
        if symbol not in self.history:
            return None
        
        recent = list(self.history[symbol])[-periods:]
        if len(recent) < 3:
            return None
        
        buy_count = sum(1 for r in recent if r.pressure in 
                       [PressureDirection.BUY, PressureDirection.STRONG_BUY])
        sell_count = sum(1 for r in recent if r.pressure in 
                        [PressureDirection.SELL, PressureDirection.STRONG_SELL])
        
        if buy_count >= periods * 0.7:
            return "BULLISH_ACCUMULATION"
        elif sell_count >= periods * 0.7:
            return "BEARISH_DISTRIBUTION"
        else:
            return "MIXED"


# Convenience instance
order_book_analyzer = OrderBookImbalance()

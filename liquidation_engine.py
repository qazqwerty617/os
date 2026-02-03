"""
MEXC Pump Monitor - Liquidation Cascade Prediction
Predicts potential liquidation cascades and their impact
"""

import asyncio
import time
import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

logger = logging.getLogger(__name__)


class LiquidationRisk(Enum):
    """Liquidation risk levels"""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    EXTREME = "EXTREME"
    CASCADE_IMMINENT = "CASCADE_IMMINENT"


@dataclass
class LiquidationLevel:
    """Price level with concentrated liquidations"""
    price: float
    estimated_volume_usd: float
    side: str  # 'LONG' or 'SHORT'
    leverage_avg: float
    distance_pct: float  # Distance from current price
    
    @property
    def is_long(self) -> bool:
        return self.side == 'LONG'


@dataclass
class CascadeZone:
    """Predicted cascade zone"""
    symbol: str
    trigger_price: float
    liquidation_levels: List[LiquidationLevel]
    total_volume_usd: float
    cascade_depth: int  # Number of levels that would trigger
    estimated_price_impact_pct: float
    risk_level: LiquidationRisk
    direction: str  # 'UP' or 'DOWN'


@dataclass
class LiquidationHeatmap:
    """Liquidation heatmap for a symbol"""
    symbol: str
    current_price: float
    timestamp: int
    
    # Levels above current price (short liquidations)
    short_liquidations: List[LiquidationLevel] = field(default_factory=list)
    
    # Levels below current price (long liquidations)
    long_liquidations: List[LiquidationLevel] = field(default_factory=list)
    
    # Total volumes
    total_short_liq_volume: float = 0
    total_long_liq_volume: float = 0
    
    # Risk assessment
    upside_cascade_risk: LiquidationRisk = LiquidationRisk.LOW
    downside_cascade_risk: LiquidationRisk = LiquidationRisk.LOW


@dataclass
class RecentLiquidation:
    """Recent liquidation event"""
    symbol: str
    timestamp: int
    side: str
    price: float
    quantity: float
    value_usd: float


class LiquidationPredictor:
    """
    Predicts liquidation cascades and their market impact
    Uses open interest, leverage estimates, and price levels
    """
    
    # Common leverage levels on MEXC
    LEVERAGE_LEVELS = [2, 3, 5, 10, 20, 25, 50, 75, 100, 125]
    
    # Liquidation threshold (maintenance margin)
    MAINTENANCE_MARGIN = 0.004  # 0.4% - typical for MEXC futures
    
    def __init__(self):
        # Heatmaps per symbol
        self.heatmaps: Dict[str, LiquidationHeatmap] = {}
        
        # Cascade zones
        self.cascade_zones: Dict[str, List[CascadeZone]] = defaultdict(list)
        
        # Recent liquidations
        self.recent_liquidations: Dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        
        # Liquidation velocity tracking
        self.liq_velocity: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
        
        # Statistics
        self.stats = {
            'cascades_predicted': 0,
            'cascades_triggered': 0,
            'total_liq_volume_usd': 0
        }
    
    def estimate_liquidation_levels(
        self,
        symbol: str,
        current_price: float,
        open_interest_usd: float,
        recent_funding_rate: float = 0
    ) -> LiquidationHeatmap:
        """
        Estimate liquidation levels based on open interest and leverage distribution
        
        Args:
            symbol: Trading pair
            current_price: Current price
            open_interest_usd: Total open interest in USD
            recent_funding_rate: Recent funding rate (affects long/short ratio)
        
        Returns:
            LiquidationHeatmap with estimated levels
        """
        heatmap = LiquidationHeatmap(
            symbol=symbol,
            current_price=current_price,
            timestamp=int(time.time() * 1000)
        )
        
        # Estimate long/short ratio from funding rate
        # Positive funding = more longs, negative = more shorts
        if recent_funding_rate > 0:
            long_ratio = 0.55 + min(0.2, recent_funding_rate * 10)
        elif recent_funding_rate < 0:
            long_ratio = 0.45 - min(0.2, abs(recent_funding_rate) * 10)
        else:
            long_ratio = 0.5
        
        short_ratio = 1 - long_ratio
        
        long_oi = open_interest_usd * long_ratio
        short_oi = open_interest_usd * short_ratio
        
        # Estimate leverage distribution (assumed)
        # Most retail uses 5-20x, some use higher
        leverage_distribution = {
            5: 0.10,
            10: 0.25,
            20: 0.30,
            25: 0.15,
            50: 0.12,
            75: 0.05,
            100: 0.03,
        }
        
        # Calculate liquidation levels for longs (below current price)
        for leverage, ratio in leverage_distribution.items():
            # Liquidation price for longs: entry * (1 - 1/leverage + maintenance)
            liq_distance_pct = (1 / leverage - self.MAINTENANCE_MARGIN) * 100
            liq_price = current_price * (1 - liq_distance_pct / 100)
            
            volume_at_level = long_oi * ratio
            
            if volume_at_level > 10000:  # Min $10k
                level = LiquidationLevel(
                    price=liq_price,
                    estimated_volume_usd=volume_at_level,
                    side='LONG',
                    leverage_avg=leverage,
                    distance_pct=liq_distance_pct
                )
                heatmap.long_liquidations.append(level)
                heatmap.total_long_liq_volume += volume_at_level
        
        # Calculate liquidation levels for shorts (above current price)
        for leverage, ratio in leverage_distribution.items():
            # Liquidation price for shorts: entry * (1 + 1/leverage - maintenance)
            liq_distance_pct = (1 / leverage - self.MAINTENANCE_MARGIN) * 100
            liq_price = current_price * (1 + liq_distance_pct / 100)
            
            volume_at_level = short_oi * ratio
            
            if volume_at_level > 10000:
                level = LiquidationLevel(
                    price=liq_price,
                    estimated_volume_usd=volume_at_level,
                    side='SHORT',
                    leverage_avg=leverage,
                    distance_pct=liq_distance_pct
                )
                heatmap.short_liquidations.append(level)
                heatmap.total_short_liq_volume += volume_at_level
        
        # Sort by distance
        heatmap.long_liquidations.sort(key=lambda x: x.distance_pct)
        heatmap.short_liquidations.sort(key=lambda x: x.distance_pct)
        
        # Assess cascade risk
        heatmap.downside_cascade_risk = self._assess_cascade_risk(
            heatmap.long_liquidations, 
            current_price,
            direction='DOWN'
        )
        heatmap.upside_cascade_risk = self._assess_cascade_risk(
            heatmap.short_liquidations,
            current_price,
            direction='UP'
        )
        
        self.heatmaps[symbol] = heatmap
        return heatmap
    
    def _assess_cascade_risk(
        self,
        levels: List[LiquidationLevel],
        current_price: float,
        direction: str
    ) -> LiquidationRisk:
        """Assess cascade risk based on level concentration"""
        if not levels:
            return LiquidationRisk.LOW
        
        # Check concentration near current price
        near_levels = [l for l in levels if l.distance_pct < 5]  # Within 5%
        near_volume = sum(l.estimated_volume_usd for l in near_levels)
        
        mid_levels = [l for l in levels if 5 <= l.distance_pct < 10]
        mid_volume = sum(l.estimated_volume_usd for l in mid_levels)
        
        # High concentration near price = high risk
        if near_volume > 1_000_000 and len(near_levels) >= 2:
            return LiquidationRisk.CASCADE_IMMINENT
        elif near_volume > 500_000:
            return LiquidationRisk.EXTREME
        elif near_volume > 200_000 or mid_volume > 500_000:
            return LiquidationRisk.HIGH
        elif near_volume > 50_000 or mid_volume > 200_000:
            return LiquidationRisk.MODERATE
        else:
            return LiquidationRisk.LOW
    
    def predict_cascade_zones(
        self,
        symbol: str,
        current_price: float
    ) -> List[CascadeZone]:
        """
        Predict potential cascade zones
        
        Args:
            symbol: Trading pair
            current_price: Current price
        
        Returns:
            List of predicted cascade zones
        """
        heatmap = self.heatmaps.get(symbol)
        if not heatmap:
            return []
        
        zones = []
        
        # Downside cascade (long liquidations)
        if heatmap.long_liquidations:
            downside_zone = self._build_cascade_zone(
                symbol,
                heatmap.long_liquidations,
                current_price,
                direction='DOWN'
            )
            if downside_zone:
                zones.append(downside_zone)
        
        # Upside cascade (short liquidations)
        if heatmap.short_liquidations:
            upside_zone = self._build_cascade_zone(
                symbol,
                heatmap.short_liquidations,
                current_price,
                direction='UP'
            )
            if upside_zone:
                zones.append(upside_zone)
        
        self.cascade_zones[symbol] = zones
        return zones
    
    def _build_cascade_zone(
        self,
        symbol: str,
        levels: List[LiquidationLevel],
        current_price: float,
        direction: str
    ) -> Optional[CascadeZone]:
        """Build a cascade zone from liquidation levels"""
        if not levels:
            return None
        
        # Find trigger price (first significant level)
        significant_levels = [l for l in levels if l.estimated_volume_usd > 50000]
        
        if not significant_levels:
            return None
        
        trigger_level = significant_levels[0]
        trigger_price = trigger_level.price
        
        # Calculate cascade depth (how many levels are close together)
        cascade_levels = []
        prev_price = trigger_price
        
        for level in significant_levels:
            price_gap = abs(level.price - prev_price) / prev_price * 100
            if price_gap < 2:  # Within 2% of each other
                cascade_levels.append(level)
                prev_price = level.price
            else:
                break
        
        if len(cascade_levels) < 2:
            return None
        
        total_volume = sum(l.estimated_volume_usd for l in cascade_levels)
        
        # Estimate price impact
        # Rough formula: impact = sqrt(volume / 10M) * 5%
        price_impact = math.sqrt(total_volume / 10_000_000) * 5
        price_impact = min(price_impact, 30)  # Cap at 30%
        
        # Assess risk
        if total_volume > 5_000_000:
            risk = LiquidationRisk.CASCADE_IMMINENT
        elif total_volume > 1_000_000:
            risk = LiquidationRisk.EXTREME
        elif total_volume > 500_000:
            risk = LiquidationRisk.HIGH
        else:
            risk = LiquidationRisk.MODERATE
        
        return CascadeZone(
            symbol=symbol,
            trigger_price=trigger_price,
            liquidation_levels=cascade_levels,
            total_volume_usd=total_volume,
            cascade_depth=len(cascade_levels),
            estimated_price_impact_pct=price_impact,
            risk_level=risk,
            direction=direction
        )
    
    def record_liquidation(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        timestamp: int = None
    ):
        """Record a liquidation event"""
        timestamp = timestamp or int(time.time() * 1000)
        value_usd = price * quantity
        
        liq = RecentLiquidation(
            symbol=symbol,
            timestamp=timestamp,
            side=side,
            price=price,
            quantity=quantity,
            value_usd=value_usd
        )
        
        self.recent_liquidations[symbol].append(liq)
        self.stats['total_liq_volume_usd'] += value_usd
        
        # Track velocity
        self.liq_velocity[symbol].append((timestamp, value_usd))
        
        # Cleanup old velocity data (keep last hour)
        cutoff = timestamp - 3600000
        self.liq_velocity[symbol] = [
            (t, v) for t, v in self.liq_velocity[symbol] if t > cutoff
        ]
    
    def get_liquidation_velocity(self, symbol: str, window_minutes: int = 5) -> float:
        """
        Get liquidation velocity (USD per minute) for recent window
        """
        if symbol not in self.liq_velocity:
            return 0
        
        now = int(time.time() * 1000)
        cutoff = now - (window_minutes * 60 * 1000)
        
        recent = [v for t, v in self.liq_velocity[symbol] if t > cutoff]
        
        if not recent:
            return 0
        
        return sum(recent) / window_minutes
    
    def is_cascade_active(self, symbol: str) -> bool:
        """Check if liquidation cascade is currently active"""
        velocity = self.get_liquidation_velocity(symbol, 1)  # Last minute
        return velocity > 100_000  # > $100k/min = cascade active
    
    def get_cascade_targets(self, current_price: float, direction: str, symbol: str) -> List[float]:
        """
        Get predicted cascade target prices
        
        Args:
            current_price: Current price
            direction: 'UP' or 'DOWN'
            symbol: Trading pair
        
        Returns:
            List of target prices during cascade
        """
        zones = self.cascade_zones.get(symbol, [])
        
        for zone in zones:
            if zone.direction == direction:
                targets = [level.price for level in zone.liquidation_levels]
                # Add final target based on estimated impact
                if direction == 'DOWN':
                    final_target = current_price * (1 - zone.estimated_price_impact_pct / 100)
                else:
                    final_target = current_price * (1 + zone.estimated_price_impact_pct / 100)
                targets.append(final_target)
                return sorted(targets, reverse=(direction == 'DOWN'))
        
        return []
    
    def get_highest_risk_symbols(self, limit: int = 20) -> List[Tuple[str, LiquidationRisk, float]]:
        """
        Get symbols with highest liquidation cascade risk
        
        Returns:
            List of (symbol, risk_level, total_near_liq_volume)
        """
        risks = []
        
        for symbol, heatmap in self.heatmaps.items():
            # Get highest risk between upside and downside
            max_risk = max(
                heatmap.upside_cascade_risk.value,
                heatmap.downside_cascade_risk.value,
                key=lambda x: ['LOW', 'MODERATE', 'HIGH', 'EXTREME', 'CASCADE_IMMINENT'].index(x)
            )
            
            near_volume = sum(
                l.estimated_volume_usd 
                for l in heatmap.long_liquidations + heatmap.short_liquidations
                if l.distance_pct < 5
            )
            
            risks.append((symbol, max_risk, near_volume))
        
        # Sort by risk level and volume
        risk_order = ['CASCADE_IMMINENT', 'EXTREME', 'HIGH', 'MODERATE', 'LOW']
        risks.sort(key=lambda x: (risk_order.index(x[1]) if x[1] in risk_order else 99, -x[2]))
        
        return risks[:limit]

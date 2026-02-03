"""
MEXC Pump Monitor - Liquidation Heatmap Generator
Visual representation of liquidation levels and clusters
"""

import time
import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class LiquidationSide(Enum):
    """Liquidation side"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class LiquidationLevel:
    """Single liquidation price level"""
    price: float
    side: LiquidationSide
    volume_usd: float
    leverage: int
    count: int = 1  # Number of positions
    
    # Intensity (for heatmap)
    intensity: float = 0
    
    def to_dict(self) -> Dict:
        return {
            'price': self.price,
            'side': self.side.value,
            'volume_usd': self.volume_usd,
            'leverage': leverage if (leverage := self.leverage) else 0,
            'count': self.count,
            'intensity': self.intensity
        }


@dataclass
class LiquidationCluster:
    """Cluster of liquidations at similar price levels"""
    price_low: float
    price_high: float
    center_price: float
    side: LiquidationSide
    
    # Aggregated data
    total_volume: float = 0
    total_count: int = 0
    avg_leverage: float = 0
    
    # Cluster importance
    importance: float = 0  # 0-100
    
    def to_dict(self) -> Dict:
        return {
            'price_range': [self.price_low, self.price_high],
            'center_price': self.center_price,
            'side': self.side.value,
            'total_volume': self.total_volume,
            'total_count': self.total_count,
            'avg_leverage': self.avg_leverage,
            'importance': self.importance
        }


@dataclass
class LiquidationHeatmap:
    """Complete heatmap for a symbol"""
    symbol: str
    current_price: float
    timestamp: int
    
    # Levels
    long_levels: List[LiquidationLevel] = field(default_factory=list)
    short_levels: List[LiquidationLevel] = field(default_factory=list)
    
    # Clusters
    long_clusters: List[LiquidationCluster] = field(default_factory=list)
    short_clusters: List[LiquidationCluster] = field(default_factory=list)
    
    # Key levels
    major_long_liq: Optional[float] = None  # Biggest long liq level below
    major_short_liq: Optional[float] = None  # Biggest short liq level above
    
    # Imbalance
    long_volume_below: float = 0  # Long liqs waiting below price
    short_volume_above: float = 0  # Short liqs waiting above price
    imbalance_ratio: float = 1.0  # >1 = more longs to liquidate
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'timestamp': self.timestamp,
            'long_levels': [l.to_dict() for l in self.long_levels],
            'short_levels': [l.to_dict() for l in self.short_levels],
            'long_clusters': [c.to_dict() for c in self.long_clusters],
            'short_clusters': [c.to_dict() for c in self.short_clusters],
            'major_long_liq': self.major_long_liq,
            'major_short_liq': self.major_short_liq,
            'imbalance_ratio': self.imbalance_ratio
        }


class LiquidationHeatmapGenerator:
    """
    Generates liquidation heatmaps based on estimated positions
    Uses open interest, funding rates, and leverage data
    """
    
    # Common leverage levels
    LEVERAGE_LEVELS = [2, 3, 5, 10, 20, 25, 50, 75, 100, 125]
    
    # Leverage distribution (estimated percentage at each level)
    LEVERAGE_DISTRIBUTION = {
        2: 0.05,
        3: 0.05,
        5: 0.10,
        10: 0.20,
        20: 0.25,
        25: 0.15,
        50: 0.10,
        75: 0.05,
        100: 0.03,
        125: 0.02
    }
    
    def __init__(self, num_levels: int = 50):
        self.num_levels = num_levels
        
        # Cached heatmaps
        self.heatmaps: Dict[str, LiquidationHeatmap] = {}
        
        # Open interest data (injected)
        self.open_interest: Dict[str, float] = {}
        
        # Stats
        self.stats = {
            'heatmaps_generated': 0,
            'clusters_found': 0
        }
    
    def set_open_interest(self, symbol: str, oi_usd: float):
        """Set open interest for a symbol"""
        self.open_interest[symbol] = oi_usd
    
    def generate_heatmap(
        self,
        symbol: str,
        current_price: float,
        price_range_pct: float = 20  # Generate levels within ±20%
    ) -> LiquidationHeatmap:
        """
        Generate liquidation heatmap for symbol
        
        Args:
            symbol: Trading pair
            current_price: Current market price
            price_range_pct: Range around current price to analyze
        """
        oi_usd = self.open_interest.get(symbol, 0)
        
        if oi_usd == 0:
            # Estimate OI if not available
            oi_usd = current_price * 100000  # Rough estimate
        
        # Calculate price range
        price_low = current_price * (1 - price_range_pct / 100)
        price_high = current_price * (1 + price_range_pct / 100)
        
        long_levels = []
        short_levels = []
        
        # Generate liquidation levels for each leverage
        for leverage, pct in self.LEVERAGE_DISTRIBUTION.items():
            oi_at_leverage = oi_usd * pct
            
            # Split into longs and shorts (assume 50/50 for estimation)
            long_oi = oi_at_leverage * 0.5
            short_oi = oi_at_leverage * 0.5
            
            # Long liquidation price = entry * (1 - 1/leverage)
            # Assuming entries are distributed around current price
            for entry_offset in [-0.05, -0.02, 0, 0.02, 0.05]:
                entry_price = current_price * (1 + entry_offset)
                liq_price = entry_price * (1 - 0.9 / leverage)  # 90% of maintenance
                
                if price_low < liq_price < current_price:
                    level = LiquidationLevel(
                        price=liq_price,
                        side=LiquidationSide.LONG,
                        volume_usd=long_oi / 5,  # Distribute across entries
                        leverage=leverage
                    )
                    long_levels.append(level)
            
            # Short liquidation price = entry * (1 + 1/leverage)
            for entry_offset in [-0.05, -0.02, 0, 0.02, 0.05]:
                entry_price = current_price * (1 + entry_offset)
                liq_price = entry_price * (1 + 0.9 / leverage)
                
                if current_price < liq_price < price_high:
                    level = LiquidationLevel(
                        price=liq_price,
                        side=LiquidationSide.SHORT,
                        volume_usd=short_oi / 5,
                        leverage=leverage
                    )
                    short_levels.append(level)
        
        # Calculate intensity for heatmap coloring
        if long_levels:
            max_long_vol = max(l.volume_usd for l in long_levels)
            for level in long_levels:
                level.intensity = level.volume_usd / max_long_vol if max_long_vol > 0 else 0
        
        if short_levels:
            max_short_vol = max(l.volume_usd for l in short_levels)
            for level in short_levels:
                level.intensity = level.volume_usd / max_short_vol if max_short_vol > 0 else 0
        
        # Find clusters
        long_clusters = self._find_clusters(long_levels, LiquidationSide.LONG)
        short_clusters = self._find_clusters(short_levels, LiquidationSide.SHORT)
        
        # Calculate imbalance
        long_volume_below = sum(l.volume_usd for l in long_levels)
        short_volume_above = sum(l.volume_usd for l in short_levels)
        
        imbalance = long_volume_below / short_volume_above if short_volume_above > 0 else 2.0
        
        # Find major levels
        major_long = max(long_levels, key=lambda l: l.volume_usd).price if long_levels else None
        major_short = max(short_levels, key=lambda l: l.volume_usd).price if short_levels else None
        
        heatmap = LiquidationHeatmap(
            symbol=symbol,
            current_price=current_price,
            timestamp=int(time.time() * 1000),
            long_levels=sorted(long_levels, key=lambda l: l.price, reverse=True),
            short_levels=sorted(short_levels, key=lambda l: l.price),
            long_clusters=long_clusters,
            short_clusters=short_clusters,
            major_long_liq=major_long,
            major_short_liq=major_short,
            long_volume_below=long_volume_below,
            short_volume_above=short_volume_above,
            imbalance_ratio=imbalance
        )
        
        self.heatmaps[symbol] = heatmap
        self.stats['heatmaps_generated'] += 1
        self.stats['clusters_found'] += len(long_clusters) + len(short_clusters)
        
        return heatmap
    
    def _find_clusters(
        self,
        levels: List[LiquidationLevel],
        side: LiquidationSide,
        cluster_range_pct: float = 2  # Group levels within 2%
    ) -> List[LiquidationCluster]:
        """Find liquidation clusters"""
        if not levels:
            return []
        
        # Sort by price
        sorted_levels = sorted(levels, key=lambda l: l.price)
        
        clusters = []
        current_cluster_levels = [sorted_levels[0]]
        
        for level in sorted_levels[1:]:
            # Check if level is close to cluster
            cluster_center = sum(l.price for l in current_cluster_levels) / len(current_cluster_levels)
            distance_pct = abs(level.price - cluster_center) / cluster_center * 100
            
            if distance_pct <= cluster_range_pct:
                current_cluster_levels.append(level)
            else:
                # Save current cluster
                if len(current_cluster_levels) >= 2:
                    clusters.append(self._create_cluster(current_cluster_levels, side))
                
                current_cluster_levels = [level]
        
        # Don't forget last cluster
        if len(current_cluster_levels) >= 2:
            clusters.append(self._create_cluster(current_cluster_levels, side))
        
        return clusters
    
    def _create_cluster(
        self,
        levels: List[LiquidationLevel],
        side: LiquidationSide
    ) -> LiquidationCluster:
        """Create cluster from levels"""
        prices = [l.price for l in levels]
        volumes = [l.volume_usd for l in levels]
        leverages = [l.leverage for l in levels]
        
        total_volume = sum(volumes)
        total_count = sum(l.count for l in levels)
        
        cluster = LiquidationCluster(
            price_low=min(prices),
            price_high=max(prices),
            center_price=sum(prices) / len(prices),
            side=side,
            total_volume=total_volume,
            total_count=total_count,
            avg_leverage=sum(leverages) / len(leverages)
        )
        
        # Calculate importance (0-100)
        # Based on volume and level count
        cluster.importance = min(100, (total_volume / 1000000) * 10 + total_count * 5)
        
        return cluster
    
    def get_nearest_liquidation(
        self,
        symbol: str,
        current_price: float
    ) -> Dict:
        """Get nearest liquidation levels on both sides"""
        heatmap = self.heatmaps.get(symbol)
        
        if not heatmap:
            return {'long': None, 'short': None}
        
        # Nearest long liquidation (below price)
        long_below = [l for l in heatmap.long_levels if l.price < current_price]
        nearest_long = max(long_below, key=lambda l: l.price) if long_below else None
        
        # Nearest short liquidation (above price)
        short_above = [l for l in heatmap.short_levels if l.price > current_price]
        nearest_short = min(short_above, key=lambda l: l.price) if short_above else None
        
        return {
            'long': nearest_long.to_dict() if nearest_long else None,
            'short': nearest_short.to_dict() if nearest_short else None,
            'distance_to_long_pct': ((current_price - nearest_long.price) / current_price * 100) if nearest_long else None,
            'distance_to_short_pct': ((nearest_short.price - current_price) / current_price * 100) if nearest_short else None
        }
    
    def get_cascade_risk(self, symbol: str, direction: str = 'DOWN') -> Dict:
        """
        Assess cascade liquidation risk
        
        Direction: 'DOWN' for long cascades, 'UP' for short cascades
        """
        heatmap = self.heatmaps.get(symbol)
        
        if not heatmap:
            return {'risk': 'UNKNOWN', 'cascade_volume': 0}
        
        if direction == 'DOWN':
            # Risk of long cascade (price drops)
            levels = heatmap.long_levels
            clusters = heatmap.long_clusters
        else:
            # Risk of short cascade (price rises)
            levels = heatmap.short_levels
            clusters = heatmap.short_clusters
        
        if not clusters:
            return {'risk': 'LOW', 'cascade_volume': 0}
        
        # Total volume in clusters
        cluster_volume = sum(c.total_volume for c in clusters)
        
        # Risk assessment
        if cluster_volume > 10000000:  # $10M+
            risk = 'EXTREME'
        elif cluster_volume > 5000000:  # $5M+
            risk = 'HIGH'
        elif cluster_volume > 1000000:  # $1M+
            risk = 'MEDIUM'
        else:
            risk = 'LOW'
        
        return {
            'risk': risk,
            'cascade_volume': cluster_volume,
            'cluster_count': len(clusters),
            'closest_cluster': clusters[0].to_dict() if clusters else None
        }
    
    def generate_ascii_heatmap(self, symbol: str, width: int = 50) -> str:
        """Generate ASCII representation of heatmap"""
        heatmap = self.heatmaps.get(symbol)
        
        if not heatmap:
            return "No heatmap data"
        
        lines = []
        lines.append(f"📊 Liquidation Heatmap: {symbol}")
        lines.append(f"Current Price: ${heatmap.current_price:.8f}")
        lines.append("=" * width)
        
        # Short levels (above)
        for level in heatmap.short_levels[:5]:
            bar_len = int(level.intensity * (width - 20))
            bar = "█" * bar_len
            lines.append(f"${level.price:.6f} |{bar}| SHORT {level.leverage}x")
        
        lines.append("-" * width)
        lines.append(f">>> CURRENT: ${heatmap.current_price:.6f} <<<")
        lines.append("-" * width)
        
        # Long levels (below)
        for level in heatmap.long_levels[:5]:
            bar_len = int(level.intensity * (width - 20))
            bar = "█" * bar_len
            lines.append(f"${level.price:.6f} |{bar}| LONG {level.leverage}x")
        
        lines.append("=" * width)
        lines.append(f"Imbalance: {heatmap.imbalance_ratio:.2f}x ({'More LONGS' if heatmap.imbalance_ratio > 1 else 'More SHORTS'})")
        
        return "\n".join(lines)

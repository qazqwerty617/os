"""
MEXC Pump Monitor - Volume Profile Analysis
Real volume clustering and price level significance
Based on actual traded volume, not estimates
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class VolumeCluster:
    """A price zone with significant volume"""
    price_low: float
    price_high: float
    price_poc: float  # Point of Control (highest volume price)
    total_volume: float
    buy_volume: float
    sell_volume: float
    trade_count: int
    avg_trade_size: float
    
    # Calculated metrics
    delta: float = 0  # Buy - Sell volume
    delta_pct: float = 0  # Delta as percentage
    imbalance: str = "NEUTRAL"  # BUY, SELL, or NEUTRAL
    
    def calculate_metrics(self):
        """Calculate derived metrics"""
        self.delta = self.buy_volume - self.sell_volume
        if self.total_volume > 0:
            self.delta_pct = (self.delta / self.total_volume) * 100
        
        if self.delta_pct > 10:
            self.imbalance = "BUY"
        elif self.delta_pct < -10:
            self.imbalance = "SELL"
        else:
            self.imbalance = "NEUTRAL"


@dataclass
class VolumeProfile:
    """Complete volume profile for a symbol"""
    symbol: str
    timestamp: int
    period_minutes: int
    
    # Price range
    high: float = 0
    low: float = 0
    current_price: float = 0
    
    # Key levels - based on REAL traded data
    poc: float = 0  # Point of Control - price with most volume
    vah: float = 0  # Value Area High (70% of volume above this)
    val: float = 0  # Value Area Low (70% of volume below this)
    
    # Volume clusters (actual data)
    clusters: List[VolumeCluster] = field(default_factory=list)
    
    # Total volume
    total_volume: float = 0
    total_buy_volume: float = 0
    total_sell_volume: float = 0
    
    # Profile shape
    profile_shape: str = "NORMAL"  # NORMAL, P-SHAPE, B-SHAPE, D-SHAPE
    
    # Key support/resistance based on volume
    volume_supports: List[float] = field(default_factory=list)
    volume_resistances: List[float] = field(default_factory=list)


@dataclass
class Trade:
    """Single trade record"""
    timestamp: int
    price: float
    quantity: float
    side: str  # 'BUY' or 'SELL'
    value_usd: float


class VolumeProfiler:
    """
    Real volume profile analysis
    Uses actual trade data to build accurate profiles
    NO ESTIMATION - only real traded volume
    """
    
    def __init__(self, num_clusters: int = 24):
        self.num_clusters = num_clusters
        
        # Store actual trades per symbol
        self.trades: Dict[str, List[Trade]] = defaultdict(list)
        
        # Built profiles
        self.profiles: Dict[str, VolumeProfile] = {}
        
        # Max trades to keep per symbol
        self.max_trades = 50000
    
    def record_trade(
        self,
        symbol: str,
        price: float,
        quantity: float,
        side: str,
        timestamp: int = None
    ):
        """
        Record an actual trade
        
        Args:
            symbol: Trading pair
            price: Trade price
            quantity: Trade quantity  
            side: 'BUY' or 'SELL'
            timestamp: Trade timestamp (ms)
        """
        timestamp = timestamp or int(time.time() * 1000)
        
        trade = Trade(
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            side=side.upper(),
            value_usd=price * quantity
        )
        
        self.trades[symbol].append(trade)
        
        # Limit memory usage
        if len(self.trades[symbol]) > self.max_trades:
            self.trades[symbol] = self.trades[symbol][-self.max_trades:]
    
    def build_profile(
        self,
        symbol: str,
        period_minutes: int = 60
    ) -> Optional[VolumeProfile]:
        """
        Build volume profile from REAL trade data
        
        Args:
            symbol: Trading pair
            period_minutes: Lookback period
        
        Returns:
            VolumeProfile built from actual trades
        """
        trades = self.trades.get(symbol, [])
        
        if len(trades) < 10:
            return None
        
        now = int(time.time() * 1000)
        cutoff = now - (period_minutes * 60 * 1000)
        
        # Filter trades within period
        period_trades = [t for t in trades if t.timestamp >= cutoff]
        
        if len(period_trades) < 10:
            return None
        
        # Get price range from actual trades
        prices = [t.price for t in period_trades]
        high = max(prices)
        low = min(prices)
        current_price = period_trades[-1].price
        
        if high == low:
            return None
        
        # Create profile
        profile = VolumeProfile(
            symbol=symbol,
            timestamp=now,
            period_minutes=period_minutes,
            high=high,
            low=low,
            current_price=current_price
        )
        
        # Build clusters from real data
        price_range = high - low
        cluster_size = price_range / self.num_clusters
        
        clusters = []
        
        for i in range(self.num_clusters):
            cluster_low = low + (i * cluster_size)
            cluster_high = low + ((i + 1) * cluster_size)
            
            # Get trades in this cluster
            cluster_trades = [
                t for t in period_trades
                if cluster_low <= t.price < cluster_high
            ]
            
            if not cluster_trades:
                continue
            
            buy_vol = sum(t.value_usd for t in cluster_trades if t.side == 'BUY')
            sell_vol = sum(t.value_usd for t in cluster_trades if t.side == 'SELL')
            total_vol = buy_vol + sell_vol
            
            # Point of control within cluster
            poc_price = statistics.median([t.price for t in cluster_trades])
            
            cluster = VolumeCluster(
                price_low=cluster_low,
                price_high=cluster_high,
                price_poc=poc_price,
                total_volume=total_vol,
                buy_volume=buy_vol,
                sell_volume=sell_vol,
                trade_count=len(cluster_trades),
                avg_trade_size=total_vol / len(cluster_trades)
            )
            cluster.calculate_metrics()
            clusters.append(cluster)
        
        if not clusters:
            return None
        
        profile.clusters = clusters
        
        # Calculate totals
        profile.total_volume = sum(c.total_volume for c in clusters)
        profile.total_buy_volume = sum(c.buy_volume for c in clusters)
        profile.total_sell_volume = sum(c.sell_volume for c in clusters)
        
        # Find POC (highest volume cluster)
        poc_cluster = max(clusters, key=lambda c: c.total_volume)
        profile.poc = poc_cluster.price_poc
        
        # Calculate Value Area (70% of volume)
        self._calculate_value_area(profile)
        
        # Find support/resistance levels
        self._find_sr_levels(profile)
        
        # Determine profile shape
        self._determine_shape(profile)
        
        self.profiles[symbol] = profile
        return profile
    
    def _calculate_value_area(self, profile: VolumeProfile):
        """Calculate Value Area High/Low (70% of volume)"""
        target_volume = profile.total_volume * 0.7
        
        # Sort clusters by volume
        sorted_clusters = sorted(
            profile.clusters,
            key=lambda c: c.total_volume,
            reverse=True
        )
        
        # Add clusters until we reach 70% of volume
        cumulative = 0
        va_clusters = []
        
        for cluster in sorted_clusters:
            va_clusters.append(cluster)
            cumulative += cluster.total_volume
            if cumulative >= target_volume:
                break
        
        if va_clusters:
            prices = []
            for c in va_clusters:
                prices.extend([c.price_low, c.price_high])
            
            profile.val = min(prices)
            profile.vah = max(prices)
    
    def _find_sr_levels(self, profile: VolumeProfile):
        """Find support/resistance levels from high volume nodes"""
        # High volume nodes are potential S/R
        avg_volume = profile.total_volume / len(profile.clusters) if profile.clusters else 0
        
        high_vol_clusters = [
            c for c in profile.clusters
            if c.total_volume > avg_volume * 1.5
        ]
        
        for cluster in high_vol_clusters:
            mid_price = (cluster.price_low + cluster.price_high) / 2
            
            if mid_price < profile.current_price:
                profile.volume_supports.append(mid_price)
            else:
                profile.volume_resistances.append(mid_price)
        
        # Sort
        profile.volume_supports.sort(reverse=True)  # Highest support first
        profile.volume_resistances.sort()  # Lowest resistance first
    
    def _determine_shape(self, profile: VolumeProfile):
        """Determine volume profile shape"""
        if len(profile.clusters) < 3:
            profile.profile_shape = "NORMAL"
            return
        
        # Divide into thirds
        third = len(profile.clusters) // 3
        
        lower_vol = sum(c.total_volume for c in profile.clusters[:third])
        middle_vol = sum(c.total_volume for c in profile.clusters[third:2*third])
        upper_vol = sum(c.total_volume for c in profile.clusters[2*third:])
        
        # P-shape: more volume at top (accumulation at high, distribution)
        if upper_vol > lower_vol * 1.5 and upper_vol > middle_vol:
            profile.profile_shape = "P-SHAPE"
        # B-shape: more volume at bottom (accumulation at low, potential reversal)
        elif lower_vol > upper_vol * 1.5 and lower_vol > middle_vol:
            profile.profile_shape = "B-SHAPE"
        # D-shape: volume concentrated in middle
        elif middle_vol > upper_vol and middle_vol > lower_vol:
            profile.profile_shape = "D-SHAPE"
        else:
            profile.profile_shape = "NORMAL"
    
    def get_delta_at_price(self, symbol: str, price: float) -> Tuple[float, str]:
        """
        Get buy/sell delta at specific price level
        
        Returns:
            (delta_pct, imbalance_type)
        """
        profile = self.profiles.get(symbol)
        if not profile:
            return 0, "UNKNOWN"
        
        for cluster in profile.clusters:
            if cluster.price_low <= price < cluster.price_high:
                return cluster.delta_pct, cluster.imbalance
        
        return 0, "UNKNOWN"
    
    def get_nearest_support(self, symbol: str, price: float) -> Optional[float]:
        """Get nearest support level below price"""
        profile = self.profiles.get(symbol)
        if not profile:
            return None
        
        supports_below = [s for s in profile.volume_supports if s < price]
        return supports_below[0] if supports_below else None
    
    def get_nearest_resistance(self, symbol: str, price: float) -> Optional[float]:
        """Get nearest resistance level above price"""
        profile = self.profiles.get(symbol)
        if not profile:
            return None
        
        resistances_above = [r for r in profile.volume_resistances if r > price]
        return resistances_above[0] if resistances_above else None
    
    def is_price_at_high_volume_node(self, symbol: str, price: float, threshold: float = 1.5) -> bool:
        """Check if price is at a high volume node"""
        profile = self.profiles.get(symbol)
        if not profile:
            return False
        
        avg_volume = profile.total_volume / len(profile.clusters) if profile.clusters else 0
        
        for cluster in profile.clusters:
            if cluster.price_low <= price < cluster.price_high:
                return cluster.total_volume > avg_volume * threshold
        
        return False
    
    def get_profile_analysis(self, symbol: str) -> Dict:
        """Get complete profile analysis"""
        profile = self.profiles.get(symbol)
        if not profile:
            return {}
        
        return {
            'symbol': symbol,
            'timeframe_min': profile.period_minutes,
            'price_range': f"{profile.low:.8f} - {profile.high:.8f}",
            'current_price': profile.current_price,
            'poc': profile.poc,
            'value_area': f"{profile.val:.8f} - {profile.vah:.8f}",
            'profile_shape': profile.profile_shape,
            'total_volume_usd': profile.total_volume,
            'buy_sell_ratio': profile.total_buy_volume / profile.total_sell_volume if profile.total_sell_volume > 0 else 0,
            'nearest_support': profile.volume_supports[0] if profile.volume_supports else None,
            'nearest_resistance': profile.volume_resistances[0] if profile.volume_resistances else None,
            'num_clusters': len(profile.clusters),
            'num_supports': len(profile.volume_supports),
            'num_resistances': len(profile.volume_resistances)
        }

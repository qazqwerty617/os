"""
MEXC Pump Monitor - Volume Profile Analysis
Optimized real volume clustering and price level significance
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
    price_poc: float
    total_volume: float
    buy_volume: float
    sell_volume: float
    trade_count: int
    avg_trade_size: float
    delta: float = 0
    delta_pct: float = 0
    imbalance: str = "NEUTRAL"
    
    def calculate_metrics(self):
        """Calculate derived metrics"""
        self.delta = self.buy_volume - self.sell_volume
        if self.total_volume > 0:
            self.delta_pct = (self.delta / self.total_volume) * 100
        
        if self.delta_pct > 10:
            self.imbalance = "BUY"
        elif self.delta_pct < -10:
            self.imbalance = "SELL"


@dataclass
class VolumeProfile:
    """Complete volume profile for a symbol"""
    symbol: str
    timestamp: int
    period_minutes: int
    high: float = 0
    low: float = 0
    current_price: float = 0
    poc: float = 0
    vah: float = 0
    val: float = 0
    clusters: List[VolumeCluster] = field(default_factory=list)
    total_volume: float = 0
    total_buy_volume: float = 0
    total_sell_volume: float = 0
    profile_shape: str = "NORMAL"
    volume_supports: List[float] = field(default_factory=list)
    volume_resistances: List[float] = field(default_factory=list)


@dataclass
class Trade:
    """Single trade record"""
    timestamp: int
    price: float
    quantity: float
    side: str
    value_usd: float


class VolumeProfiler:
    """
    Optimized volume profile analysis
    Uses actual trade data to build accurate profiles
    """
    
    VALUE_AREA_PCT = 0.7
    HIGH_VOLUME_THRESHOLD = 1.5
    
    def __init__(self, num_clusters: int = 24):
        self.num_clusters = num_clusters
        self.trades: Dict[str, List[Trade]] = defaultdict(list)
        self.profiles: Dict[str, VolumeProfile] = {}
        self.max_trades = 2000  # Reduced from 50k to prevent OOM
    
    def record_trade(
        self, symbol: str, price: float, quantity: float,
        side: str, timestamp: int = None
    ):
        """Record an actual trade"""
        timestamp = timestamp or int(time.time() * 1000)
        
        self.trades[symbol].append(Trade(
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            side=side.upper(),
            value_usd=price * quantity
        ))
        
        if len(self.trades[symbol]) > self.max_trades:
            self.trades[symbol] = self.trades[symbol][-self.max_trades:]
    
    def build_profile(self, symbol: str, period_minutes: int = 60) -> Optional[VolumeProfile]:
        """Build volume profile from REAL trade data"""
        trades = self.trades.get(symbol, [])
        if len(trades) < 10:
            return None
        
        now = int(time.time() * 1000)
        cutoff = now - (period_minutes * 60000)
        
        period_trades = [t for t in trades if t.timestamp >= cutoff]
        if len(period_trades) < 10:
            return None
        
        prices = [t.price for t in period_trades]
        high, low = max(prices), min(prices)
        
        if high == low:
            return None
        
        profile = VolumeProfile(
            symbol=symbol,
            timestamp=now,
            period_minutes=period_minutes,
            high=high,
            low=low,
            current_price=period_trades[-1].price
        )
        
        # Build clusters
        cluster_size = (high - low) / self.num_clusters
        clusters = []
        
        for i in range(self.num_clusters):
            cl_low = low + (i * cluster_size)
            cl_high = low + ((i + 1) * cluster_size)
            
            cluster_trades = [t for t in period_trades if cl_low <= t.price < cl_high]
            if not cluster_trades:
                continue
            
            buy_vol = sum(t.value_usd for t in cluster_trades if t.side == 'BUY')
            sell_vol = sum(t.value_usd for t in cluster_trades if t.side == 'SELL')
            total_vol = buy_vol + sell_vol
            
            cluster = VolumeCluster(
                price_low=cl_low,
                price_high=cl_high,
                price_poc=statistics.median([t.price for t in cluster_trades]),
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
        profile.total_volume = sum(c.total_volume for c in clusters)
        profile.total_buy_volume = sum(c.buy_volume for c in clusters)
        profile.total_sell_volume = sum(c.sell_volume for c in clusters)
        
        # POC
        poc_cluster = max(clusters, key=lambda c: c.total_volume)
        profile.poc = poc_cluster.price_poc
        
        self._calculate_value_area(profile)
        self._find_sr_levels(profile)
        self._determine_shape(profile)
        
        self.profiles[symbol] = profile
        return profile
    
    def cleanup(self, max_age_ms: int = 1800000):
        """Remove stale trade data and profiles older than max_age (default 30min)"""
        now = int(time.time() * 1000)
        cutoff = now - max_age_ms
        
        stale_symbols = []
        for sym, trades_list in self.trades.items():
            # Remove old trades
            self.trades[sym] = [t for t in trades_list if t.timestamp > cutoff]
            if not self.trades[sym]:
                stale_symbols.append(sym)
        
        for sym in stale_symbols:
            del self.trades[sym]
            self.profiles.pop(sym, None)
        
        if stale_symbols:
            logger.debug(f"🧹 VolumeProfiler cleanup: removed {len(stale_symbols)} stale symbols")
    
    def _calculate_value_area(self, profile: VolumeProfile):
        """Calculate Value Area High/Low (70% of volume)"""
        target = profile.total_volume * self.VALUE_AREA_PCT
        
        sorted_clusters = sorted(profile.clusters, key=lambda c: c.total_volume, reverse=True)
        cumulative = 0
        va_clusters = []
        
        for cluster in sorted_clusters:
            va_clusters.append(cluster)
            cumulative += cluster.total_volume
            if cumulative >= target:
                break
        
        if va_clusters:
            prices = [p for c in va_clusters for p in (c.price_low, c.price_high)]
            profile.val = min(prices)
            profile.vah = max(prices)
    
    def _find_sr_levels(self, profile: VolumeProfile):
        """Find support/resistance levels from high volume nodes"""
        if not profile.clusters:
            return
        
        avg_vol = profile.total_volume / len(profile.clusters)
        current = profile.current_price
        
        for cluster in profile.clusters:
            if cluster.total_volume > avg_vol * self.HIGH_VOLUME_THRESHOLD:
                mid = (cluster.price_low + cluster.price_high) / 2
                target = profile.volume_supports if mid < current else profile.volume_resistances
                target.append(mid)
        
        profile.volume_supports.sort(reverse=True)
        profile.volume_resistances.sort()
    
    def _determine_shape(self, profile: VolumeProfile):
        """Determine volume profile shape"""
        if len(profile.clusters) < 3:
            return
        
        third = len(profile.clusters) // 3
        lower = sum(c.total_volume for c in profile.clusters[:third])
        middle = sum(c.total_volume for c in profile.clusters[third:2*third])
        upper = sum(c.total_volume for c in profile.clusters[2*third:])
        
        if upper > lower * 1.5 and upper > middle:
            profile.profile_shape = "P-SHAPE"
        elif lower > upper * 1.5 and lower > middle:
            profile.profile_shape = "B-SHAPE"
        elif middle > upper and middle > lower:
            profile.profile_shape = "D-SHAPE"
    
    def get_delta_at_price(self, symbol: str, price: float) -> Tuple[float, str]:
        """Get buy/sell delta at specific price level"""
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
        
        below = [s for s in profile.volume_supports if s < price]
        return below[0] if below else None
    
    def get_nearest_resistance(self, symbol: str, price: float) -> Optional[float]:
        """Get nearest resistance level above price"""
        profile = self.profiles.get(symbol)
        if not profile:
            return None
        
        above = [r for r in profile.volume_resistances if r > price]
        return above[0] if above else None
    
    def is_price_at_high_volume_node(self, symbol: str, price: float, threshold: float = 1.5) -> bool:
        """Check if price is at a high volume node"""
        profile = self.profiles.get(symbol)
        if not profile or not profile.clusters:
            return False
        
        avg = profile.total_volume / len(profile.clusters)
        
        for cluster in profile.clusters:
            if cluster.price_low <= price < cluster.price_high:
                return cluster.total_volume > avg * threshold
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
            'buy_sell_ratio': profile.total_buy_volume / profile.total_sell_volume if profile.total_sell_volume else 0,
            'nearest_support': profile.volume_supports[0] if profile.volume_supports else None,
            'nearest_resistance': profile.volume_resistances[0] if profile.volume_resistances else None,
            'num_clusters': len(profile.clusters),
            'num_supports': len(profile.volume_supports),
            'num_resistances': len(profile.volume_resistances)
        }

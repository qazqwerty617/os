"""
MEXC Pump Monitor - Manipulation Detector
Tracks single-entity pump patterns and detects distribution phase
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque, Counter
import statistics

logger = logging.getLogger(__name__)


class PumperPhase(Enum):
    """Pumper activity phases"""
    ACCUMULATION = "ACCUMULATION"   # Quietly buying
    AGGRESSIVE_BUY = "AGGRESSIVE_BUY"  # Pumping hard
    DISTRIBUTION = "DISTRIBUTION"   # Starting to sell
    DUMPING = "DUMPING"             # Heavy selling
    INACTIVE = "INACTIVE"           # No activity


class ManipulationType(Enum):
    """Types of detected manipulation"""
    SINGLE_WALLET_PUMP = "SINGLE_WALLET_PUMP"
    WASH_TRADING = "WASH_TRADING"
    LAYERED_ORDERS = "LAYERED_ORDERS"
    SPOOFING = "SPOOFING"


@dataclass 
class OrderPattern:
    """Detected order pattern"""
    size: float  # Order size
    count: int   # How many times seen
    avg_interval_ms: int  # Average time between orders
    last_seen: int
    side: str  # "BUY" or "SELL"


@dataclass
class PumperProfile:
    """Profile of detected pumper entity"""
    symbol: str
    detected_at: int
    
    # Order patterns
    typical_order_sizes: List[float] = field(default_factory=list)
    avg_order_interval_ms: int = 0
    
    # Activity
    current_phase: PumperPhase = PumperPhase.INACTIVE
    phase_started: int = 0
    
    # Volume
    buy_volume_usd: float = 0
    sell_volume_usd: float = 0
    net_position_usd: float = 0
    
    # Timing
    buy_orders_count: int = 0
    sell_orders_count: int = 0
    last_buy_time: int = 0
    last_sell_time: int = 0
    
    # Distribution detection
    distribution_started: bool = False
    distribution_start_time: Optional[int] = None
    distribution_confidence: int = 0  # 0-100
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
    def get_buy_sell_ratio(self) -> float:
        """Get buy/sell ratio"""
        if self.sell_volume_usd == 0:
            return 10.0 if self.buy_volume_usd > 0 else 1.0
        return self.buy_volume_usd / self.sell_volume_usd
    
    def get_phase_duration_seconds(self) -> int:
        """Get current phase duration"""
        return (int(time.time() * 1000) - self.phase_started) // 1000
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'phase': self.current_phase.value,
            'phase_duration_sec': self.get_phase_duration_seconds(),
            'buy_volume': self.buy_volume_usd,
            'sell_volume': self.sell_volume_usd,
            'net_position': self.net_position_usd,
            'buy_sell_ratio': self.get_buy_sell_ratio(),
            'distribution_started': self.distribution_started,
            'distribution_confidence': self.distribution_confidence,
            'typical_order_sizes': self.typical_order_sizes[:5],
            'warnings': self.warnings
        }


@dataclass
class ManipulationAlert:
    """Alert for detected manipulation"""
    symbol: str
    alert_type: str
    timestamp: int
    
    message: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    
    # Context
    buy_sell_ratio: float = 1.0
    phase: str = ""
    confidence: int = 0
    
    # Action
    recommended_action: str = ""


class ManipulationDetector:
    """
    Detects single-wallet pump patterns and distribution phase
    
    Key signals:
    1. Repetitive order sizes (same entity)
    2. Regular timing intervals
    3. Sudden shift from buying to selling
    4. Volume exhaustion patterns
    """
    
    # Thresholds
    MIN_ORDERS_FOR_PATTERN = 5
    SIZE_SIMILARITY_THRESHOLD = 0.1  # 10% tolerance
    DISTRIBUTION_BUY_SELL_RATIO = 0.5  # Ratio drops below this = distribution
    
    def __init__(self):
        # Order history per symbol
        self.orders: Dict[str, deque] = {}
        self.max_orders = 500
        
        # Detected patterns
        self.patterns: Dict[str, List[OrderPattern]] = {}
        
        # Pumper profiles
        self.profiles: Dict[str, PumperProfile] = {}
        
        # Alerts
        self.alerts: List[ManipulationAlert] = []
        
        # Callbacks
        self._alert_callbacks: List = []
        self._distribution_callbacks: List = []
        
        # Stats
        self.stats = {
            'orders_analyzed': 0,
            'patterns_detected': 0,
            'distributions_detected': 0,
            'alerts_generated': 0
        }
    
    def on_alert(self, callback):
        """Register alert callback"""
        self._alert_callbacks.append(callback)
    
    def on_distribution(self, callback):
        """Register distribution detection callback"""
        self._distribution_callbacks.append(callback)
    
    def record_order(
        self,
        symbol: str,
        price: float,
        quantity: float,
        side: str,  # "BUY" or "SELL"
        timestamp: int = None
    ):
        """Record an order for pattern analysis"""
        timestamp = timestamp or int(time.time() * 1000)
        value_usd = price * quantity
        
        # Store order
        if symbol not in self.orders:
            self.orders[symbol] = deque(maxlen=self.max_orders)
        
        order = {
            'timestamp': timestamp,
            'price': price,
            'quantity': quantity,
            'value_usd': value_usd,
            'side': side.upper()
        }
        
        self.orders[symbol].append(order)
        self.stats['orders_analyzed'] += 1
        
        # Update or create profile
        self._update_profile(symbol, order)
        
        # Analyze patterns
        if len(self.orders[symbol]) >= self.MIN_ORDERS_FOR_PATTERN:
            self._analyze_patterns(symbol)
            self._detect_phase_change(symbol)
    
    def _update_profile(self, symbol: str, order: Dict):
        """Update pumper profile with new order"""
        if symbol not in self.profiles:
            self.profiles[symbol] = PumperProfile(
                symbol=symbol,
                detected_at=order['timestamp'],
                phase_started=order['timestamp']
            )
        
        profile = self.profiles[symbol]
        
        if order['side'] == 'BUY':
            profile.buy_volume_usd += order['value_usd']
            profile.buy_orders_count += 1
            profile.last_buy_time = order['timestamp']
            profile.net_position_usd += order['value_usd']
        else:
            profile.sell_volume_usd += order['value_usd']
            profile.sell_orders_count += 1
            profile.last_sell_time = order['timestamp']
            profile.net_position_usd -= order['value_usd']
    
    def _analyze_patterns(self, symbol: str):
        """Analyze order patterns for single-entity behavior"""
        orders = list(self.orders[symbol])
        
        # Group orders by similar size
        size_groups = self._group_by_size(orders)
        
        patterns = []
        for size, group_orders in size_groups.items():
            if len(group_orders) >= self.MIN_ORDERS_FOR_PATTERN:
                # Calculate average interval
                timestamps = sorted([o['timestamp'] for o in group_orders])
                intervals = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                avg_interval = sum(intervals) // len(intervals) if intervals else 0
                
                # Determine dominant side
                buys = len([o for o in group_orders if o['side'] == 'BUY'])
                sells = len(group_orders) - buys
                side = 'BUY' if buys > sells else 'SELL'
                
                pattern = OrderPattern(
                    size=size,
                    count=len(group_orders),
                    avg_interval_ms=avg_interval,
                    last_seen=max(timestamps),
                    side=side
                )
                patterns.append(pattern)
        
        if patterns:
            self.patterns[symbol] = patterns
            self.stats['patterns_detected'] = len(patterns)
            
            # Update profile with typical sizes
            profile = self.profiles.get(symbol)
            if profile:
                profile.typical_order_sizes = [p.size for p in sorted(patterns, key=lambda p: p.count, reverse=True)[:5]]
                
                # Calculate average interval
                intervals = [p.avg_interval_ms for p in patterns if p.avg_interval_ms > 0]
                if intervals:
                    profile.avg_order_interval_ms = sum(intervals) // len(intervals)
    
    def _group_by_size(self, orders: List[Dict]) -> Dict[float, List[Dict]]:
        """Group orders by similar size"""
        groups = {}
        
        for order in orders:
            size = order['value_usd']
            
            # Find existing group with similar size
            found = False
            for group_size in list(groups.keys()):
                if abs(size - group_size) / group_size < self.SIZE_SIMILARITY_THRESHOLD:
                    groups[group_size].append(order)
                    found = True
                    break
            
            if not found:
                groups[size] = [order]
        
        return groups
    
    def _detect_phase_change(self, symbol: str):
        """Detect pumper phase change"""
        profile = self.profiles.get(symbol)
        if not profile:
            return
        
        orders = list(self.orders[symbol])[-50:]  # Last 50 orders
        
        if len(orders) < 10:
            return
        
        # Split into recent and older
        recent = orders[-10:]
        older = orders[-30:-10] if len(orders) >= 30 else orders[:-10]
        
        if not older:
            return
        
        # Calculate buy/sell ratios
        recent_buys = sum(o['value_usd'] for o in recent if o['side'] == 'BUY')
        recent_sells = sum(o['value_usd'] for o in recent if o['side'] == 'SELL')
        
        older_buys = sum(o['value_usd'] for o in older if o['side'] == 'BUY')
        older_sells = sum(o['value_usd'] for o in older if o['side'] == 'SELL')
        
        recent_ratio = recent_buys / recent_sells if recent_sells > 0 else 10
        older_ratio = older_buys / older_sells if older_sells > 0 else 10
        
        old_phase = profile.current_phase
        now = int(time.time() * 1000)
        
        # Determine phase
        if recent_ratio > 3:
            new_phase = PumperPhase.AGGRESSIVE_BUY
        elif recent_ratio > 1.5:
            new_phase = PumperPhase.ACCUMULATION
        elif recent_ratio < 0.3:
            new_phase = PumperPhase.DUMPING
        elif recent_ratio < self.DISTRIBUTION_BUY_SELL_RATIO:
            new_phase = PumperPhase.DISTRIBUTION
        else:
            new_phase = profile.current_phase
        
        # Detect significant phase change
        if old_phase != new_phase:
            profile.current_phase = new_phase
            profile.phase_started = now
            
            # CRITICAL: Detect distribution start
            if old_phase in [PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION]:
                if new_phase in [PumperPhase.DISTRIBUTION, PumperPhase.DUMPING]:
                    self._trigger_distribution_alert(symbol, profile, recent_ratio, older_ratio)
    
    def _trigger_distribution_alert(
        self,
        symbol: str,
        profile: PumperProfile,
        recent_ratio: float,
        older_ratio: float
    ):
        """Trigger distribution/dump alert"""
        profile.distribution_started = True
        profile.distribution_start_time = int(time.time() * 1000)
        
        # Calculate confidence
        ratio_drop = (older_ratio - recent_ratio) / older_ratio if older_ratio > 0 else 0
        confidence = min(100, int(ratio_drop * 100 + 30))
        profile.distribution_confidence = confidence
        
        self.stats['distributions_detected'] += 1
        
        # Determine severity
        if profile.current_phase == PumperPhase.DUMPING:
            severity = "CRITICAL"
            action = "EXIT IMMEDIATELY - Heavy selling detected"
        else:
            severity = "WARNING"
            action = "Prepare to exit - Distribution phase starting"
        
        alert = ManipulationAlert(
            symbol=symbol,
            alert_type="DISTRIBUTION_DETECTED",
            timestamp=int(time.time() * 1000),
            message=f"🚨 DISTRIBUTION DETECTED on {symbol}! Buy/Sell ratio dropped from {older_ratio:.1f} to {recent_ratio:.1f}",
            severity=severity,
            buy_sell_ratio=recent_ratio,
            phase=profile.current_phase.value,
            confidence=confidence,
            recommended_action=action
        )
        
        self.alerts.append(alert)
        self.stats['alerts_generated'] += 1
        
        logger.warning(f"🚨 DISTRIBUTION: {symbol} - {alert.message}")
        
        # Notify callbacks
        self._notify_distribution(symbol, profile, alert)
    
    async def _notify_distribution(self, symbol: str, profile: PumperProfile, alert: ManipulationAlert):
        """Notify distribution callbacks"""
        import asyncio
        
        for callback in self._distribution_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, profile, alert)
                else:
                    callback(symbol, profile, alert)
            except Exception as e:
                logger.error(f"Distribution callback error: {e}")
    
    def get_profile(self, symbol: str) -> Optional[PumperProfile]:
        """Get pumper profile for symbol"""
        return self.profiles.get(symbol)
    
    def get_all_distributions(self) -> List[PumperProfile]:
        """Get all symbols in distribution phase"""
        return [
            p for p in self.profiles.values()
            if p.distribution_started or p.current_phase in [PumperPhase.DISTRIBUTION, PumperPhase.DUMPING]
        ]
    
    def get_active_pumps(self) -> List[PumperProfile]:
        """Get actively pumping symbols"""
        return [
            p for p in self.profiles.values()
            if p.current_phase in [PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION]
        ]
    
    def is_single_entity_pump(self, symbol: str) -> Tuple[bool, int]:
        """
        Check if pump looks like single entity manipulation
        
        Returns:
            (is_manipulation, confidence)
        """
        patterns = self.patterns.get(symbol, [])
        profile = self.profiles.get(symbol)
        
        if not patterns or not profile:
            return False, 0
        
        confidence = 0
        
        # Check for repetitive order sizes
        dominant_pattern = max(patterns, key=lambda p: p.count)
        if dominant_pattern.count >= 10:
            confidence += 30
        if dominant_pattern.count >= 20:
            confidence += 20
        
        # Check for regular intervals
        if profile.avg_order_interval_ms > 0:
            # Calculate interval consistency
            if 1000 < profile.avg_order_interval_ms < 60000:  # 1-60 seconds
                confidence += 25
        
        # Check buy concentration
        if profile.get_buy_sell_ratio() > 5:
            confidence += 25
        
        return confidence >= 50, confidence
    
    def get_exit_recommendation(self, symbol: str) -> Dict:
        """Get exit recommendation for symbol"""
        profile = self.profiles.get(symbol)
        
        if not profile:
            return {'action': 'NO_DATA', 'urgency': 'LOW'}
        
        if profile.current_phase == PumperPhase.DUMPING:
            return {
                'action': 'EXIT_NOW',
                'urgency': 'CRITICAL',
                'reason': 'Heavy dump in progress',
                'confidence': 95
            }
        elif profile.current_phase == PumperPhase.DISTRIBUTION:
            return {
                'action': 'PREPARE_EXIT',
                'urgency': 'HIGH',
                'reason': 'Distribution phase detected',
                'confidence': profile.distribution_confidence
            }
        elif profile.current_phase == PumperPhase.AGGRESSIVE_BUY:
            duration = profile.get_phase_duration_seconds()
            if duration > 300:  # 5+ minutes of aggressive buying
                return {
                    'action': 'WATCH_CLOSELY',
                    'urgency': 'MEDIUM',
                    'reason': f'Pump running for {duration//60}min - could reverse soon',
                    'confidence': 60
                }
            return {
                'action': 'HOLD',
                'urgency': 'LOW',
                'reason': 'Pump active',
                'confidence': 40
            }
        
        return {'action': 'MONITOR', 'urgency': 'LOW', 'reason': 'No clear signal'}
    
    def generate_report(self, symbol: str) -> str:
        """Generate detailed report for symbol"""
        profile = self.profiles.get(symbol)
        patterns = self.patterns.get(symbol, [])
        
        if not profile:
            return f"No data for {symbol}"
        
        is_manip, manip_conf = self.is_single_entity_pump(symbol)
        exit_rec = self.get_exit_recommendation(symbol)
        
        report = f"""
🎯 MANIPULATION ANALYSIS: {symbol}
{'=' * 40}

📊 CURRENT PHASE: {profile.current_phase.value}
   Duration: {profile.get_phase_duration_seconds()}s

💰 VOLUME:
   Buy Volume:  ${profile.buy_volume_usd:,.0f}
   Sell Volume: ${profile.sell_volume_usd:,.0f}
   Net Position: ${profile.net_position_usd:,.0f}
   Buy/Sell Ratio: {profile.get_buy_sell_ratio():.2f}

🔍 PATTERN ANALYSIS:
   Typical Order Sizes: {[f'${s:,.0f}' for s in profile.typical_order_sizes[:3]]}
   Avg Order Interval: {profile.avg_order_interval_ms}ms
   
   Single Entity Detected: {'YES' if is_manip else 'NO'} ({manip_conf}% confidence)

🚨 DISTRIBUTION STATUS:
   Started: {'YES' if profile.distribution_started else 'NO'}
   Confidence: {profile.distribution_confidence}%

📋 RECOMMENDATION:
   Action: {exit_rec['action']}
   Urgency: {exit_rec['urgency']}
   Reason: {exit_rec.get('reason', 'N/A')}
"""
        
        return report


class DumpPredictor:
    """
    Predicts when pumper will likely dump
    Based on historical patterns and current behavior
    """
    
    # Typical pump durations by meme coin type
    TYPICAL_PUMP_DURATIONS = {
        'micro': (60, 300),      # 1-5 minutes
        'small': (300, 900),     # 5-15 minutes  
        'medium': (900, 3600),   # 15-60 minutes
        'large': (3600, 14400),  # 1-4 hours
    }
    
    def __init__(self, detector: ManipulationDetector):
        self.detector = detector
        
        # Historical dumps for learning
        self.dump_history: List[Dict] = []
    
    def predict_dump_time(self, symbol: str) -> Optional[Dict]:
        """
        Predict when dump is likely
        
        Returns:
            {
                'estimated_seconds': int,
                'confidence': int,
                'signals': List[str]
            }
        """
        profile = self.detector.get_profile(symbol)
        
        if not profile:
            return None
        
        if profile.current_phase not in [PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION]:
            return None
        
        signals = []
        estimated_seconds = 0
        confidence = 30
        
        pump_duration = profile.get_phase_duration_seconds()
        
        # Based on typical patterns
        if pump_duration > 300:  # 5+ minutes
            estimated_seconds = 120  # Could dump in next 2 min
            signals.append("Pump running 5+ minutes")
            confidence += 20
        
        if pump_duration > 600:  # 10+ minutes
            estimated_seconds = 60  # Imminent
            signals.append("Extended pump (10+ min)")
            confidence += 20
        
        # Check if buy pressure declining
        orders = list(self.detector.orders.get(symbol, []))[-20:]
        if len(orders) >= 10:
            recent_buys = sum(1 for o in orders[-5:] if o['side'] == 'BUY')
            older_buys = sum(1 for o in orders[-10:-5] if o['side'] == 'BUY')
            
            if recent_buys < older_buys:
                signals.append("Buy pressure declining")
                confidence += 15
                estimated_seconds = min(estimated_seconds, 90) if estimated_seconds else 90
        
        # Check order size changes
        if orders:
            recent_sizes = [o['value_usd'] for o in orders[-5:]]
            older_sizes = [o['value_usd'] for o in orders[-15:-5]]
            
            if recent_sizes and older_sizes:
                recent_avg = sum(recent_sizes) / len(recent_sizes)
                older_avg = sum(older_sizes) / len(older_sizes)
                
                if recent_avg < older_avg * 0.7:  # 30% drop in order size
                    signals.append("Order sizes decreasing")
                    confidence += 15
        
        if not signals:
            return None
        
        return {
            'estimated_seconds': estimated_seconds,
            'confidence': min(100, confidence),
            'signals': signals,
            'recommendation': 'PREPARE_EXIT' if confidence > 60 else 'MONITOR'
        }
    
    def record_dump(self, symbol: str, pump_duration: int, dump_severity: float):
        """Record a dump event for learning"""
        self.dump_history.append({
            'symbol': symbol,
            'pump_duration': pump_duration,
            'dump_severity': dump_severity,
            'timestamp': int(time.time() * 1000)
        })

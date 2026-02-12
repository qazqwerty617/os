"""
MEXC Pump Monitor - Manipulation Detector
Optimized pump detection and distribution phase tracking
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import asyncio

logger = logging.getLogger(__name__)


class PumperPhase(Enum):
    """Pumper activity phases"""
    ACCUMULATION = "ACCUMULATION"
    AGGRESSIVE_BUY = "AGGRESSIVE_BUY"
    DISTRIBUTION = "DISTRIBUTION"
    DUMPING = "DUMPING"
    INACTIVE = "INACTIVE"


class ManipulationType(Enum):
    """Types of manipulation"""
    SINGLE_WALLET_PUMP = "SINGLE_WALLET_PUMP"
    WASH_TRADING = "WASH_TRADING"
    LAYERED_ORDERS = "LAYERED_ORDERS"
    SPOOFING = "SPOOFING"


@dataclass
class PumperProfile:
    """Pumper entity profile"""
    symbol: str
    detected_at: int
    
    typical_order_sizes: List[float] = field(default_factory=list)
    avg_order_interval_ms: int = 0
    
    current_phase: PumperPhase = PumperPhase.INACTIVE
    phase_started: int = 0
    
    buy_volume_usd: float = 0
    sell_volume_usd: float = 0
    net_position_usd: float = 0
    
    buy_orders_count: int = 0
    sell_orders_count: int = 0
    last_buy_time: int = 0
    last_sell_time: int = 0
    
    distribution_started: bool = False
    distribution_start_time: Optional[int] = None
    distribution_confidence: int = 0
    
    warnings: List[str] = field(default_factory=list)
    
    def get_buy_sell_ratio(self) -> float:
        if self.sell_volume_usd == 0:
            return 10.0 if self.buy_volume_usd > 0 else 1.0
        return self.buy_volume_usd / self.sell_volume_usd
    
    def get_phase_duration_seconds(self) -> int:
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
    """Manipulation alert"""
    symbol: str
    alert_type: str
    timestamp: int
    message: str
    severity: str
    buy_sell_ratio: float = 1.0
    phase: str = ""
    confidence: int = 0
    recommended_action: str = ""


class ManipulationDetector:
    """
    Optimized manipulation detector
    
    Key signals:
    1. Repetitive order sizes
    2. Regular timing intervals
    3. Sudden buying to selling shift
    4. Volume exhaustion
    """
    
    MIN_ORDERS_FOR_PATTERN = 5
    SIZE_SIMILARITY_THRESHOLD = 0.1
    DISTRIBUTION_BUY_SELL_RATIO = 0.5
    
    # Phase thresholds (ratio -> phase)
    PHASE_THRESHOLDS = [
        (3.0, PumperPhase.AGGRESSIVE_BUY),
        (1.5, PumperPhase.ACCUMULATION),
        (0.3, PumperPhase.DUMPING),
        (0.5, PumperPhase.DISTRIBUTION),
    ]
    
    def __init__(self):
        self.orders: Dict[str, deque] = {}
        self.max_orders = 500
        self.profiles: Dict[str, PumperProfile] = {}
        self.alerts: List[ManipulationAlert] = []
        
        self._alert_callbacks: List = []
        self._distribution_callbacks: List = []
        
        self.stats = {
            'orders_analyzed': 0,
            'patterns_detected': 0,
            'distributions_detected': 0,
            'alerts_generated': 0
        }
    
    def on_alert(self, callback):
        self._alert_callbacks.append(callback)
    
    def on_distribution(self, callback):
        self._distribution_callbacks.append(callback)
    
    def record_order(
        self,
        symbol: str,
        price: float,
        quantity: float,
        side: str,
        timestamp: int = None
    ):
        """Record an order for analysis"""
        timestamp = timestamp or int(time.time() * 1000)
        value_usd = price * quantity
        
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
        
        self._update_profile(symbol, order)
        
        if len(self.orders[symbol]) >= self.MIN_ORDERS_FOR_PATTERN:
            self._detect_phase_change(symbol)
    
    def _update_profile(self, symbol: str, order: Dict):
        """Update profile with new order"""
        if symbol not in self.profiles:
            self.profiles[symbol] = PumperProfile(
                symbol=symbol,
                detected_at=order['timestamp'],
                phase_started=order['timestamp']
            )
        
        profile = self.profiles[symbol]
        is_buy = order['side'] == 'BUY'
        value = order['value_usd']
        
        if is_buy:
            profile.buy_volume_usd += value
            profile.buy_orders_count += 1
            profile.last_buy_time = order['timestamp']
            profile.net_position_usd += value
        else:
            profile.sell_volume_usd += value
            profile.sell_orders_count += 1
            profile.last_sell_time = order['timestamp']
            profile.net_position_usd -= value
    
    def _detect_phase_change(self, symbol: str):
        """Detect pumper phase change"""
        profile = self.profiles.get(symbol)
        if not profile:
            return
        
        orders = list(self.orders[symbol])[-50:]
        if len(orders) < 10:
            return
        
        recent = orders[-10:]
        older = orders[-30:-10] if len(orders) >= 30 else orders[:-10]
        
        if not older:
            return
        
        # Calculate ratios
        recent_buys = sum(o['value_usd'] for o in recent if o['side'] == 'BUY')
        recent_sells = sum(o['value_usd'] for o in recent if o['side'] == 'SELL')
        older_buys = sum(o['value_usd'] for o in older if o['side'] == 'BUY')
        older_sells = sum(o['value_usd'] for o in older if o['side'] == 'SELL')
        
        recent_ratio = recent_buys / recent_sells if recent_sells > 0 else 10
        older_ratio = older_buys / older_sells if older_sells > 0 else 10
        
        old_phase = profile.current_phase
        now = int(time.time() * 1000)
        
        # Determine new phase
        new_phase = profile.current_phase
        for threshold, phase in self.PHASE_THRESHOLDS:
            if phase in (PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION):
                if recent_ratio >= threshold:
                    new_phase = phase
                    break
            else:
                if recent_ratio <= threshold:
                    new_phase = phase
                    break
        
        if old_phase != new_phase:
            profile.current_phase = new_phase
            profile.phase_started = now
            
            if old_phase in (PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION):
                if new_phase in (PumperPhase.DISTRIBUTION, PumperPhase.DUMPING):
                    self._trigger_distribution_alert(symbol, profile, recent_ratio, older_ratio)
    
    def _trigger_distribution_alert(
        self,
        symbol: str,
        profile: PumperProfile,
        recent_ratio: float,
        older_ratio: float
    ):
        """Trigger distribution alert"""
        profile.distribution_started = True
        profile.distribution_start_time = int(time.time() * 1000)
        
        ratio_drop = (older_ratio - recent_ratio) / older_ratio if older_ratio > 0 else 0
        confidence = min(100, int(ratio_drop * 100 + 30))
        profile.distribution_confidence = confidence
        
        self.stats['distributions_detected'] += 1
        
        is_dumping = profile.current_phase == PumperPhase.DUMPING
        severity = "CRITICAL" if is_dumping else "WARNING"
        action = "EXIT IMMEDIATELY" if is_dumping else "Prepare to exit"
        
        alert = ManipulationAlert(
            symbol=symbol,
            alert_type="DISTRIBUTION_DETECTED",
            timestamp=int(time.time() * 1000),
            message=f"🚨 DISTRIBUTION: {symbol} ratio {older_ratio:.1f} → {recent_ratio:.1f}",
            severity=severity,
            buy_sell_ratio=recent_ratio,
            phase=profile.current_phase.value,
            confidence=confidence,
            recommended_action=action
        )
        
        self.alerts.append(alert)
        self.stats['alerts_generated'] += 1
        
        logger.info(f"🚨 DISTRIBUTION: {symbol} - {alert.message}")
        
        asyncio.create_task(self._notify_distribution(symbol, profile, alert))
    
    async def _notify_distribution(self, symbol: str, profile: PumperProfile, alert: ManipulationAlert):
        """Notify callbacks"""
        for callback in self._distribution_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, profile, alert)
                else:
                    callback(symbol, profile, alert)
            except Exception as e:
                logger.error(f"Distribution callback error: {e}")
    
    def get_profile(self, symbol: str) -> Optional[PumperProfile]:
        return self.profiles.get(symbol)
    
    def get_all_distributions(self) -> List[PumperProfile]:
        return [
            p for p in self.profiles.values()
            if p.distribution_started or p.current_phase in (PumperPhase.DISTRIBUTION, PumperPhase.DUMPING)
        ]
    
    def get_active_pumps(self) -> List[PumperProfile]:
        return [
            p for p in self.profiles.values()
            if p.current_phase in (PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION)
        ]
    
    def is_single_entity_pump(self, symbol: str) -> Tuple[bool, int]:
        """Check if single entity manipulation"""
        profile = self.profiles.get(symbol)
        if not profile:
            return False, 0
        
        confidence = 0
        
        # Order count check
        total_orders = profile.buy_orders_count + profile.sell_orders_count
        if total_orders >= 10:
            confidence += 30
        if total_orders >= 20:
            confidence += 20
        
        # Interval consistency
        if profile.avg_order_interval_ms > 0:
            if 1000 < profile.avg_order_interval_ms < 60000:
                confidence += 25
        
        # Buy concentration
        if profile.get_buy_sell_ratio() > 5:
            confidence += 25
        
        return confidence >= 50, confidence
    
    def get_exit_recommendation(self, symbol: str) -> Dict:
        """Get exit recommendation"""
        profile = self.profiles.get(symbol)
        
        if not profile:
            return {'action': 'NO_DATA', 'urgency': 'LOW'}
        
        recommendations = {
            PumperPhase.DUMPING: {
                'action': 'EXIT_NOW',
                'urgency': 'CRITICAL',
                'reason': 'Heavy dump in progress',
                'confidence': 95
            },
            PumperPhase.DISTRIBUTION: {
                'action': 'PREPARE_EXIT',
                'urgency': 'HIGH',
                'reason': 'Distribution phase detected',
                'confidence': profile.distribution_confidence
            }
        }
        
        if profile.current_phase in recommendations:
            return recommendations[profile.current_phase]
        
        if profile.current_phase == PumperPhase.AGGRESSIVE_BUY:
            duration = profile.get_phase_duration_seconds()
            if duration > 300:
                return {
                    'action': 'WATCH_CLOSELY',
                    'urgency': 'MEDIUM',
                    'reason': f'Pump running {duration//60}min',
                    'confidence': 60
                }
            return {'action': 'HOLD', 'urgency': 'LOW', 'confidence': 40}
        
        return {'action': 'MONITOR', 'urgency': 'LOW'}


class DumpPredictor:
    """Predicts dump timing - optimized"""
    
    TYPICAL_PUMP_DURATIONS = {
        'micro': (60, 300),
        'small': (300, 900),
        'medium': (900, 3600),
        'large': (3600, 14400),
    }
    
    def __init__(self, detector: ManipulationDetector):
        self.detector = detector
        self.dump_history: List[Dict] = []
    
    def predict_dump_time(self, symbol: str) -> Optional[Dict]:
        """Predict dump timing"""
        profile = self.detector.get_profile(symbol)
        
        if not profile or profile.current_phase not in (PumperPhase.AGGRESSIVE_BUY, PumperPhase.ACCUMULATION):
            return None
        
        signals = []
        estimated_seconds = 0
        confidence = 30
        
        pump_duration = profile.get_phase_duration_seconds()
        
        # Duration-based prediction
        if pump_duration > 600:
            estimated_seconds = 60
            signals.append("Extended pump (10+ min)")
            confidence += 40
        elif pump_duration > 300:
            estimated_seconds = 120
            signals.append("Pump running 5+ minutes")
            confidence += 20
        
        # Buy pressure analysis
        orders = list(self.detector.orders.get(symbol, []))[-20:]
        if len(orders) >= 10:
            recent_buys = sum(1 for o in orders[-5:] if o['side'] == 'BUY')
            older_buys = sum(1 for o in orders[-10:-5] if o['side'] == 'BUY')
            
            if recent_buys < older_buys:
                signals.append("Buy pressure declining")
                confidence += 15
                estimated_seconds = min(estimated_seconds, 90) if estimated_seconds else 90
        
        if not signals:
            return None
        
        return {
            'estimated_seconds': estimated_seconds,
            'confidence': min(100, confidence),
            'signals': signals,
            'recommendation': 'PREPARE_EXIT' if confidence > 60 else 'MONITOR'
        }
    
    def record_dump(self, symbol: str, pump_duration: int, dump_severity: float):
        """Record dump for learning"""
        self.dump_history.append({
            'symbol': symbol,
            'pump_duration': pump_duration,
            'dump_severity': dump_severity,
            'timestamp': int(time.time() * 1000)
        })

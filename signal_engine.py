"""
MEXC Pump Monitor - Enhanced Signal Engine
Optimized signal generation with all analysis modules
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

from config import config
from indicators import IndicatorResult

logger = logging.getLogger(__name__)


class SignalQuality(Enum):
    """Signal quality grades"""
    S_TIER = "S"  # Perfect setup - 90+ score
    A_TIER = "A"  # Excellent - 80+ score
    B_TIER = "B"  # Good - 70+ score
    C_TIER = "C"  # Risky - 60+ score


# Quality thresholds for faster lookup
QUALITY_THRESHOLDS = [
    (90, SignalQuality.S_TIER),
    (80, SignalQuality.A_TIER),
    (70, SignalQuality.B_TIER),
    (0, SignalQuality.C_TIER)
]

# Pump tier thresholds
PUMP_TIERS = [
    (50, 'MEGA'),
    (30, 'MASSIVE'),
    (15, 'STRONG'),
    (0, 'EARLY')
]

# Position weights by quality
POSITION_WEIGHTS = {
    SignalQuality.S_TIER: 1.0,
    SignalQuality.A_TIER: 0.75,
    SignalQuality.B_TIER: 0.5,
    SignalQuality.C_TIER: 0.25
}


@dataclass
class EnhancedSignal:
    """Enhanced signal with all data combined"""
    symbol: str
    timestamp: int
    
    # Price data
    price: float
    price_change_pct: float
    pump_tier: str
    
    # Technical indicators
    rsi: float
    rsi_5m: float
    rsi_15m: float
    ema_extension_pct: float
    momentum: float
    
    # Volume data
    volume_ratio: float
    volume_usd_24h: float
    buy_sell_ratio: float
    
    # Whale activity
    whale_buy_volume: float
    whale_sell_volume: float
    whale_pressure: int
    
    # Market structure
    funding_rate: float
    open_interest: float
    oi_change_1h: float
    
    # Volume profile
    vp_poc: float
    vp_vah: float
    vp_val: float
    nearest_resistance: float
    nearest_support: float
    
    # MTF confluence
    mtf_score: int
    tf_alignment: str
    
    # Divergences
    has_bearish_div: bool
    has_bullish_div: bool
    
    # Scoring
    base_score: int
    final_score: int
    quality: SignalQuality
    
    # Trade parameters
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    position_weight: float
    
    confidence_breakdown: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    smart_levels: Optional[Any] = None  # SmartLevels объект для умных уровней
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price': self.price,
            'price_change_pct': self.price_change_pct,
            'pump_tier': self.pump_tier,
            'rsi': self.rsi,
            'volume_ratio': self.volume_ratio,
            'whale_pressure': self.whale_pressure,
            'funding_rate': self.funding_rate,
            'mtf_score': self.mtf_score,
            'final_score': self.final_score,
            'quality': self.quality.value,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'risk_reward': self.risk_reward,
            'position_weight': self.position_weight,
            'warnings': self.warnings,
            'confidence': self.confidence_breakdown
        }


class SignalEngine:
    """
    Enhanced signal engine - optimized
    Combines all analysis for comprehensive signals
    """
    
    # Scoring weights
    WEIGHTS = {
        'rsi': 0.20,
        'volume': 0.20,
        'extension': 0.15,
        'momentum': 0.15,
        'whale': 0.10,
        'funding': 0.10,
        'mtf': 0.10
    }
    
    def __init__(
        self,
        whale_detector=None,
        volume_profiler=None,
        mtf_analyzer=None,
        market_analyzer=None,
        database=None
    ):
        self.whale_detector = whale_detector
        self.volume_profiler = volume_profiler
        self.mtf_analyzer = mtf_analyzer
        self.market_analyzer = market_analyzer
        self.database = database
        
        self.signals: List[EnhancedSignal] = []
        self._signal_callbacks: List = []
    
    def on_signal(self, callback):
        """Register callback for new signals"""
        self._signal_callbacks.append(callback)
    
    @staticmethod
    def _get_pump_tier(pct: float) -> str:
        """Get pump tier based on percentage change"""
        for threshold, tier in PUMP_TIERS:
            if pct >= threshold:
                return tier
        return 'EARLY'
    
    @staticmethod
    def _get_quality(score: int) -> SignalQuality:
        """Get quality based on score"""
        for threshold, quality in QUALITY_THRESHOLDS:
            if score >= threshold:
                return quality
        return SignalQuality.C_TIER
    
    @staticmethod
    def _calc_score(value: float, thresholds: List[tuple]) -> int:
        """Calculate score based on thresholds"""
        for threshold, score in thresholds:
            if value >= threshold:
                return score
        return thresholds[-1][1] if thresholds else 40
    
    async def generate_signal(
        self,
        symbol: str,
        price: float,
        price_change_pct: float,
        indicators: IndicatorResult,
        volume_usd: float
    ) -> Optional[EnhancedSignal]:
        """Generate enhanced signal with all confirmations"""
        timestamp = int(time.time() * 1000)
        
        pump_tier = self._get_pump_tier(price_change_pct)
        
        # Get whale data
        whale_buy, whale_sell, whale_pressure = 0, 0, 50
        if self.whale_detector:
            activity = self.whale_detector.get_activity(symbol)
            if activity:
                whale_buy = activity.buy_volume_usd
                whale_sell = activity.sell_volume_usd
                whale_pressure = activity.whale_pressure_score
        
        # Get market data
        funding_rate, open_interest, oi_change = 0, 0, 0
        if self.market_analyzer:
            funding = self.market_analyzer.funding_rates.get(symbol)
            if funding:
                funding_rate = funding.funding_rate
            
            oi = self.market_analyzer.open_interest.get(symbol)
            if oi:
                open_interest = oi.open_interest_value
                oi_change = oi.oi_change_1h
        
        # Get volume profile
        vp_poc, buy_sell_ratio = price, 1.0
        vp_vah, vp_val = price * 1.05, price * 0.95
        nearest_res, nearest_sup = price * 1.1, price * 0.9
        
        if self.volume_profiler:
            profile = self.volume_profiler.profiles.get(symbol)
            if profile:
                vp_poc = profile.poc
                vp_vah = profile.vah
                vp_val = profile.val
                nearest_res = self.volume_profiler.get_nearest_resistance(symbol, price) or price * 1.1
                nearest_sup = self.volume_profiler.get_nearest_support(symbol, price) or price * 0.9
                if profile.total_sell_volume > 0:
                    buy_sell_ratio = profile.total_buy_volume / profile.total_sell_volume
        
        # Get MTF analysis
        mtf_score, tf_alignment = 50, "Unknown"
        if self.mtf_analyzer:
            try:
                mtf = await self.mtf_analyzer.analyze_symbol(symbol)
                mtf_score = mtf.short_entry_score
                tf_alignment = f"{mtf.bullish_count} bullish, {mtf.bearish_count} bearish TFs"
            except Exception:
                pass
        
        # Calculate confidence scores
        confidence = {}
        
        # RSI score
        rsi = indicators.rsi
        confidence['rsi'] = self._calc_score(rsi, [(90, 100), (85, 90), (80, 75), (70, 60), (0, 40)])
        
        # Volume score - ОПТИМИЗИРОВАНО для мемкоинов (ниже пороги)
        vr = indicators.volume_ratio
        confidence['volume'] = self._calc_score(vr, [(5, 100), (3, 90), (2, 75), (1.5, 60), (0, 40)])  # Было 10/7/5/3
        
        # Extension score - ОПТИМИЗИРОВАНО для мемкоинов
        ext = abs(indicators.ema_extension_pct)
        confidence['extension'] = self._calc_score(ext, [(10, 100), (7, 85), (5, 70), (3, 55), (0, 40)])  # Было 15/10/7/5
        
        # Momentum score - ОПТИМИЗИРОВАНО для мемкоинов (мемкоины могут памповать сильнее)
        confidence['momentum'] = self._calc_score(
            price_change_pct, 
            [(100, 100), (50, 95), (30, 85), (15, 75), (5, 60), (0, 40)]  # Более агрессивные пороги
        )
        
        # Whale pressure (low = good for short)
        confidence['whale'] = 90 if whale_pressure < 30 else (70 if whale_pressure < 50 else (50 if whale_pressure < 70 else 30))
        
        # Funding rate (high = good for short)
        confidence['funding'] = self._calc_score(
            funding_rate,
            [(0.1, 100), (0.05, 80), (0, 60), (-1, 40)]
        )
        
        confidence['mtf'] = mtf_score
        
        # Divergence bonus
        confidence['divergence'] = 25 if (indicators.is_divergence and indicators.divergence_type == 'bearish') else 0
        
        # Calculate base score (weighted average)
        weights = self.WEIGHTS
        base_score = int(sum(confidence.get(k, 0) * v for k, v in weights.items()))
        
        # Final score with divergence bonus
        final_score = min(100, base_score + confidence['divergence'])
        
        quality = self._get_quality(final_score)
        
        # Calculate trade parameters for memecoins (wider stops for volatility)
        entry_price = price
        # Стоп 5-12% - даёт больше места для волатильности
        sl_pct = max(5, min(12, ext * 0.7))
        stop_loss = price * (1 + sl_pct / 100)
        
        # TP: 2x и 4x риск (вместо 1.5x и 3x) - лучший R:R
        tp1_pct = sl_pct * 2.0
        tp2_pct = sl_pct * 4.0
        
        take_profit_1 = price * (1 - tp1_pct / 100)
        take_profit_2 = price * (1 - tp2_pct / 100)
        
        if nearest_sup and nearest_sup < price * 0.95:
            take_profit_1 = nearest_sup
        
        risk = stop_loss - entry_price
        reward = entry_price - take_profit_1
        risk_reward = reward / risk if risk > 0 else 0
        
        position_weight = POSITION_WEIGHTS.get(quality, 0.25)
        
        # Generate warnings
        warnings = []
        if whale_pressure > 70:
            warnings.append("⚠️ High whale buy pressure")
        if funding_rate < 0:
            warnings.append("⚠️ Negative funding")
        if oi_change > 30:
            warnings.append("⚠️ OI spiking")
        if buy_sell_ratio > 2:
            warnings.append("⚠️ Heavy buying")
        if risk_reward < 1.5:
            warnings.append("⚠️ Low R:R")
        
        signal = EnhancedSignal(
            symbol=symbol,
            timestamp=timestamp,
            price=price,
            price_change_pct=price_change_pct,
            pump_tier=pump_tier,
            rsi=rsi,
            rsi_5m=rsi,
            rsi_15m=rsi,
            ema_extension_pct=indicators.ema_extension_pct,
            momentum=indicators.momentum,
            volume_ratio=indicators.volume_ratio,
            volume_usd_24h=volume_usd,
            buy_sell_ratio=buy_sell_ratio,
            whale_buy_volume=whale_buy,
            whale_sell_volume=whale_sell,
            whale_pressure=whale_pressure,
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_change_1h=oi_change,
            vp_poc=vp_poc,
            vp_vah=vp_vah,
            vp_val=vp_val,
            nearest_resistance=nearest_res,
            nearest_support=nearest_sup,
            mtf_score=mtf_score,
            tf_alignment=tf_alignment,
            has_bearish_div=indicators.is_divergence and indicators.divergence_type == 'bearish',
            has_bullish_div=indicators.is_divergence and indicators.divergence_type == 'bullish',
            base_score=base_score,
            final_score=final_score,
            quality=quality,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            risk_reward=risk_reward,
            position_weight=position_weight,
            confidence_breakdown=confidence,
            warnings=warnings
        )
        
        # Store signal (keep last 200)
        self.signals.append(signal)
        if len(self.signals) > 200:
            self.signals = self.signals[-200:]
        
        # Notify callbacks
        await self._notify_signal(signal)
        
        return signal
    
    async def _notify_signal(self, signal: EnhancedSignal):
        """Notify callbacks about new signal"""
        for callback in self._signal_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(signal)
                else:
                    callback(signal)
            except Exception as e:
                logger.error(f"Signal callback error: {e}")
    
    def get_best_signals(self, quality_threshold: SignalQuality = SignalQuality.B_TIER) -> List[EnhancedSignal]:
        """Get recent signals of specified quality or better"""
        quality_order = [SignalQuality.S_TIER, SignalQuality.A_TIER, SignalQuality.B_TIER, SignalQuality.C_TIER]
        threshold_idx = quality_order.index(quality_threshold)
        
        return [
            s for s in self.signals
            if quality_order.index(s.quality) <= threshold_idx
        ]
    
    def get_signals_by_tier(self, tier: str) -> List[EnhancedSignal]:
        """Get signals by pump tier"""
        return [s for s in self.signals if s.pump_tier == tier]

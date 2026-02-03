"""
MEXC Pump Monitor - Enhanced Signal Engine
Combines all analysis modules for comprehensive signal generation
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from config import config
from indicators import calculate_all_indicators, IndicatorResult
from pump_detector import PumpSignal

logger = logging.getLogger(__name__)


class SignalQuality(Enum):
    """Signal quality grades"""
    S_TIER = "S"  # Perfect setup - 90+ score, all confirmations
    A_TIER = "A"  # Excellent - 80+ score, strong confirmations
    B_TIER = "B"  # Good - 70+ score, some confirmations
    C_TIER = "C"  # Risky - 60+ score, weak setup


@dataclass
class EnhancedSignal:
    """Enhanced signal with all data combined"""
    # Base signal
    symbol: str
    timestamp: int
    
    # Price data
    price: float
    price_change_pct: float
    pump_tier: str  # MEGA, MASSIVE, STRONG, EARLY
    
    # Technical indicators
    rsi: float
    rsi_5m: float
    rsi_15m: float
    ema_extension_pct: float
    momentum: float
    
    # Volume data (REAL)
    volume_ratio: float
    volume_usd_24h: float
    buy_sell_ratio: float
    
    # Whale activity (REAL data)
    whale_buy_volume: float
    whale_sell_volume: float
    whale_pressure: int  # 0-100
    
    # Market structure
    funding_rate: float
    open_interest: float
    oi_change_1h: float
    
    # Volume profile (REAL)
    vp_poc: float  # Point of control
    vp_vah: float  # Value area high
    vp_val: float  # Value area low
    nearest_resistance: float
    nearest_support: float
    
    # MTF confluence
    mtf_score: int  # 0-100
    tf_alignment: str  # Description of TF alignment
    
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
    take_profit_1: float  # Conservative
    take_profit_2: float  # Aggressive
    risk_reward: float
    position_weight: float  # Suggested position size weight
    
    # Confidence breakdown
    confidence_breakdown: Dict[str, int] = field(default_factory=dict)
    
    # Warnings
    warnings: List[str] = field(default_factory=list)
    
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
    Enhanced signal engine
    Combines all analysis for comprehensive signals
    """
    
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
        
        # Signal history
        self.signals: List[EnhancedSignal] = []
        
        # Callbacks
        self._signal_callbacks: List = []
    
    def on_signal(self, callback):
        """Register callback for new signals"""
        self._signal_callbacks.append(callback)
    
    async def generate_signal(
        self,
        symbol: str,
        price: float,
        price_change_pct: float,
        indicators: IndicatorResult,
        volume_usd: float
    ) -> Optional[EnhancedSignal]:
        """
        Generate enhanced signal with all confirmations
        
        Args:
            symbol: Trading pair
            price: Current price
            price_change_pct: Recent price change
            indicators: Calculated indicators
            volume_usd: 24h volume in USD
        
        Returns:
            EnhancedSignal if signal is valid, None otherwise
        """
        timestamp = int(time.time() * 1000)
        
        # Determine pump tier
        if price_change_pct >= 50:
            pump_tier = 'MEGA'
        elif price_change_pct >= 30:
            pump_tier = 'MASSIVE'
        elif price_change_pct >= 15:
            pump_tier = 'STRONG'
        else:
            pump_tier = 'EARLY'
        
        # Get whale data
        whale_buy = 0
        whale_sell = 0
        whale_pressure = 50
        
        if self.whale_detector:
            activity = self.whale_detector.get_activity(symbol)
            if activity:
                whale_buy = activity.buy_volume_usd
                whale_sell = activity.sell_volume_usd
                whale_pressure = activity.whale_pressure_score
        
        # Get market data
        funding_rate = 0
        open_interest = 0
        oi_change = 0
        
        if self.market_analyzer:
            funding = self.market_analyzer.funding_rates.get(symbol)
            if funding:
                funding_rate = funding.funding_rate
            
            oi = self.market_analyzer.open_interest.get(symbol)
            if oi:
                open_interest = oi.open_interest_value
                oi_change = oi.oi_change_1h
        
        # Get volume profile
        vp_poc = price
        vp_vah = price * 1.05
        vp_val = price * 0.95
        nearest_res = price * 1.1
        nearest_sup = price * 0.9
        buy_sell_ratio = 1.0
        
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
        mtf_score = 50
        tf_alignment = "Unknown"
        
        if self.mtf_analyzer:
            try:
                mtf = await self.mtf_analyzer.analyze_symbol(symbol)
                mtf_score = mtf.short_entry_score
                tf_alignment = f"{mtf.bullish_count} bullish, {mtf.bearish_count} bearish TFs"
            except Exception as e:
                logger.debug(f"MTF analysis failed: {e}")
        
        # Calculate scores
        confidence = {}
        
        # RSI score (0-100)
        if indicators.rsi >= 90:
            confidence['rsi'] = 100
        elif indicators.rsi >= 85:
            confidence['rsi'] = 90
        elif indicators.rsi >= 80:
            confidence['rsi'] = 75
        elif indicators.rsi >= 70:
            confidence['rsi'] = 60
        else:
            confidence['rsi'] = 40
        
        # Volume score (0-100)
        if indicators.volume_ratio >= 10:
            confidence['volume'] = 100
        elif indicators.volume_ratio >= 7:
            confidence['volume'] = 90
        elif indicators.volume_ratio >= 5:
            confidence['volume'] = 75
        elif indicators.volume_ratio >= 3:
            confidence['volume'] = 60
        else:
            confidence['volume'] = 40
        
        # Extension score (0-100)
        ext = abs(indicators.ema_extension_pct)
        if ext >= 15:
            confidence['extension'] = 100
        elif ext >= 10:
            confidence['extension'] = 85
        elif ext >= 7:
            confidence['extension'] = 70
        elif ext >= 5:
            confidence['extension'] = 55
        else:
            confidence['extension'] = 40
        
        # Momentum score (0-100)
        if price_change_pct >= 50:
            confidence['momentum'] = 100
        elif price_change_pct >= 30:
            confidence['momentum'] = 90
        elif price_change_pct >= 20:
            confidence['momentum'] = 80
        elif price_change_pct >= 15:
            confidence['momentum'] = 70
        else:
            confidence['momentum'] = 50
        
        # Whale pressure score (for short: low whale buying is good)
        if whale_pressure < 30:  # Whales selling
            confidence['whale'] = 90
        elif whale_pressure < 50:
            confidence['whale'] = 70
        elif whale_pressure < 70:
            confidence['whale'] = 50
        else:  # Whales buying - risky for short
            confidence['whale'] = 30
        
        # Funding rate score (high funding = good for short)
        if funding_rate > 0.1:
            confidence['funding'] = 100
        elif funding_rate > 0.05:
            confidence['funding'] = 80
        elif funding_rate > 0:
            confidence['funding'] = 60
        else:
            confidence['funding'] = 40
        
        # MTF score
        confidence['mtf'] = mtf_score
        
        # Divergence bonus
        if indicators.is_divergence and indicators.divergence_type == 'bearish':
            confidence['divergence'] = 25
        else:
            confidence['divergence'] = 0
        
        # Calculate base score (weighted average)
        base_score = int(
            confidence['rsi'] * 0.20 +
            confidence['volume'] * 0.20 +
            confidence['extension'] * 0.15 +
            confidence['momentum'] * 0.15 +
            confidence['whale'] * 0.10 +
            confidence['funding'] * 0.10 +
            confidence['mtf'] * 0.10
        )
        
        # Add divergence bonus
        final_score = min(100, base_score + confidence['divergence'])
        
        # Determine quality
        if final_score >= 90:
            quality = SignalQuality.S_TIER
        elif final_score >= 80:
            quality = SignalQuality.A_TIER
        elif final_score >= 70:
            quality = SignalQuality.B_TIER
        else:
            quality = SignalQuality.C_TIER
        
        # Calculate trade parameters
        entry_price = price
        
        # Stop loss based on extension
        sl_pct = max(3, min(8, ext * 0.5))  # 3-8% SL based on extension
        stop_loss = price * (1 + sl_pct / 100)
        
        # Take profits
        tp1_pct = sl_pct * 1.5  # 1.5R minimum
        tp2_pct = sl_pct * 3.0  # 3R aggressive
        
        take_profit_1 = price * (1 - tp1_pct / 100)
        take_profit_2 = price * (1 - tp2_pct / 100)
        
        # Use nearest support as target if available
        if nearest_sup and nearest_sup < price * 0.95:
            take_profit_1 = nearest_sup
        
        # Risk/reward
        risk = stop_loss - entry_price
        reward = entry_price - take_profit_1
        risk_reward = reward / risk if risk > 0 else 0
        
        # Position weight (based on quality)
        position_weights = {
            SignalQuality.S_TIER: 1.0,
            SignalQuality.A_TIER: 0.75,
            SignalQuality.B_TIER: 0.5,
            SignalQuality.C_TIER: 0.25
        }
        position_weight = position_weights.get(quality, 0.25)
        
        # Generate warnings
        warnings = []
        
        if whale_pressure > 70:
            warnings.append("⚠️ High whale buy pressure - risky short")
        
        if funding_rate < 0:
            warnings.append("⚠️ Negative funding - shorts paying longs")
        
        if oi_change > 30:
            warnings.append("⚠️ OI spiking - new positions opening")
        
        if buy_sell_ratio > 2:
            warnings.append("⚠️ Heavy buying in volume profile")
        
        if risk_reward < 1.5:
            warnings.append("⚠️ Low R:R ratio")
        
        # Create signal
        signal = EnhancedSignal(
            symbol=symbol,
            timestamp=timestamp,
            price=price,
            price_change_pct=price_change_pct,
            pump_tier=pump_tier,
            rsi=indicators.rsi,
            rsi_5m=indicators.rsi,  # Would need separate calculation
            rsi_15m=indicators.rsi,
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
        
        # Store signal
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

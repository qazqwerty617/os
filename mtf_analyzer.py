"""
MEXC Pump Monitor - Multi-Timeframe Analysis
Analyze price action across multiple timeframes for confluence
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from indicators import calculate_rsi, calculate_ema, calculate_momentum

logger = logging.getLogger(__name__)


class Trend(Enum):
    """Market trend direction"""
    STRONG_UP = "STRONG_UP"
    UP = "UP"
    NEUTRAL = "NEUTRAL"
    DOWN = "DOWN"
    STRONG_DOWN = "STRONG_DOWN"


class SignalStrength(Enum):
    """Signal strength based on MTF confluence"""
    PERFECT = 5      # All timeframes aligned
    STRONG = 4       # 3+ timeframes aligned
    MODERATE = 3     # 2 timeframes aligned
    WEAK = 2         # Mixed signals
    CONFLICTING = 1  # Contradicting signals


@dataclass
class TimeframeAnalysis:
    """Analysis for single timeframe"""
    timeframe: str
    prices: List[float]
    volumes: List[float]
    
    # Calculated values
    rsi: float = 0
    ema20: float = 0
    ema50: float = 0
    ema200: float = 0
    momentum: float = 0
    trend: Trend = Trend.NEUTRAL
    
    # Price relative to EMAs
    above_ema20: bool = False
    above_ema50: bool = False
    above_ema200: bool = False
    
    # Extension
    ema20_extension_pct: float = 0
    
    def analyze(self):
        """Calculate all indicators for this timeframe"""
        if len(self.prices) < 20:
            return
        
        current_price = self.prices[-1]
        
        # RSI
        self.rsi = calculate_rsi(self.prices)
        
        # EMAs
        self.ema20 = calculate_ema(self.prices, 20)
        if len(self.prices) >= 50:
            self.ema50 = calculate_ema(self.prices, 50)
        if len(self.prices) >= 200:
            self.ema200 = calculate_ema(self.prices, 200)
        
        # Momentum
        self.momentum = calculate_momentum(self.prices)
        
        # Price vs EMAs
        self.above_ema20 = current_price > self.ema20
        self.above_ema50 = current_price > self.ema50 if self.ema50 else False
        self.above_ema200 = current_price > self.ema200 if self.ema200 else False
        
        # Extension from EMA20
        if self.ema20 > 0:
            self.ema20_extension_pct = ((current_price - self.ema20) / self.ema20) * 100
        
        # Determine trend
        self._determine_trend()
    
    def _determine_trend(self):
        """Determine trend based on EMAs and momentum"""
        bullish_signals = 0
        bearish_signals = 0
        
        # EMA alignment
        if self.above_ema20:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if self.above_ema50:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        if self.above_ema200:
            bullish_signals += 1
        else:
            bearish_signals += 1
        
        # Momentum
        if self.momentum > 5:
            bullish_signals += 2
        elif self.momentum > 0:
            bullish_signals += 1
        elif self.momentum < -5:
            bearish_signals += 2
        else:
            bearish_signals += 1
        
        # RSI
        if self.rsi > 70:
            bullish_signals += 1
        elif self.rsi < 30:
            bearish_signals += 1
        
        # Determine trend
        net = bullish_signals - bearish_signals
        
        if net >= 4:
            self.trend = Trend.STRONG_UP
        elif net >= 2:
            self.trend = Trend.UP
        elif net <= -4:
            self.trend = Trend.STRONG_DOWN
        elif net <= -2:
            self.trend = Trend.DOWN
        else:
            self.trend = Trend.NEUTRAL


@dataclass
class MTFAnalysis:
    """Multi-timeframe analysis result"""
    symbol: str
    timestamp: int
    
    # Individual timeframe analyses
    tf_1m: Optional[TimeframeAnalysis] = None
    tf_5m: Optional[TimeframeAnalysis] = None
    tf_15m: Optional[TimeframeAnalysis] = None
    tf_1h: Optional[TimeframeAnalysis] = None
    tf_4h: Optional[TimeframeAnalysis] = None
    
    # Confluence scoring
    signal_strength: SignalStrength = SignalStrength.WEAK
    bullish_count: int = 0
    bearish_count: int = 0
    
    # Short entry quality (0-100)
    short_entry_score: int = 0
    
    # Key levels
    nearest_resistance: float = 0
    nearest_support: float = 0
    
    def calculate_confluence(self):
        """Calculate MTF confluence and short entry score"""
        timeframes = [
            self.tf_1m, self.tf_5m, self.tf_15m, 
            self.tf_1h, self.tf_4h
        ]
        
        bullish = 0
        bearish = 0
        overbought_count = 0
        overextended_count = 0
        
        for tf in timeframes:
            if tf is None:
                continue
            
            # Count trends
            if tf.trend in [Trend.STRONG_UP, Trend.UP]:
                bullish += 1
            elif tf.trend in [Trend.STRONG_DOWN, Trend.DOWN]:
                bearish += 1
            
            # Count overbought RSI (good for short)
            if tf.rsi > 70:
                overbought_count += 1
            
            # Count overextended (good for short)
            if tf.ema20_extension_pct > 5:
                overextended_count += 1
        
        self.bullish_count = bullish
        self.bearish_count = bearish
        
        # Determine signal strength for SHORT
        # Best short: lower TFs bullish (pump), higher TFs bearish/neutral
        lower_tf_bullish = 0
        higher_tf_bearish = 0
        
        if self.tf_1m and self.tf_1m.trend in [Trend.STRONG_UP, Trend.UP]:
            lower_tf_bullish += 1
        if self.tf_5m and self.tf_5m.trend in [Trend.STRONG_UP, Trend.UP]:
            lower_tf_bullish += 1
        
        if self.tf_1h and self.tf_1h.trend in [Trend.STRONG_DOWN, Trend.DOWN, Trend.NEUTRAL]:
            higher_tf_bearish += 1
        if self.tf_4h and self.tf_4h.trend in [Trend.STRONG_DOWN, Trend.DOWN, Trend.NEUTRAL]:
            higher_tf_bearish += 1
        
        # Perfect short: pump on low TF against higher TF trend
        if lower_tf_bullish >= 2 and higher_tf_bearish >= 1:
            self.signal_strength = SignalStrength.PERFECT
        elif lower_tf_bullish >= 1 and higher_tf_bearish >= 1:
            self.signal_strength = SignalStrength.STRONG
        elif overbought_count >= 2:
            self.signal_strength = SignalStrength.MODERATE
        elif bullish >= 3:
            self.signal_strength = SignalStrength.WEAK  # Pure pump, risky short
        else:
            self.signal_strength = SignalStrength.CONFLICTING
        
        # Calculate short entry score
        score = 50  # Base score
        
        # Overbought bonus
        score += overbought_count * 10
        
        # Overextended bonus
        score += overextended_count * 8
        
        # HTF against the pump bonus
        score += higher_tf_bearish * 12
        
        # Pure momentum penalty (chasing)
        if bullish >= 4:
            score -= 15
        
        self.short_entry_score = min(100, max(0, score))
    
    def get_summary(self) -> Dict:
        """Get summary of MTF analysis"""
        return {
            'symbol': self.symbol,
            'signal_strength': self.signal_strength.name,
            'short_entry_score': self.short_entry_score,
            'bullish_tf_count': self.bullish_count,
            'bearish_tf_count': self.bearish_count,
            'timeframes': {
                '1m': self.tf_1m.trend.value if self.tf_1m else None,
                '5m': self.tf_5m.trend.value if self.tf_5m else None,
                '15m': self.tf_15m.trend.value if self.tf_15m else None,
                '1h': self.tf_1h.trend.value if self.tf_1h else None,
                '4h': self.tf_4h.trend.value if self.tf_4h else None,
            }
        }


class MTFAnalyzer:
    """
    Multi-timeframe analyzer
    Analyzes price action across 1m, 5m, 15m, 1h, 4h
    """
    
    def __init__(self, client):
        self.client = client
        
        # Cache for kline data
        self.kline_cache: Dict[str, Dict[str, List]] = {}  # symbol -> timeframe -> klines
    
    async def analyze_symbol(self, symbol: str) -> MTFAnalysis:
        """
        Perform multi-timeframe analysis for symbol
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            MTFAnalysis with all timeframe data
        """
        import time as time_module
        
        analysis = MTFAnalysis(
            symbol=symbol,
            timestamp=int(time_module.time() * 1000)
        )
        
        # Fetch klines for each timeframe
        timeframe_map = {
            'Min1': 'tf_1m',
            'Min5': 'tf_5m', 
            'Min15': 'tf_15m',
            'Hour1': 'tf_1h',
            'Hour4': 'tf_4h'
        }
        
        for mexc_tf, attr_name in timeframe_map.items():
            try:
                klines = await self.client.get_klines(symbol, mexc_tf, 200)
                
                if klines:
                    prices = [k.close for k in klines]
                    volumes = [k.volume for k in klines]
                    
                    tf_analysis = TimeframeAnalysis(
                        timeframe=mexc_tf,
                        prices=prices,
                        volumes=volumes
                    )
                    tf_analysis.analyze()
                    
                    setattr(analysis, attr_name, tf_analysis)
                
                await asyncio.sleep(0.05)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error fetching {mexc_tf} for {symbol}: {e}")
        
        # Calculate confluence
        analysis.calculate_confluence()
        
        return analysis
    
    async def quick_scan(self, symbols: List[str]) -> List[Tuple[str, MTFAnalysis]]:
        """
        Quick scan multiple symbols for best short opportunities
        
        Returns:
            List of (symbol, analysis) sorted by short entry score
        """
        results = []
        
        for symbol in symbols:
            try:
                analysis = await self.analyze_symbol(symbol)
                results.append((symbol, analysis))
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
        
        # Sort by short entry score (highest first)
        results.sort(key=lambda x: x[1].short_entry_score, reverse=True)
        
        return results

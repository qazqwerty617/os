"""
MEXC Pump Monitor - ULTIMATE PATTERN & GRAPHICAL ENGINE v3.0
Combines:
1. Pro-Grade Geometric Analysis (Math-based Trendlines, Flags, Wedges)
2. Candlestick Patterns (Hammer, Engulfing, Stars)
3. Smart Money Concepts (FVG, Order Blocks, Liquidity)
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class PatternType(Enum):
    # --- GEOMETRIC (CLASSIC) ---
    HEAD_AND_SHOULDERS = "Head & Shoulders (Bear)"
    INV_HEAD_AND_SHOULDERS = "Inv Head & Shoulders (Bull)"
    DOUBLE_TOP = "Double Top"
    DOUBLE_BOTTOM = "Double Bottom"
    TRIPLE_TOP = "Triple Top"
    TRIPLE_BOTTOM = "Triple Bottom"
    RISING_WEDGE = "Rising Wedge (Bear)"
    FALLING_WEDGE = "Falling Wedge (Bull)"
    BULL_FLAG = "Bull Flag"
    BEAR_FLAG = "Bear Flag" 
    BULL_PENNANT = "Bull Pennant"
    BEAR_PENNANT = "Bear Pennant"
    ASCENDING_TRIANGLE = "Ascending Triangle"
    DESCENDING_TRIANGLE = "Descending Triangle"
    SYMMETRICAL_TRIANGLE = "Symmetrical Triangle"
    CUP_AND_HANDLE = "Cup & Handle"
    DIAMOND = "Diamond"
    MEGAPHONE = "Megaphone"
    RECTANGLE = "Rectangle/Range"
    
    # --- CANDLESTICK ---
    HAMMER = "Hammer"
    SHOOTING_STAR = "Shooting Star" 
    BULLISH_ENGULFING = "Bull Engulfing"
    BEARISH_ENGULFING = "Bear Engulfing"
    MORNING_STAR = "Morning Star"
    EVENING_STAR = "Evening Star"
    DOJI = "Doji"
    PINBAR = "Pinbar"
    INSIDE_BAR = "Inside Bar"
    MARUBOZU = "Marubozu"
    
    # --- SMART MONEY (SMC) ---
    FVG_BULLISH = "FVG Bull (Imbalance)"
    FVG_BEARISH = "FVG Bear (Imbalance)"
    ORDER_BLOCK_BULL = "Bullish OB"
    ORDER_BLOCK_BEAR = "Bearish OB"
    BOS_BULLISH = "BOS Bull"
    BOS_BEARISH = "BOS Bear"
    LIQUIDITY_GRAB = "Liquidity Grab"

@dataclass
class DetectedPattern:
    pattern_type: PatternType
    symbol: str
    confidence: float   # 0-100%
    price_target: float
    stop_loss: float
    timestamp: int
    info: str = ""

class AdvancedPatternScanner:
    """
    🧠 The Brain of Technical Analysis
    """
    
    def __init__(self):
        pass

    def find_patterns(
        self, 
        symbol: str, 
        opens: Union[List[float], np.ndarray], 
        highs: Union[List[float], np.ndarray], 
        lows: Union[List[float], np.ndarray], 
        closes: Union[List[float], np.ndarray], 
        volumes: Union[List[float], np.ndarray],
        times: Union[List[int], np.ndarray]
    ) -> List[DetectedPattern]:
        
        # Data Prep
        if isinstance(closes, list): closes = np.array(closes)
        if isinstance(opens, list): opens = np.array(opens)
        if isinstance(highs, list): highs = np.array(highs)
        if isinstance(lows, list): lows = np.array(lows)
        if isinstance(volumes, list): volumes = np.array(volumes)
        if isinstance(times, list): times = np.array(times)
        
        if len(closes) < 50: return []
        
        detected = []
        current_price = closes[-1]
        
        # 1. GEOMETRIC SCAN (ZigZag + Polyfit)
        pivots = self._get_pivots(highs, lows, order=5)
        trend_slope = self._get_trend_slope(closes[-50:])
        
        detected.extend(self._scan_geometry(symbol, pivots, closes, highs, lows, trend_slope))
        
        # 2. CANDLESTICK SCAN (Last 1-3 bars)
        detected.extend(self._scan_candles(symbol, opens, highs, lows, closes))
        
        # 3. SMC SCAN (Structure & Logs)
        detected.extend(self._scan_smc(symbol, opens, highs, lows, closes, volumes))
        
        # Post-processing
        # Assign timestamp if missing
        last_ts = times[-1] if len(times) > 0 else 0
        for p in detected:
            if p.timestamp == 0:
                p.timestamp = last_ts
                
        # Filter low confidence
        return [p for p in detected if p.confidence >= 65]

    # ================= 1. GEOMETRIC ENGINE =================
    
    def _scan_geometry(self, symbol, pivots, closes, highs, lows, trend_slope) -> List[DetectedPattern]:
        patterns = []
        
        # A. Triangles/Wedges (Slope Convergence)
        ph = pivots['highs'][-3:]
        pl = pivots['lows'][-3:]
        if len(ph) >= 2 and len(pl) >= 2:
            h_slope = self._get_slope(ph)
            l_slope = self._get_slope(pl)
            
            # Symmetrical Triangle
            if h_slope < -0.0005 and l_slope > 0.0005:
                if abs(h_slope) + abs(l_slope) > 0.003: # Strong enough convergence
                    patterns.append(DetectedPattern(
                        PatternType.SYMMETRICAL_TRIANGLE, symbol, 75,
                        closes[-1] + (ph[-1][1]-pl[-1][1]), # Target range
                        pl[-1][1], 0, f"Slopes: {h_slope:.4f}/{l_slope:.4f}"
                    ))
            
            # Ascending Triangle
            elif abs(h_slope) < 0.0005 and l_slope > 0.001:
                patterns.append(DetectedPattern(
                    PatternType.ASCENDING_TRIANGLE, symbol, 80,
                    ph[-1][1] * 1.05, pl[-1][1], 0, "Flat Top, Rising Lows"
                ))
            
            # Falling Wedge
            elif h_slope < -0.001 and l_slope < -0.0005 and h_slope < l_slope:
                patterns.append(DetectedPattern(
                    PatternType.FALLING_WEDGE, symbol, 85,
                    ph[0][1], pl[-1][1], 0, "Bullish Reversal Setup"
                ))
                
        # B. Flags (context based)
        # Check pole
        pole_slope = self._get_trend_slope(closes[-50:-15])
        recent_slope = self._get_trend_slope(closes[-15:])
        
        if pole_slope > 0.004 and -0.003 < recent_slope < 0: # Bull Flag
             patterns.append(DetectedPattern(
                 PatternType.BULL_FLAG, symbol, 85,
                 closes[-1] * 1.10, min(lows[-15:]), 0, "Impulse + Consolidation"
             ))

        # C. Head & Shoulders (Logic from v2 refined)
        if len(ph) >= 3 and len(pl) >= 2:
            LS, Head, RS = ph[0], ph[1], ph[2]
            N1, N2 = pl[0], pl[1]
            if Head[1] > LS[1] and Head[1] > RS[1]:
                if abs(LS[1]-RS[1])/Head[1] < 0.1: # Symmetry
                    patterns.append(DetectedPattern(
                        PatternType.HEAD_AND_SHOULDERS, symbol, 90,
                        N2[1] - (Head[1]-N2[1]), Head[1], 0, "Bearish Reversal"
                    ))

        return patterns

    # ================= 2. CANDLESTICK ENGINE =================
    
    def _scan_candles(self, symbol, opens, highs, lows, closes) -> List[DetectedPattern]:
        patterns = []
        i = -1
        O, H, L, C = opens[i], highs[i], lows[i], closes[i]
        body = abs(C - O)
        total = H - L if H != L else 0.00001
        
        # Hammer (Bullish Pinbar)
        # Lower wick > 2x body, Upper wick small
        lower_wick = min(O, C) - L
        upper_wick = H - max(O, C)
        
        if lower_wick > 2 * body and upper_wick < 0.5 * body:
            # Check context: must be at support/low
            # Simple check: lower than prev low
            if L < lows[i-1]:
                patterns.append(DetectedPattern(
                    PatternType.HAMMER, symbol, 75,
                    H + body*2, L, 0, "Rejection from lows"
                ))
                
        # Bearish Engulfing
        O_prev, C_prev = opens[i-1], closes[i-1]
        if C_prev > O_prev: # Prev Green
            if C < O: # Curr Red
                if O >= C_prev and C <= O_prev: # Engulfs body
                    patterns.append(DetectedPattern(
                        PatternType.BEARISH_ENGULFING, symbol, 80,
                        L - (H-L), H, 0, "Momentum Shift"
                    ))
                    
        return patterns

    # ================= 3. SMC ENGINE =================
    
    def _scan_smc(self, symbol, opens, highs, lows, closes, volumes) -> List[DetectedPattern]:
        patterns = []
        
        # FVG (Fair Value Gap)
        # Bullish: High[i-2] < Low[i]
        if len(highs) > 3:
            gap = lows[-1] - highs[-3]
            if gap > (highs[-1]-lows[-1])*0.1: # Significant gap
                patterns.append(DetectedPattern(
                    PatternType.FVG_BULLISH, symbol, 80,
                    highs[-3], lows[-1], 0, f"Imbalance: {gap:.4f}"
                ))
                
        # Order Block (Bullish)
        # Last Bear candle before BOS (break of structure)
        # Simplified: Big green candle engulfing previous small red
        if closes[-1] > opens[-1] and (closes[-1]-opens[-1]) > (highs[-1]-lows[-1])*0.8: # Strong green
            if closes[-2] < opens[-2]: # Prev red
                 patterns.append(DetectedPattern(
                     PatternType.ORDER_BLOCK_BULL, symbol, 70,
                     0, lows[-2], 0, "Demand Zone Created"
                 ))
                 
        return patterns

    # ================= UTILS =================
    
    def _get_pivots(self, highs, lows, order=5):
        h_idx, l_idx = [], []
        for i in range(order, len(highs)-order):
            if highs[i] == max(highs[i-order:i+order+1]):
                h_idx.append((i, highs[i]))
            if lows[i] == min(lows[i-order:i+order+1]):
                l_idx.append((i, lows[i]))
        return {'highs': h_idx, 'lows': l_idx}
        
    def _get_trend_slope(self, series):
        if len(series) < 2: return 0
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series, 1)
        return slope / series[0]
        
    def _get_slope(self, points):
        if len(points) < 2: return 0
        x = [p[0] for p in points]
        y = [p[1] for p in points]
        slope, _ = np.polyfit(x, y, 1)
        return slope / y[0]

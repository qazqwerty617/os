"""
MEXC Pump Monitor - Technical Indicators
RSI, EMA, Volume analysis, and divergence detection
"""

import numpy as np
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class IndicatorResult:
    """Container for indicator calculations"""
    rsi: float
    ema20: float
    ema_extension_pct: float
    volume_ratio: float
    momentum: float
    is_divergence: bool
    divergence_type: Optional[str]  # 'bullish' or 'bearish'


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """
    Calculate Relative Strength Index
    
    Args:
        prices: List of closing prices (oldest first)
        period: RSI period (default 14)
    
    Returns:
        RSI value (0-100)
    """
    if len(prices) < period + 1:
        return 50.0  # Neutral if not enough data
    
    prices_arr = np.array(prices)
    deltas = np.diff(prices_arr)
    
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    # Use exponential moving average for smoothing
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)


def calculate_ema(prices: List[float], period: int = 20) -> float:
    """
    Calculate Exponential Moving Average
    
    Args:
        prices: List of closing prices (oldest first)
        period: EMA period (default 20)
    
    Returns:
        EMA value
    """
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    
    prices_arr = np.array(prices)
    multiplier = 2 / (period + 1)
    
    # Start with SMA
    ema = np.mean(prices_arr[:period])
    
    # Calculate EMA
    for price in prices_arr[period:]:
        ema = (price - ema) * multiplier + ema
    
    return ema


def calculate_extension(current_price: float, ema: float) -> float:
    """
    Calculate price extension from EMA as percentage
    
    Args:
        current_price: Current price
        ema: EMA value
    
    Returns:
        Extension percentage (positive = above EMA)
    """
    if ema == 0:
        return 0.0
    
    return round(((current_price - ema) / ema) * 100, 2)


def calculate_volume_ratio(
    current_volume: float,
    historical_volumes: List[float]
) -> float:
    """
    Calculate current volume as ratio of average
    
    Args:
        current_volume: Current candle volume
        historical_volumes: List of historical volumes
    
    Returns:
        Volume ratio (1.0 = average, 3.0 = 300% of average)
    """
    if not historical_volumes:
        return 1.0
    
    avg_volume = np.mean(historical_volumes)
    
    if avg_volume == 0:
        return 1.0
    
    return round(current_volume / avg_volume, 2)


def calculate_momentum(prices: List[float], period: int = 10) -> float:
    """
    Calculate momentum (Rate of Change)
    
    Args:
        prices: List of closing prices
        period: Lookback period
    
    Returns:
        Momentum as percentage change
    """
    if len(prices) < period + 1:
        return 0.0
    
    old_price = prices[-(period + 1)]
    current_price = prices[-1]
    
    if old_price == 0:
        return 0.0
    
    return round(((current_price - old_price) / old_price) * 100, 2)


def detect_divergence(
    prices: List[float],
    rsi_values: List[float],
    lookback: int = 10
) -> Tuple[bool, Optional[str]]:
    """
    Detect RSI divergence
    
    Args:
        prices: List of closing prices
        rsi_values: List of RSI values
        lookback: Number of periods to look back
    
    Returns:
        Tuple of (is_divergence, divergence_type)
        divergence_type: 'bullish' or 'bearish' or None
    """
    if len(prices) < lookback or len(rsi_values) < lookback:
        return False, None
    
    recent_prices = prices[-lookback:]
    recent_rsi = rsi_values[-lookback:]
    
    # Find local highs and lows
    price_high_idx = np.argmax(recent_prices)
    price_low_idx = np.argmin(recent_prices)
    
    # Check for bearish divergence (price higher high, RSI lower high)
    if price_high_idx == len(recent_prices) - 1:  # Current is highest
        # Look for previous high
        for i in range(len(recent_prices) - 2, 0, -1):
            if recent_prices[i] > recent_prices[i-1] and recent_prices[i] > recent_prices[i+1]:
                # Found previous local high
                if recent_prices[-1] > recent_prices[i] and recent_rsi[-1] < recent_rsi[i]:
                    return True, 'bearish'
                break
    
    # Check for bullish divergence (price lower low, RSI higher low)
    if price_low_idx == len(recent_prices) - 1:  # Current is lowest
        for i in range(len(recent_prices) - 2, 0, -1):
            if recent_prices[i] < recent_prices[i-1] and recent_prices[i] < recent_prices[i+1]:
                if recent_prices[-1] < recent_prices[i] and recent_rsi[-1] > recent_rsi[i]:
                    return True, 'bullish'
                break
    
    return False, None


def calculate_all_indicators(
    prices: List[float],
    volumes: List[float],
    current_volume: float,
    rsi_period: int = 14,
    ema_period: int = 20
) -> IndicatorResult:
    """
    Calculate all indicators at once
    
    Args:
        prices: Historical closing prices (oldest first)
        volumes: Historical volumes
        current_volume: Current candle volume
        rsi_period: RSI calculation period
        ema_period: EMA calculation period
    
    Returns:
        IndicatorResult with all calculated values
    """
    current_price = prices[-1] if prices else 0.0
    
    # Calculate RSI
    rsi = calculate_rsi(prices, rsi_period)
    
    # Calculate EMA and extension
    ema20 = calculate_ema(prices, ema_period)
    extension = calculate_extension(current_price, ema20)
    
    # Calculate volume ratio
    volume_ratio = calculate_volume_ratio(current_volume, volumes)
    
    # Calculate momentum
    momentum = calculate_momentum(prices)
    
    # Calculate RSI series for divergence detection
    rsi_values = []
    for i in range(max(0, len(prices) - 20), len(prices)):
        rsi_values.append(calculate_rsi(prices[:i+1], rsi_period))
    
    # Detect divergence
    is_div, div_type = detect_divergence(prices[-20:], rsi_values)
    
    return IndicatorResult(
        rsi=rsi,
        ema20=ema20,
        ema_extension_pct=extension,
        volume_ratio=volume_ratio,
        momentum=momentum,
        is_divergence=is_div,
        divergence_type=div_type
    )

"""
Tests for pump detector indicators
"""

import pytest
from indicators import (
    calculate_rsi,
    calculate_ema,
    calculate_extension,
    calculate_volume_ratio,
    calculate_momentum,
    detect_divergence,
    calculate_all_indicators
)


class TestRSI:
    """Test RSI calculations"""
    
    def test_rsi_overbought(self):
        """Rising prices should give high RSI"""
        prices = list(range(100, 120))  # Steadily rising
        rsi = calculate_rsi(prices)
        assert rsi > 70, f"Expected RSI > 70 for rising prices, got {rsi}"
    
    def test_rsi_oversold(self):
        """Falling prices should give low RSI"""
        prices = list(range(120, 100, -1))  # Steadily falling
        rsi = calculate_rsi(prices)
        assert rsi < 30, f"Expected RSI < 30 for falling prices, got {rsi}"
    
    def test_rsi_neutral(self):
        """Sideways prices should give neutral RSI"""
        prices = [100, 101, 100, 101, 100, 101, 100, 101, 100, 101,
                  100, 101, 100, 101, 100, 101, 100, 101, 100, 101]
        rsi = calculate_rsi(prices)
        assert 40 < rsi < 60, f"Expected neutral RSI, got {rsi}"
    
    def test_rsi_insufficient_data(self):
        """With insufficient data, return neutral"""
        prices = [100, 101, 102]
        rsi = calculate_rsi(prices)
        assert rsi == 50.0


class TestEMA:
    """Test EMA calculations"""
    
    def test_ema_basic(self):
        """EMA should be calculated correctly"""
        prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 
                  20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
        ema = calculate_ema(prices, 20)
        # EMA should be close to recent average
        assert 20 < ema < 30
    
    def test_ema_insufficient_data(self):
        """With insufficient data, return last price"""
        prices = [100, 101, 102]
        ema = calculate_ema(prices, 20)
        assert ema == 102


class TestExtension:
    """Test price extension calculations"""
    
    def test_extension_above_ema(self):
        """Price above EMA should give positive extension"""
        ext = calculate_extension(110, 100)
        assert ext == 10.0
    
    def test_extension_below_ema(self):
        """Price below EMA should give negative extension"""
        ext = calculate_extension(90, 100)
        assert ext == -10.0
    
    def test_extension_at_ema(self):
        """Price at EMA should give zero"""
        ext = calculate_extension(100, 100)
        assert ext == 0.0


class TestVolumeRatio:
    """Test volume ratio calculations"""
    
    def test_volume_spike(self):
        """High volume should give ratio > 1"""
        current = 1000
        historical = [100] * 20
        ratio = calculate_volume_ratio(current, historical)
        assert ratio == 10.0
    
    def test_low_volume(self):
        """Low volume should give ratio < 1"""
        current = 50
        historical = [100] * 20
        ratio = calculate_volume_ratio(current, historical)
        assert ratio == 0.5
    
    def test_normal_volume(self):
        """Average volume should give ratio ~1"""
        current = 100
        historical = [100] * 20
        ratio = calculate_volume_ratio(current, historical)
        assert ratio == 1.0


class TestMomentum:
    """Test momentum calculations"""
    
    def test_positive_momentum(self):
        """Rising prices should give positive momentum"""
        prices = list(range(100, 121))  # 20% rise
        momentum = calculate_momentum(prices, 10)
        assert momentum > 0
    
    def test_negative_momentum(self):
        """Falling prices should give negative momentum"""
        prices = list(range(120, 99, -1))  # 20% fall
        momentum = calculate_momentum(prices, 10)
        assert momentum < 0


class TestAllIndicators:
    """Test combined indicator calculation"""
    
    def test_pump_scenario(self):
        """Test a typical pump scenario"""
        # Simulate pump: prices rising sharply
        base_prices = list(range(100, 110))
        pump_prices = [110, 115, 120, 130, 145, 160]
        prices = base_prices + pump_prices
        
        volumes = [1000] * 10 + [5000] * 6  # Volume spike during pump
        
        result = calculate_all_indicators(
            prices=prices,
            volumes=volumes[:-1],
            current_volume=volumes[-1]
        )
        
        assert result.rsi > 70, "RSI should be overbought"
        assert result.volume_ratio > 1, "Volume should be elevated"
        assert result.momentum > 0, "Momentum should be positive"
        assert result.ema_extension_pct > 0, "Price should be extended above EMA"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

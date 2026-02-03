"""
Tests for pump detector
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pump_detector import PumpDetector, PumpSignal, PriceHistory


class TestPriceHistory:
    """Test price history tracking"""
    
    def test_add_data(self):
        """Test adding price data"""
        history = PriceHistory()
        history.add(100, 1000, 1000000)
        
        assert len(history.prices) == 1
        assert history.prices[0] == 100
    
    def test_max_length(self):
        """Test that history is trimmed to max length"""
        history = PriceHistory(max_length=10)
        
        for i in range(20):
            history.add(100 + i, 1000, 1000000 + i)
        
        assert len(history.prices) == 10
        assert history.prices[0] == 110  # First 10 should be trimmed
    
    def test_price_change(self):
        """Test price change calculation"""
        history = PriceHistory()
        
        # Add data points 5 minutes apart (300000 ms)
        import time
        base_time = int(time.time() * 1000) - 600000  # 10 mins ago
        
        for i in range(10):
            history.add(100 + i, 1000, base_time + i * 60000)
        
        # Should detect price increase
        change = history.get_price_change(5)
        assert change >= 0


class TestPumpSignal:
    """Test pump signal construction"""
    
    def test_signal_creation(self):
        """Test creating a pump signal"""
        signal = PumpSignal(
            symbol='TEST_USDT',
            timestamp=1000000,
            price=100.0,
            price_change_pct=15.0,
            price_5min_ago=87.0,
            volume_ratio=5.0,
            volume_usd=1000000,
            rsi=85.0,
            ema20=90.0,
            ema_extension_pct=11.1,
            momentum=15.0,
            has_divergence=True,
            divergence_type='bearish',
            score=85
        )
        
        assert signal.symbol == 'TEST_USDT'
        assert signal.score == 85
        assert signal.entry_zone_low > 0
        assert signal.stop_loss > signal.price
        assert signal.take_profit < signal.price
    
    def test_signal_to_dict(self):
        """Test signal serialization"""
        signal = PumpSignal(
            symbol='TEST_USDT',
            timestamp=1000000,
            price=100.0,
            price_change_pct=15.0,
            price_5min_ago=87.0,
            volume_ratio=5.0,
            volume_usd=1000000,
            rsi=85.0,
            ema20=90.0,
            ema_extension_pct=11.1,
            momentum=15.0,
            has_divergence=False,
            divergence_type=None,
            score=85
        )
        
        data = signal.to_dict()
        
        assert 'symbol' in data
        assert 'score' in data
        assert 'entry_zone' in data


class TestPumpDetector:
    """Test pump detector logic"""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock MEXC client"""
        client = Mock()
        client.symbols = {'TEST_USDT': Mock()}
        client.tickers = {}
        client.get_tickers = AsyncMock(return_value=[])
        client.get_klines = AsyncMock(return_value=[])
        client.on_ticker = Mock()
        return client
    
    def test_detector_creation(self, mock_client):
        """Test detector instantiation"""
        detector = PumpDetector(mock_client)
        
        assert detector.client == mock_client
        assert len(detector.active_signals) == 0
    
    def test_score_calculation_high(self, mock_client):
        """Test score calculation for strong pump"""
        detector = PumpDetector(mock_client)
        
        from indicators import IndicatorResult
        
        indicators = IndicatorResult(
            rsi=90.0,
            ema20=100.0,
            ema_extension_pct=10.0,
            volume_ratio=6.0,
            momentum=20.0,
            is_divergence=True,
            divergence_type='bearish'
        )
        
        score, breakdown = detector._calculate_score(indicators, 20.0)
        
        assert score >= 80, f"Expected high score, got {score}"
        assert breakdown['rsi'] == 100
        assert breakdown['divergence'] == 20
    
    def test_score_calculation_low(self, mock_client):
        """Test score calculation for weak pump"""
        detector = PumpDetector(mock_client)
        
        from indicators import IndicatorResult
        
        indicators = IndicatorResult(
            rsi=65.0,
            ema20=100.0,
            ema_extension_pct=2.0,
            volume_ratio=1.5,
            momentum=5.0,
            is_divergence=False,
            divergence_type=None
        )
        
        score, breakdown = detector._calculate_score(indicators, 5.0)
        
        assert score < 70, f"Expected low score, got {score}"
    
    def test_get_stats(self, mock_client):
        """Test statistics retrieval"""
        detector = PumpDetector(mock_client)
        
        stats = detector.get_stats()
        
        assert 'total_checked' in stats
        assert 'pumps_detected' in stats
        assert 'signals_generated' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

"""
MEXC Pump Monitor - Configuration
All settings for pump detection, scoring, and notifications
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

# Load environment variables from .env
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


@dataclass
class PumpConfig:
    """Pump detection thresholds - MEMECOIN OPTIMIZED"""
    
    # Multi-tier pump detection - оптимизировано для мемкоинов
    pump_tiers: dict = field(default_factory=lambda: {
        'MEGA': {'min_pct': 100.0, 'time_min': 50, 'priority': 1},  # 100%+ за 10 мин
        'MASSIVE': {'min_pct': 20.0, 'time_min': 20, 'priority': 2},  # 30%+ за 5 мин
        'STRONG': {'min_pct': 12.0, 'time_min': 5, 'priority': 3},  # 10%+ за 3 мин
        'EARLY': {'min_pct': 8.0, 'time_min': 3, 'priority': 4},     # 3%+ за 1 мин - РАННЕЕ ОБНАРУЖЕНИЕ
    })
    
    # Main thresholds - АГРЕССИВНО для мемкоинов
    min_price_change_pct: float = 3.0  # 3% минимум (было 1%)
    time_window_minutes: int = 3  # 3 минуты окно (было 5)
    
    # Micro-pump detection (catch the start) - СУПЕР РАННЕЕ
    micro_pump_pct: float = 1.5  # 1.5% для раннего обнаружения
    micro_pump_window: int = 1   # 1 минута окно
    
    # Volume confirmation - ЛЕГЧЕ для мемкоинов
    min_volume_multiplier: float = 2.0   # 200% среднего (было 500%)
    extreme_volume_multiplier: float = 5.0  # 500% = MEGA pump (было 1000%)
    volume_avg_period_minutes: int = 30  # 30 минут средний объем (было 60)
    
    # Trade count (anti-manipulation)
    min_trades_multiplier: float = 3.0  # 300% of average trades
    
    # RSI thresholds - ОПТИМИЗИРОВАНО для мемкоинов
    rsi_period: int = 14
    rsi_overbought: float = 75.0   # Ниже порог для мемкоинов (было 80)
    rsi_extreme: float = 85.0      # Экстремальная зона (было 90)
    rsi_signal_zone: float = 80.0  # Лучшая зона для шорта (было 85)
    
    # Multi-timeframe
    timeframes: tuple = ('Min1', 'Min5', 'Min15', 'Hour1')
    
    # Open Interest spike detection
    oi_spike_multiplier: float = 2.0  # 200% OI increase = significant
    
    # Funding rate extremes
    funding_rate_extreme: float = 0.1  # 0.1% = extremely high funding


@dataclass
class ScoringConfig:
    """Signal scoring configuration"""
    min_score_threshold: int = 70  # Minimum score to generate alert
    
    # RSI scoring
    rsi_excellent: float = 85.0  # Score 100
    rsi_good: float = 75.0  # Score 70
    rsi_weak: float = 65.0  # Score 40
    
    # Extension from EMA20
    extension_excellent_pct: float = 8.0
    extension_good_pct: float = 5.0
    extension_weak_pct: float = 3.0
    
    # Volume decline from peak
    volume_decline_excellent_pct: float = 30.0
    volume_decline_good_pct: float = 15.0


@dataclass
class FilterConfig:
    """Signal filtering rules - OPTIMIZED FOR MEMECOINS"""
    # Exclude new listings (reduced for memecoins)
    min_listing_days: int = 1  # Мемкоины могут быть новыми
    
    # Volume filters (daily USD) - ЛЕГКИЕ для мемкоинов
    min_daily_volume_usd: float = 50_000  # $50K minimum (было $1M)
    max_daily_volume_usd: float = 500_000_000  # $500M maximum (увеличено для топ мемкоинов)
    
    # Exclude stable coins and specific tokens
    excluded_symbols: tuple = (
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD',  # Stablecoins
        'BTCUSDT',  # Too stable for pumps
    )
    
    # Memecoin specific settings
    allow_low_volume: bool = True  # Разрешить низкий объем для мемкоинов
    min_volume_multiplier: float = 2.0  # Минимум 2x среднего объема (было 5x)
    max_spread_pct: float = 0.35  # 0.35% максимум спред
    min_orderbook_depth_usd: float = 10_000.0  # Минимум ликвидности в обеих сторонах (суммарно топ-10)
    whale_pressure_short_max: int = 40  # Для шорта: максимум 40% buy-pressure у китов


@dataclass
class MEXCConfig:
    """MEXC API configuration - REST ONLY"""
    # REST API - FUTURES
    rest_base_url: str = "https://contract.mexc.com"
    
    # API credentials (optional for public endpoints)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Rate limiting - 20 requests/sec
    max_requests_per_second: int = 20
    request_interval: float = 0.05
    
    # Polling intervals
    pump_scan_interval: float = 1.0  # Pump detection scan every 1 sec
    market_scan_interval: float = 2.0  # General market scan every 2 sec
    use_rest_aggressive: bool = True
    polling_interval: float = 0.5
    
    def __post_init__(self):
        self.api_key = os.getenv('MEXC_API_KEY')
        self.api_secret = os.getenv('MEXC_API_SECRET')


@dataclass
class TelegramConfig:
    """Telegram notification settings"""
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: bool = False
    
    def __post_init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.bot_token and self.chat_id)


@dataclass
class DeepSeekConfig:
    """DeepSeek API configuration"""
    api_key: Optional[str] = None
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"
    
    def __post_init__(self):
        self.api_key = os.getenv('DEEPSEEK_API_KEY')

@dataclass
class DashboardConfig:
    """Web dashboard settings"""
    host: str = "0.0.0.0"
    port: int = 8080
    public_url: Optional[str] = None
    debug: bool = False

    def __post_init__(self):
        self.public_url = os.getenv('PUBLIC_URL')


class Config:
    """Main configuration container"""
    
    def __init__(self):
        self.pump = PumpConfig()
        self.scoring = ScoringConfig()
        self.filters = FilterConfig()
        self.mexc = MEXCConfig()
        self.telegram = TelegramConfig()
        self.deepseek = DeepSeekConfig()
        self.dashboard = DashboardConfig()
        
        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'pump_monitor.log')


# Global config instance
config = Config()

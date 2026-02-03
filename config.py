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
    """Pump detection thresholds - AGGRESSIVE MODE for life-changing trades"""
    
    # Multi-tier pump detection
    pump_tiers: dict = field(default_factory=lambda: {
        'MEGA': {'min_pct': 50.0, 'time_min': 15, 'priority': 1},
        'MASSIVE': {'min_pct': 5.0, 'time_min': 10, 'priority': 2}, # Lowered for test
        'STRONG': {'min_pct': 2.0, 'time_min': 5, 'priority': 3},   # Lowered for test
        'EARLY': {'min_pct': 1.0, 'time_min': 3, 'priority': 4},     # Lowered for test
    })
    
    # Main thresholds
    min_price_change_pct: float = 1.0  # 1% for test
    time_window_minutes: int = 5
    
    # Micro-pump detection (catch the start)
    micro_pump_pct: float = 0.5  # 0.5% for test
    micro_pump_window: int = 2   # 2 minutes
    
    # Volume confirmation - AGGRESSIVE 
    min_volume_multiplier: float = 5.0   # 500% of average = real pump
    extreme_volume_multiplier: float = 10.0  # 1000% = MEGA pump
    volume_avg_period_minutes: int = 60
    
    # Trade count (anti-manipulation)
    min_trades_multiplier: float = 3.0  # 300% of average trades
    
    # RSI thresholds - AGGRESSIVE
    rsi_period: int = 14
    rsi_overbought: float = 80.0   # Higher threshold
    rsi_extreme: float = 90.0      # Extreme zone
    rsi_signal_zone: float = 85.0  # Best short entry zone
    
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
    """Signal filtering rules"""
    # Exclude new listings
    min_listing_days: int = 7
    
    # Volume filters (daily USD)
    min_daily_volume_usd: float = 1_000_000  # $1M minimum
    max_daily_volume_usd: float = 50_000_000  # $50M maximum (mid-cap focus)
    
    # Exclude stable coins and specific tokens
    excluded_symbols: tuple = (
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD',  # Stablecoins
        'BTCUSDT',  # Too stable for pumps
    )


@dataclass
class MEXCConfig:
    """MEXC API configuration"""
    # REST API - FUTURES
    rest_base_url: str = "https://contract.mexc.com"
    
    # WebSocket - FUTURES
    ws_base_url: str = "wss://contract.mexc.com/edge"
    
    # API credentials (optional for public endpoints)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Rate limiting - быстрые запросы каждые 0.05 сек (20 в секунду)
    max_requests_per_second: int = 20
    request_interval: float = 0.05
    
    # Aggressive REST Mode (User Request)
    use_rest_aggressive: bool = True
    polling_interval: float = 0.05
    
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

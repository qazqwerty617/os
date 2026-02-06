"""
MEXC Pump Monitor - Configuration
All settings for pump detection, scoring, and notifications
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
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
    
    # Multi-tier pump detection - ТОЛЬКО МЕГА-ПАМПЫ
    pump_tiers: dict = field(default_factory=lambda: {
        'MEGA': {'min_pct': 50.0, 'time_min': 30, 'priority': 1},    # 50%+ за 30 мин
        'MASSIVE': {'min_pct': 20.0, 'time_min': 15, 'priority': 2}, # 20%+ за 15 мин
        'STRONG': {'min_pct': 10.0, 'time_min': 5, 'priority': 3},   # 10%+ за 5 мин
        'EARLY': {'min_pct': 8.0, 'time_min': 3, 'priority': 4},     # 8%+ за 3 мин
    })
    
    # Main thresholds - ТОЛЬКО МЕГА-ПАМПЫ
    min_price_change_pct: float = 8.0  # 8% минимум (EARLY tier)
    time_window_minutes: int = 3       # 3 минуты
    
    # Micro-pump detection (catch the start) - СУПЕР РАННЕЕ
    micro_pump_pct: float = 1.0  # 1.0% для раннего обнаружения
    micro_pump_window: int = 1   # 1 минута окно
    
    # Volume confirmation - ЛЕГЧЕ для мемкоинов
    min_volume_multiplier: float = 1.2   # 120% среднего (было 2.0)
    extreme_volume_multiplier: float = 3.0  # 300% = MEGA pump (было 5.0)
    volume_avg_period_minutes: int = 60  # 60 минут средний объем (было 30)
    
    # Trade count (anti-manipulation)
    min_trades_multiplier: float = 1.5  # 150% of average trades
    
    # RSI thresholds - ОПТИМИЗИРОВАНО для мемкоинов
    rsi_period: int = 14
    rsi_overbought: float = 65.0   # Ниже порог (было 75)
    rsi_extreme: float = 80.0      # Экстремальная зона (было 85)
    rsi_signal_zone: float = 75.0  # Лучшая зона (было 80)
    
    # Multi-timeframe
    timeframes: tuple = ('Min1', 'Min5', 'Min15', 'Hour1')
    
    # Open Interest spike detection
    oi_spike_multiplier: float = 1.5  # 150% OI increase
    
    # Funding rate extremes
    funding_rate_extreme: float = 0.05  # 0.05%


@dataclass
class ScoringConfig:
    """Signal scoring configuration"""
    min_score_threshold: int = 30  # СНИЖЕН порог (был 50)
    
    # RSI scoring
    rsi_excellent: float = 80.0  # Score 100
    rsi_good: float = 70.0  # Score 70
    rsi_weak: float = 60.0  # Score 40
    
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
    min_listing_days: int = 0  # Разрешить даже самые новые
    
    # Volume filters (daily USD) - ЛЕГКИЕ для мемкоинов
    min_daily_volume_usd: float = 10_000  # $10K minimum (было $50K)
    max_daily_volume_usd: float = 1_000_000_000  # $1B maximum
    
    # Exclude stable coins and specific tokens
    excluded_symbols: tuple = (
        'USDT', 'USDC', 'BUSD', 'DAI', 'TUSD',  # Stablecoins
    )
    
    # Memecoin specific settings
    allow_low_volume: bool = True
    min_volume_multiplier: float = 1.2  # Минимум 1.2x среднего объема


@dataclass
class MEXCConfig:
    """MEXC API configuration - REST ONLY"""
    # REST API - FUTURES
    rest_base_url: str = "https://contract.mexc.com"
    
    # API credentials (optional for public endpoints)
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    
    # Rate limiting - 50 requests/sec (Optimized for 8GB/4-core)
    max_requests_per_second: int = 50
    request_interval: float = 0.02
    
    # Polling intervals - ULTRA-FAST
    pump_scan_interval: float = 0.1  # 10 scans per second
    market_scan_interval: float = 1.0
    polling_interval: float = 0.1
    use_rest_aggressive: bool = True
    
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
class OpenRouterConfig:
    """OpenRouter AI configuration (Free Models)"""
    api_key: Optional[str] = None
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "google/gemini-2.0-flash-exp"
    
    def __post_init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')

@dataclass
class GroqConfig:
    """Groq AI configuration (FREE, FAST)"""
    api_keys: List[str] = field(default_factory=list)
    base_url: str = "https://api.groq.com/openai/v1"
    model: str = "llama-3.1-8b-instant"  # HIGHER LIMITS, ultra-fast for news translation
    
    def __post_init__(self):
        # Load multiple keys separated by comma
        raw_keys = os.getenv('GROQ_API_KEY', '')
        if raw_keys:
            self.api_keys = [k.strip() for k in raw_keys.split(',') if k.strip()]

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
        self.openrouter = OpenRouterConfig()
        self.groq = GroqConfig()
        self.dashboard = DashboardConfig()
        self.dashboard = DashboardConfig()
        
        # Logging
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
        self.log_file = os.getenv('LOG_FILE', 'pump_monitor.log')


# Global config instance
config = Config()

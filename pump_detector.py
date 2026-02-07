"""
MEXC Pump Monitor - Pump Detection Engine
Core logic for detecting pumps and scoring entry signals
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict, deque

from config import config
from indicators import calculate_all_indicators, IndicatorResult
from mexc_client import MEXCClient, Ticker, Kline

logger = logging.getLogger(__name__)


@dataclass
class PumpSignal:
    """Detected pump signal with scoring"""
    symbol: str
    timestamp: int
    
    # Price info
    price: float
    price_change_pct: float
    price_5min_ago: float
    time_window_min: int
    
    # Volume info
    volume_ratio: float
    volume_usd: float
    
    # Indicators
    rsi: float
    ema20: float
    ema_extension_pct: float
    momentum: float
    
    # Divergence
    has_divergence: bool
    divergence_type: Optional[str]
    
    # Scoring
    score: int  # 0-100
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    
    # Entry recommendation
    entry_zone_low: float = 0
    entry_zone_high: float = 0
    stop_loss: float = 0
    take_profit: float = 0
    
    def __post_init__(self):
        self._calculate_entry_levels()
    
    def _calculate_entry_levels(self):
        """Calculate recommended entry levels for short"""
        # Entry zone: current price +/- 1%
        self.entry_zone_low = self.price * 0.99
        self.entry_zone_high = self.price * 1.01
        
        # Stop loss: 4% above current price
        self.stop_loss = self.price * 1.04
        
        # Take profit: based on extension from EMA
        # Target: return to EMA20 + small buffer
        self.take_profit = self.ema20 * 1.01  # 1% above EMA
    
    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price': self.price,
            'price_change_pct': self.price_change_pct,
            'volume_ratio': self.volume_ratio,
            'volume_usd': self.volume_usd,
            'rsi': self.rsi,
            'ema_extension_pct': self.ema_extension_pct,
            'score': self.score,
            'score_breakdown': self.score_breakdown,
            'entry_zone': f"{self.entry_zone_low:.8f} - {self.entry_zone_high:.8f}",
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'has_divergence': self.has_divergence,
            'divergence_type': self.divergence_type
        }


@dataclass
class PriceHistory:
    """Track price history for a symbol"""
    prices: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    timestamps: List[int] = field(default_factory=list)
    max_length: int = 3000  # ~50 hours of 1m context (Optimized for 8GB RAM)
    
    def add(self, price: float, volume: float, timestamp: int):
        """Add new data point (aggregates same minute)"""
        # Convert to start of minute for aggregation
        minute_ts = (timestamp // 60000) * 60000
        
        if self.timestamps and (self.timestamps[-1] // 60000) * 60000 == minute_ts:
            # Update last point
            self.prices[-1] = price
            self.volumes[-1] += volume  # Accumulate volume
            self.timestamps[-1] = timestamp
        else:
            # Add new point
            self.prices.append(price)
            self.volumes.append(volume)
            self.timestamps.append(timestamp)
        
        # Trim to max length
        if len(self.prices) > self.max_length:
            self.prices = self.prices[-self.max_length:]
            self.volumes = self.volumes[-self.max_length:]
            self.timestamps = self.timestamps[-self.max_length:]
    
    def get_price_change(self, minutes: int) -> float:
        """Get price change over last N minutes"""
        if len(self.prices) < 2:
            return 0.0
        
        cutoff_time = time.time() * 1000 - (minutes * 60 * 1000)
        
        # Find price at cutoff time
        old_price = self.prices[-1]
        for i, ts in enumerate(self.timestamps):
            if ts >= cutoff_time:
                old_price = self.prices[i]
                break
        
        if old_price == 0:
            return 0.0
        
        current_price = self.prices[-1]
        return ((current_price - old_price) / old_price) * 100
    
    def get_volume_avg(self, periods: int) -> float:
        """Get average volume over last N periods"""
        if len(self.volumes) < periods:
            return 0.0
        return sum(self.volumes[-periods:]) / periods


class PumpDetector:
    """
    Main pump detection engine
    Monitors all symbols and generates alerts
    """
    
    def __init__(self, client: MEXCClient):
        self.client = client
        self.config = config
        
        # Price history per symbol
        self.history: Dict[str, PriceHistory] = defaultdict(PriceHistory)
        
        # Active signals
        self.active_signals: Dict[str, PumpSignal] = {}
        
        # Signal history (limited to prevent memory leak)
        self.signal_history: deque = deque(maxlen=100)
        
        # Cooldown to avoid duplicate signals - СНИЖЕН для мемкоинов
        self.cooldown: Dict[str, int] = {}  # symbol -> last signal timestamp
        self.cooldown_minutes = 5  # Было 15, стало 5 минут для мемкоинов
        
        # Callbacks for new signals
        self._signal_callbacks: List = []
        
        # Statistics
        self.stats = {
            'total_checked': 0,
            'pumps_detected': 0,
            'signals_generated': 0,
            'start_time': time.time()
        }
        
        # Track last volume to calculate deltas
        self.last_vol_24h: Dict[str, float] = {}
        self.last_tickers_ts: Dict[str, int] = {}
    
    def on_signal(self, callback):
        """Register callback for new signals"""
        self._signal_callbacks.append(callback)
    
    async def start(self):
        """Start pump detection - REST ONLY MODE"""
        logger.info("🚀 Starting pump detector (REST-ONLY MODE)...")
        
        # Initial data load
        await self._initial_load()
        
        # Start aggressive REST polling loop
        asyncio.create_task(self._scan_loop())
        
        logger.info("✅ Pump detector started (REST polling every 1s)")
    
    async def _initial_load(self):
        """Load initial kline data for all symbols (Parallel)"""
        symbols = self.client.get_active_symbols()
        logger.info(f"🚀 ULTRA-FAST LOAD: Fetching history for {len(symbols)} symbols...")
        
        start_time = time.time()
        semaphore = asyncio.Semaphore(20)  # Limit to 20 concurrent requests
        
        async def fetch_symbol(symbol):
             async with semaphore:
                 try:
                     # Only need last 50 candles for RSI/EMA
                     klines = await self.client.get_klines(symbol, 'Min1', 60)
                     if not klines: return
                     
                     history = self.history[symbol]
                     for k in klines:
                         history.add(k.close, k.volume, k.timestamp)
                         
                 except Exception as e:
                     logger.debug(f"Failed to load {symbol}: {e}")

        # Batch processing
        tasks = [fetch_symbol(s) for s in symbols]
        
        # Show progress
        total = len(tasks)
        chunk_size = 100
        
        for i in range(0, total, chunk_size):
            chunk = tasks[i:i+chunk_size]
            await asyncio.gather(*chunk)
            logger.info(f"⚡ Loaded {min(i+chunk_size, total)}/{total} symbols")
            
        duration = time.time() - start_time
        logger.info(f"✅ LOAD COMPLETE in {duration:.2f}s")
    
    async def _scan_loop(self):
        """Aggressive REST polling loop - MEMECOIN OPTIMIZED (ultra-fast)"""
        logger.info("📡 REST polling loop started (MEMECOIN MODE - 0.5s interval)")
        heartbeat_time = time.time()
        scan_count = 0
        
        while True:
            try:
                start = time.time()
                await self._full_scan()
                elapsed = time.time() - start
                scan_count += 1
                
                # Heartbeat каждые 30 минут (1800 сек)
                if time.time() - heartbeat_time >= 1800:
                    pumps_detected = len(self.pump_history) if hasattr(self, 'pump_history') else 0
                    logger.info(f"🚀 PUMP DETECTOR ALIVE | Scans: {scan_count} | Pumps: {pumps_detected} | Symbols: {len(self.client.symbols)}")
                    heartbeat_time = time.time()
                    scan_count = 0
                
                # ULTRA-AGGRESSIVE polling: 0.1 second interval (10 scans per second)
                sleep_time = max(0.01, 0.1 - elapsed)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Scan loop error: {e}")
                await asyncio.sleep(1)  # Было 2, стало 1
    
    async def _full_scan(self):
        """Scan all symbols for pumps"""
        tickers = await self.client.get_tickers()
        
        for ticker in tickers:
            # Calculate volume since last scan
            prev_vol = self.last_vol_24h.get(ticker.symbol, 0)
            
            if prev_vol > 0:
                # Delta volume between two snapshots
                current_vol = max(0, ticker.volume_24h - prev_vol)
            else:
                # Fallback to average on first scan (but divide by 60 to simulate a 1s slice)
                current_vol = ticker.volume_24h / 1440 / 60
            
            self.last_vol_24h[ticker.symbol] = ticker.volume_24h
            self.last_tickers_ts[ticker.symbol] = ticker.timestamp
            
            self.history[ticker.symbol].add(
                price=ticker.price,
                volume=current_vol,
                timestamp=ticker.timestamp
            )
            
            # Use normalized rate for immediate detection
            if prev_vol > 0:
                prev_ts = self.last_tickers_ts.get(ticker.symbol, ticker.timestamp - 1000)
                elapsed_min = max(0.01, (ticker.timestamp - prev_ts) / 60000)
                current_vol_rate = current_vol / elapsed_min
            else:
                current_vol_rate = ticker.volume_24h / 1440
                
            await self._check_pump(ticker.symbol, current_vol_rate=current_vol_rate)
            self.stats['total_checked'] += 1
    
    async def _check_pump(self, symbol: str, current_vol_rate: float = 0):
        """Check if symbol is pumping - PRICE ONLY MODE"""
        history = self.history.get(symbol)
        if not history or len(history.prices) < 2: # Min 2 points (1 min diff)
            return
        
        # Check cooldown
        if symbol in self.cooldown:
            cooldown_until = self.cooldown[symbol] + (self.cooldown_minutes * 60 * 1000)
            if time.time() * 1000 < cooldown_until:
                return
        
        # Get price change
        price_change = history.get_price_change(
            self.config.pump.time_window_minutes
        )
        
        # Check minimum pump threshold
        if price_change >= 1.0:
            logger.debug(f"🔍 Checking {symbol}: +{price_change:.2f}%")
            
        if price_change < self.config.pump.min_price_change_pct:
            return
        
        # Calculate indicators
        indicators = calculate_all_indicators(
            prices=history.prices,
            volumes=history.volumes,
            current_volume=current_vol_rate or history.volumes[-1]
        )
        
        # RSI check - DISABLED for pure price mode
        # rsi_threshold = max(self.config.pump.rsi_overbought - 5, 60.0)
        # if indicators.rsi < rsi_threshold:
        #     logger.debug(f"⏭️ Skipped {symbol}: Low RSI {indicators.rsi:.1f} < {rsi_threshold}")
        #     return
        
        self.stats['pumps_detected'] += 1
        
        # Calculate score (kept for info only, no longer blocks)
        score, breakdown = self._calculate_score(indicators, price_change)
        
        # Check minimum score threshold - DISABLED for pure price mode
        # min_score = min(self.config.scoring.min_score_threshold, 50)
        # if score < min_score:
        #     logger.debug(f"⏭️ Skipped {symbol}: Low score {score} < {min_score}")
        #     return
        
        # Get volume USD estimate
        ticker = self.client.tickers.get(symbol)
        volume_usd = ticker.volume_24h * ticker.price if ticker else 0
        
        # MINIMUM VOLUME FILTER - skip garbage pumps
        MIN_PUMP_VOLUME_USD = 1000  # Skip pumps with < $1000 volume
        if volume_usd < MIN_PUMP_VOLUME_USD:
            return  # Skip low-volume garbage
        
        # Create signal
        signal = PumpSignal(
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            price=history.prices[-1],
            price_change_pct=price_change,
            price_5min_ago=history.prices[-1] / (1 + price_change / 100),
            time_window_min=self.config.pump.time_window_minutes,
            volume_ratio=indicators.volume_ratio,
            volume_usd=volume_usd,
            rsi=indicators.rsi,
            ema20=indicators.ema20,
            ema_extension_pct=indicators.ema_extension_pct,
            momentum=indicators.momentum,
            has_divergence=indicators.is_divergence,
            divergence_type=indicators.divergence_type,
            score=score,
            score_breakdown=breakdown
        )
        
        # Store signal
        self.active_signals[symbol] = signal
        self.signal_history.append(signal)
        self.cooldown[symbol] = signal.timestamp
        self.stats['signals_generated'] += 1
        
        # Keep history limited
        if len(self.signal_history) > 100:
            self.signal_history = self.signal_history[-100:]
        
        logger.info(
            f"🔴 PUMP SIGNAL: {symbol} | "
            f"+{price_change:.1f}% | RSI {indicators.rsi:.1f} | "
            f"Score {score}/100"
        )
        
        # Notify callbacks
        await self._notify_signal(signal)
    
    def _calculate_score(
        self,
        indicators: IndicatorResult,
        price_change: float
    ) -> tuple[int, Dict[str, int]]:
        """
        Calculate signal score based on multiple factors
        
        Returns:
            Tuple of (total_score, breakdown_dict)
        """
        breakdown = {}
        
        # RSI Score (0-100)
        if indicators.rsi >= self.config.scoring.rsi_excellent:
            breakdown['rsi'] = 100
        elif indicators.rsi >= self.config.scoring.rsi_good:
            breakdown['rsi'] = 70
        elif indicators.rsi >= self.config.scoring.rsi_weak:
            breakdown['rsi'] = 40
        else:
            breakdown['rsi'] = 20
        
        # Extension Score (0-100)
        ext = abs(indicators.ema_extension_pct)
        if ext >= self.config.scoring.extension_excellent_pct:
            breakdown['extension'] = 100
        elif ext >= self.config.scoring.extension_good_pct:
            breakdown['extension'] = 70
        elif ext >= self.config.scoring.extension_weak_pct:
            breakdown['extension'] = 40
        else:
            breakdown['extension'] = 20
        
        # Volume Score (0-100)
        vol_ratio = indicators.volume_ratio
        if vol_ratio >= 5.0:
            breakdown['volume'] = 100
        elif vol_ratio >= 3.0:
            breakdown['volume'] = 70
        elif vol_ratio >= 2.0:
            breakdown['volume'] = 50
        else:
            breakdown['volume'] = 30
        
        # Momentum Score (0-100) 
        if price_change >= 15:
            breakdown['momentum'] = 100
        elif price_change >= 10:
            breakdown['momentum'] = 80
        elif price_change >= 5:
            breakdown['momentum'] = 60
        else:
            breakdown['momentum'] = 40
        
        # Divergence Bonus
        if indicators.is_divergence and indicators.divergence_type == 'bearish':
            breakdown['divergence'] = 20
        else:
            breakdown['divergence'] = 0
        
        # Calculate total (weighted average + bonus)
        base_score = (
            breakdown['rsi'] * 0.3 +
            breakdown['extension'] * 0.25 +
            breakdown['volume'] * 0.25 +
            breakdown['momentum'] * 0.2
        )
        
        total_score = min(100, int(base_score + breakdown['divergence']))
        
        return total_score, breakdown
    
    async def _notify_signal(self, signal: PumpSignal):
        """Notify all registered callbacks about new signal"""
        for callback in self._signal_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(signal)
                else:
                    callback(signal)
            except Exception as e:
                logger.error(f"Signal callback error: {e}")
    
    def get_active_signals(self) -> List[PumpSignal]:
        """Get list of currently active signals"""
        return list(self.active_signals.values())
    
    def get_signal_history(self, limit: int = 50) -> List[PumpSignal]:
        """Get recent signal history"""
        return self.signal_history[-limit:]
    
    def get_stats(self) -> Dict:
        """Get detector statistics"""
        uptime = time.time() - self.stats['start_time']
        return {
            **self.stats,
            'uptime_seconds': uptime,
            'uptime_formatted': f"{uptime / 3600:.1f}h",
            'active_signals': len(self.active_signals),
            'symbols_tracked': len(self.history)
        }

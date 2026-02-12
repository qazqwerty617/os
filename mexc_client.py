"""
MEXC Pump Monitor - MEXC Futures API Client
REST API only - optimized for aggressive polling
"""

import asyncio
import time
import logging
import ssl
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from collections import defaultdict, deque

import aiohttp

from config import config

logger = logging.getLogger(__name__)


@dataclass
class Ticker:
    """Ticker data container"""
    symbol: str
    price: float
    volume_24h: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    timestamp: int


@dataclass
class Kline:
    """Candlestick data container"""
    symbol: str
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


@dataclass 
class SymbolInfo:
    """Symbol metadata"""
    symbol: str
    base_asset: str
    quote_asset: str
    price_precision: int
    quantity_precision: int
    min_qty: float
    max_qty: float
    tick_size: float


class MEXCClient:
    """
    MEXC Futures API Client - REST ONLY
    Optimized for aggressive polling and pump detection
    """
    
    def __init__(self):
        self.config = config.mexc
        self.session: Optional[aiohttp.ClientSession] = None
        self.ssl_context: Optional[ssl.SSLContext] = None
        
        # Data storage (with limits to prevent memory leaks)
        self.tickers: Dict[str, Ticker] = {}
        self.klines: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self.symbols: Dict[str, SymbolInfo] = {}
        
        # Rate limiting - 20 requests/sec
        self._last_request_time = 0
        self._request_interval = 0.05
        self._request_count = 0
        
        self.stats = {
            'requests_made': 0,
            'requests_failed': 0,
            'rate_limited': 0,
            'start_time': time.time()
        }

    async def start(self):
        """Initialize the client"""
        # SSL context for HTTPS
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        
        # Connection pooling for better performance
        connector = aiohttp.TCPConnector(
            ssl=self.ssl_context,
            limit=50,  # Max connections
            limit_per_host=20,
            keepalive_timeout=30
        )
        
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
        
        await self._load_symbols()
        logger.info(f"✅ MEXC Client started (REST-ONLY mode)")
        logger.info(f"📊 Loaded {len(self.symbols)} trading symbols")

    async def stop(self):
        """Cleanup resources"""
        if self.session and not self.session.closed:
            await self.session.close()
        logger.info("MEXC client stopped")
    
    async def close(self):
        """Alias for stop"""
        await self.stop()
    
    async def _rate_limit(self):
        """Enforce rate limiting"""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._request_interval:
            await asyncio.sleep(self._request_interval - elapsed)
        self._last_request_time = time.time()
        self._request_count += 1
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        retries: int = 3
    ) -> Dict:
        """Make REST API request with retry logic"""
        await self._rate_limit()
        
        url = f"{self.config.rest_base_url}{endpoint}"
        self.stats['requests_made'] += 1
        
        for attempt in range(retries):
            try:
                async with self.session.request(method, url, params=params) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        self.stats['rate_limited'] += 1
                        wait_time = (attempt + 1) * 1.0
                        logger.warning(f"⚠️ MEXC rate limit (429), waiting {wait_time:.0f}s")
                        await asyncio.sleep(wait_time)
                        continue
                    elif resp.status == 403:
                        # Forbidden - likely geo-blocked
                        logger.debug(f"API 403: {endpoint}")
                        return {}
                    else:
                        text = await resp.text()
                        logger.warning(f"API {resp.status}: {text[:100]}")
                        return {}
                        
            except asyncio.TimeoutError:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                logger.debug(f"Timeout: {endpoint}")
                self.stats['requests_failed'] += 1
            except aiohttp.ClientError as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
                logger.debug(f"Client error: {e}")
                self.stats['requests_failed'] += 1
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                logger.debug(f"Request error: {e}")
                self.stats['requests_failed'] += 1
        
        return {}
    
    async def _load_symbols(self):
        """Load all available futures symbols"""
        data = await self._request('GET', '/api/v1/contract/detail')
        
        if not data or 'data' not in data:
            logger.error("Failed to load symbols")
            return
        
        loaded = 0
        for item in data['data']:
            symbol = item.get('symbol', '')
            
            # Only perpetual contracts
            if not symbol:
                continue
            
            # Skip leverage tokens and indices
            if '_' in symbol and not symbol.endswith('_USDT'):
                continue
            
            self.symbols[symbol] = SymbolInfo(
                symbol=symbol,
                base_asset=item.get('baseCoin', ''),
                quote_asset=item.get('quoteCoin', 'USDT'),
                price_precision=int(item.get('priceScale', 2)),
                quantity_precision=int(item.get('volScale', 2)),
                min_qty=float(item.get('minVol', 1) or 1),
                max_qty=float(item.get('maxVol', 100000) or 100000),
                tick_size=float(item.get('priceUnit', 0.01) or 0.01)
            )
            loaded += 1
        
        logger.info(f"Loaded {loaded} futures contracts")

    async def get_tickers(self) -> List[Ticker]:
        """Get all tickers - FUTURES API"""
        data = await self._request('GET', '/api/v1/contract/ticker')
        
        if not data or 'data' not in data:
            return list(self.tickers.values())  # Return cached on error
        
        tickers = []
        for item in data['data']:
            symbol = item.get('symbol', '')
            if symbol not in self.symbols:
                continue
            
            ticker = Ticker(
                symbol=symbol,
                price=float(item.get('lastPrice', 0) or 0),
                volume_24h=float(item.get('volume24', 0) or 0),
                change_24h_pct=float(item.get('riseFallRate', 0) or 0) * 100,
                high_24h=float(item.get('high24Price', 0) or 0),
                low_24h=float(item.get('low24Price', 0) or 0),
                timestamp=int(item.get('timestamp', time.time() * 1000))
            )
            tickers.append(ticker)
            self.tickers[symbol] = ticker
        
        return tickers

    async def get_ticker(self, symbol: str) -> Optional[Ticker]:
        """Get single ticker - FUTURES API"""
        endpoint = f'/api/v1/contract/ticker/{symbol}'
        data = await self._request('GET', endpoint)
        
        if not data or 'data' not in data:
            return self.tickers.get(symbol)
        
        item = data['data']
        ticker = Ticker(
            symbol=symbol,
            price=float(item.get('lastPrice', 0) or 0),
            volume_24h=float(item.get('volume24', 0) or 0),
            change_24h_pct=float(item.get('riseFallRate', 0) or 0) * 100,
            high_24h=float(item.get('high24Price', 0) or 0),
            low_24h=float(item.get('low24Price', 0) or 0),
            timestamp=int(item.get('timestamp', time.time() * 1000))
        )
        self.tickers[symbol] = ticker
        return ticker
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = 'Min1',
        limit: int = 100
    ) -> List[Kline]:
        """
        Get candlestick data - FUTURES API
        
        Args:
            symbol: Trading pair symbol
            interval: Candle interval (Min1, Min5, Min15, Min30, Hour1, etc.)
            limit: Number of candles to fetch
        """
        endpoint = f'/api/v1/contract/kline/{symbol}'
        
        now = int(time.time())
        
        # Map interval string to seconds
        interval_seconds = 60
        if 'Min' in interval:
            try:
                interval_seconds = int(interval.replace('Min', '')) * 60
            except: pass
        elif 'Hour' in interval:
            try:
                interval_seconds = int(interval.replace('Hour', '')) * 3600
            except: pass
        elif 'Day' in interval:
            try:
                interval_seconds = int(interval.replace('Day', '')) * 86400
            except: pass
            
        start = now - (limit * interval_seconds)
        end = now
        
        params = {
            'interval': interval,
            'start': start,
            'end': end
        }
        
        data = await self._request('GET', endpoint, params)
        
        if not data or not data.get('success', True):
            return []

        result = data.get('data')    
        if not result or not isinstance(result, dict) or 'time' not in result:
            return []
             
        # Parse columnar data
        klines = []
        times = result.get('time', [])
        opens = result.get('open', [])
        closes = result.get('close', [])
        highs = result.get('high', [])
        lows = result.get('low', [])
        vols = result.get('vol', [])
        amounts = result.get('amount', [])
        
        for i in range(len(times)):
            kline = Kline(
                symbol=symbol,
                timestamp=int(times[i] * 1000) if times[i] < 10000000000 else int(times[i]),
                open=float(opens[i]) if i < len(opens) else 0,
                high=float(highs[i]) if i < len(highs) else 0,
                low=float(lows[i]) if i < len(lows) else 0,
                close=float(closes[i]) if i < len(closes) else 0,
                volume=float(vols[i]) if i < len(vols) else 0,
                turnover=float(amounts[i]) if i < len(amounts) else 0
            )
            klines.append(kline)
            
        klines.sort(key=lambda x: x.timestamp)
        return klines
    
    async def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """
        Get order book - FUTURES API
        
        Args:
            symbol: Trading pair symbol
            depth: Depth of order book (default 20)
        
        Returns:
            {'bids': [(price, qty), ...], 'asks': [(price, qty), ...]}
        """
        endpoint = f'/api/v1/contract/depth/{symbol}'
        params = {'limit': depth}
        
        try:
            data = await self._request('GET', endpoint, params=params)
            
            if not data or 'data' not in data:
                return None
            
            orderbook_data = data['data']
            
            # Parse bids and asks
            bids = []
            asks = []
            
            if 'bids' in orderbook_data:
                for bid in orderbook_data['bids']:
                    if len(bid) >= 2:
                        bids.append((float(bid[0]), float(bid[1])))
            
            if 'asks' in orderbook_data:
                for ask in orderbook_data['asks']:
                    if len(ask) >= 2:
                        asks.append((float(ask[0]), float(ask[1])))
            
            return {
                'bids': bids,
                'asks': asks
            }
            
        except Exception as e:
            logger.debug(f"Orderbook fetch failed for {symbol}: {e}")
            return None
    
    async def get_open_interest(self, symbol: str) -> float:
        """Get open interest for a symbol"""
        endpoint = f'/api/v1/contract/open_interest/{symbol}'
        data = await self._request('GET', endpoint)
        
        if data and data.get('success', False):
            oi_data = data.get('data', {})
            return float(oi_data.get('openInterest', 0) or 0)
        return 0.0
    
    def get_active_symbols(self) -> List[str] :
        """Get list of active trading symbols"""
        return list(self.symbols.keys())
    
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol metadata"""
        return self.symbols.get(symbol)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics"""
        uptime = time.time() - self.stats['start_time']
        return {
            **self.stats,
            'symbols_count': len(self.symbols),
            'cached_tickers': len(self.tickers),
            'uptime_seconds': uptime,
            'requests_per_minute': self.stats['requests_made'] / max(1, uptime / 60)
        }

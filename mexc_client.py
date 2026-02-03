"""
MEXC Pump Monitor - MEXC Futures API Client
WebSocket and REST API integration
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from collections import defaultdict

import aiohttp
import websockets

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
    MEXC Futures API Client
    Handles WebSocket subscriptions and REST API calls
    """
    
    def __init__(self):
        self.config = config.mexc
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        
        # Data storage
        self.tickers: Dict[str, Ticker] = {}
        self.klines: Dict[str, List[Kline]] = defaultdict(list)
        self.symbols: Dict[str, SymbolInfo] = {}
        
        # Callbacks
        self._ticker_callbacks: List[Callable] = []
        self._kline_callbacks: List[Callable] = []
        
        # Rate limiting - 0.05 сек между запросами (20 запросов/сек)
        self._last_request_time = 0
        self._request_interval = 0.05

    
    async def start(self):
        """Initialize the client"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        self.ssl_context = ssl_context
        
        await self._load_symbols()
        logger.info(f"Loaded {len(self.symbols)} trading symbols")

    
    async def stop(self):
        """Cleanup resources"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        self.is_connected = False
        self.is_connected = False
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
        
        for attempt in range(retries):
            try:
                async with self.session.request(method, url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        # Rate limited - wait and retry
                        await asyncio.sleep(1)
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
                    await asyncio.sleep(0.5)
                    continue
                logger.debug(f"Timeout: {endpoint}")
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(0.5)
                    continue
                logger.debug(f"Request error: {e}")
        
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
            
            # Только perpetual контракты
            if not symbol:
                continue
            
            # Пропускаем leverage токены и индексы
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
            return []
        
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
        # Endpoint format: /api/v1/contract/kline/{symbol}
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

        # API returns:
        # { success: true, code: 0, data: { time: [], close: [], ... } }
        result = data.get('data')    
        if not result or not isinstance(result, dict) or 'time' not in result:
             # Fallback check
             if result and isinstance(result, list):
                 # Handle list format fallback if needed
                 pass
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
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=float(closes[i]),
                volume=float(vols[i]),
                turnover=float(amounts[i]) if i < len(amounts) else 0
            )
            klines.append(kline)
            
        klines.sort(key=lambda x: x.timestamp)
        return klines
        
        klines.sort(key=lambda x: x.timestamp)
        self.klines[symbol] = klines
        
        return klines

    
    def on_ticker(self, callback: Callable[[Ticker], Any]):
        """Register ticker update callback"""
        self._ticker_callbacks.append(callback)
    
    def on_kline(self, callback: Callable[[Kline], Any]):
        """Register kline update callback"""
        self._kline_callbacks.append(callback)
    
    async def connect_websocket(self, symbols: Optional[List[str]] = None):
        """
        Connect to WebSocket and subscribe to updates
        
        Args:
            symbols: List of symbols to subscribe to (None = all)
        """
        if symbols is None:
            symbols = list(self.symbols.keys())
        
        logger.info(f"Connecting to WebSocket for {len(symbols)} symbols...")
        
        try:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.ws = await websockets.connect(
                self.config.ws_base_url,
                ping_interval=20,
                ping_timeout=10,
                ssl=ssl_context
            )
            self.is_connected = True
            logger.info("WebSocket connected")

            
            # Subscribe to ticker updates for all symbols
            # MEXC uses batch subscriptions
            for i in range(0, len(symbols), 20):
                batch = symbols[i:i+20]
                
                # Subscribe to tickers
                sub_msg = {
                    "method": "sub.ticker",
                    "param": {"symbol": batch[0]}  # MEXC subscribes one at a time
                }
                
                for symbol in batch:
                    sub_msg['param']['symbol'] = symbol
                    await self.ws.send(json.dumps(sub_msg))
                
                await asyncio.sleep(0.1)
            
            logger.info(f"Subscribed to {len(symbols)} symbols")
            
            # Start message handling
            asyncio.create_task(self._handle_messages())
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            self.is_connected = False
    
    async def _handle_messages(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # Handle ticker updates
                    if 'channel' in data and 'ticker' in data['channel']:
                        await self._process_ticker_update(data)
                    
                    # Handle kline updates
                    elif 'channel' in data and 'kline' in data['channel']:
                        await self._process_kline_update(data)
                    
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket disconnected")
            self.is_connected = False
            
            # Attempt reconnection
            await asyncio.sleep(5)
            await self.connect_websocket()
    
    async def _process_ticker_update(self, data: Dict):
        """Process ticker WebSocket update"""
        try:
            symbol = data.get('symbol', '')
            ticker_data = data.get('data', {})
            
            # Handle case where data is a string or different format
            if isinstance(ticker_data, str):
                return
            if not isinstance(ticker_data, dict):
                return
            
            ticker = Ticker(
                symbol=symbol,
                price=float(ticker_data.get('lastPrice', 0) or 0),
                volume_24h=float(ticker_data.get('volume24', 0) or 0),
                change_24h_pct=float(ticker_data.get('riseFallRate', 0) or 0) * 100,
                high_24h=float(ticker_data.get('high24Price', 0) or 0),
                low_24h=float(ticker_data.get('low24Price', 0) or 0),
                timestamp=int(time.time() * 1000)
            )
            
            self.tickers[symbol] = ticker
            
            # Notify callbacks
            for callback in self._ticker_callbacks:
                try:
                    await callback(ticker) if asyncio.iscoroutinefunction(callback) else callback(ticker)
                except Exception as e:
                    logger.error(f"Ticker callback error: {e}")
        
        except Exception as e:
            logger.debug(f"Ticker parse skip: {e}")

    
    async def _process_kline_update(self, data: Dict):
        """Process kline WebSocket update"""
        try:
            symbol = data.get('symbol', '')
            kline_data = data.get('data', {})
            
            kline = Kline(
                symbol=symbol,
                timestamp=int(kline_data.get('t', time.time() * 1000)),
                open=float(kline_data.get('o', 0)),
                high=float(kline_data.get('h', 0)),
                low=float(kline_data.get('l', 0)),
                close=float(kline_data.get('c', 0)),
                volume=float(kline_data.get('v', 0)),
                turnover=float(kline_data.get('q', 0))
            )
            
            # Update klines storage
            if symbol in self.klines:
                # Update or append
                if self.klines[symbol] and self.klines[symbol][-1].timestamp == kline.timestamp:
                    self.klines[symbol][-1] = kline
                else:
                    self.klines[symbol].append(kline)
                    # Keep only last 200 candles
                    if len(self.klines[symbol]) > 200:
                        self.klines[symbol] = self.klines[symbol][-200:]
            
            # Notify callbacks
            for callback in self._kline_callbacks:
                try:
                    await callback(kline) if asyncio.iscoroutinefunction(callback) else callback(kline)
                except Exception as e:
                    logger.error(f"Kline callback error: {e}")
        
        except Exception as e:
            logger.error(f"Error processing kline: {e}")
    
    def get_active_symbols(self) -> List[str]:
        """Get list of active trading symbols"""
        return list(self.symbols.keys())
    
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Get symbol metadata"""
        return self.symbols.get(symbol)

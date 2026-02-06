"""
MEXC Pump Monitor - Global Listing Watcher
Tracks listings across 6 major exchanges: Binance, OKX, Bybit, Gate.io, BingX, KuCoin
"""

import asyncio
import aiohttp
import time
import logging
import json
import os
from typing import Dict, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)

class GlobalListingWatcher:
    """
    Monitors 6 major exchanges for token presence and listing age.
    Used to identify high-risk pumps causing by new listings.
    """
    
    EXCHANGES = ['Binance', 'Binance Futures', 'OKX', 'Bybit', 'Gate.io', 'BingX', 'KuCoin']
    PERSISTENCE_FILE = "data/global_listings.json"
    
    def __init__(self, check_interval: int = 30): # 30 seconds for instant alerts
        self.check_interval = check_interval
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._is_first_run = True  # Flag to handle first scan properly
        
        self.listings: Dict[str, Dict[str, int]] = {}
        self._callbacks: List[callable] = []
        self._load_listings()
        
    def _load_listings(self):
        """Load listings from persistence file"""
        if os.path.exists(self.PERSISTENCE_FILE):
            try:
                with open(self.PERSISTENCE_FILE, 'r') as f:
                    self.listings = json.load(f)
                logger.info(f"📁 Loaded {len(self.listings)} symbols from global listings cache.")
                # Cache exists = not first run, enable real-time new listing detection
                self._is_first_run = False
            except Exception as e:
                logger.error(f"Error loading global listings: {e}")
                self.listings = {}
        else:
            os.makedirs(os.path.dirname(self.PERSISTENCE_FILE), exist_ok=True)
            self.listings = {}

    def _save_listings(self):
        """Save listings to persistence file"""
        try:
            with open(self.PERSISTENCE_FILE, 'w') as f:
                json.dump(self.listings, f)
        except Exception as e:
            logger.error(f"Error saving global listings: {e}")

    async def start(self):
        """Start monitoring loop"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)
        self._running = True
        
        # Initial scan
        await self._perform_full_scan()
        
        # Start background loop
        asyncio.create_task(self._monitor_loop())
        logger.info("📡 GlobalListingWatcher started (6 exchanges tracked).")

    async def stop(self):
        """Stop monitoring loop"""
        self._running = False
        if self._session:
            await self._session.close()
        self._save_listings()

    async def _monitor_loop(self):
        """Periodic scan loop"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval)
                await self._perform_full_scan()
                self._save_listings()
            except Exception as e:
                logger.error(f"GlobalWatcher loop error: {e}")

    async def _perform_full_scan(self):
        """Scan all 6 exchanges for symbols"""
        logger.debug("🔍 Performing global listing scan...")
        
        tasks = [
            self._fetch_binance(),
            self._fetch_binance_futures(),
            self._fetch_okx(),
            self._fetch_bybit(),
            self._fetch_gate(),
            self._fetch_bingx(),
            self._fetch_kucoin()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        now = int(time.time() * 1000)
    
        # On first run, use old timestamp (7 days ago) for existing symbols
        # This prevents false "NEW LISTING" alerts for already-listed coins
        discovery_time = now if not self._is_first_run else now - (7 * 24 * 3600 * 1000)
        
        for idx, symbols in enumerate(results):
            if isinstance(symbols, Exception):
                logger.error(f"Error fetching from {self.EXCHANGES[idx]}: {symbols}")
                continue
                
            exchange_name = self.EXCHANGES[idx]
            for sym in symbols:
                sym_upper = sym.upper()
                if sym_upper not in self.listings:
                    self.listings[sym_upper] = {}
                
                if exchange_name not in self.listings[sym_upper]:
                    # Use discovery_time: now for real new listings, old for first run
                    self.listings[sym_upper][exchange_name] = discovery_time
                    if not self._is_first_run:
                        logger.info(f"✨ NEW LISTING: {sym_upper} on {exchange_name}")
                        # Notify callbacks
                        for cb in self._callbacks:
                            asyncio.create_task(cb(sym_upper, exchange_name))
        
        # Mark first run as complete
        if self._is_first_run:
            self._is_first_run = False
            logger.info(f"📊 Initial scan complete: {len(self.listings)} symbols indexed")

    async def _fetch_binance_futures(self) -> Set[str]:
        """Fetch symbols from Binance Futures"""
        try:
            url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
            async with self._session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {s['baseAsset'] for s in data.get('symbols', []) if s['quoteAsset'] == 'USDT'}
        except Exception:
            pass
        return set()

    def on_new_listing(self, callback):
        """Register callback for new listings"""
        self._callbacks.append(callback)

    def check_token(self, symbol: str) -> Dict[str, str]:
        """
        Check if token exists on major exchanges and its age.
        Returns: { exchange_name: status_string }
        """
        # Clean symbol (remove USDT suffix/prefix)
        base = symbol.split('_')[0] if '_' in symbol else symbol.replace('USDT', '')
        base = base.upper()
        
        found_on = self.listings.get(base, {})
        if not found_on:
            return {}
            
        now = int(time.time() * 1000)
        report = {}
        
        for ex, first_seen in found_on.items():
            age_hours = (now - first_seen) / (3600 * 1000)
            if age_hours < 24:
                report[ex] = f"New ({age_hours:.1f}h ago)"
            else:
                report[ex] = "Old"
                
        return report

    def is_new_listing(self, symbol: str, max_age_hours: float = 24) -> tuple[bool, list[tuple[str, float]]]:
        """
        Check if token was recently listed on major exchanges.
        
        Args:
            symbol: Token symbol (e.g., 'BTC_USDT' or 'BTCUSDT')
            max_age_hours: Maximum age in hours to consider "new"
            
        Returns:
            Tuple of (is_new, list of (exchange_name, age_hours))
        """
        base = symbol.split('_')[0] if '_' in symbol else symbol.replace('USDT', '')
        base = base.upper()
        
        found_on = self.listings.get(base, {})
        if not found_on:
            return False, []
            
        now = int(time.time() * 1000)
        new_listings = []
        
        for ex, first_seen in found_on.items():
            age_hours = (now - first_seen) / (3600 * 1000)
            if age_hours < max_age_hours:
                new_listings.append((ex, age_hours))
        
        # Sort by age (newest first)
        new_listings.sort(key=lambda x: x[1])
        
        return len(new_listings) > 0, new_listings

    async def get_prices(self, symbol: str) -> Dict[str, float]:
        """
        Fetch current prices from exchanges where token is listed
        """
        base = symbol.split('_')[0] if '_' in symbol else symbol.replace('USDT', '')
        base = base.upper()
        
        exchanges = self.listings.get(base, {}).keys()
        if not exchanges:
            return {}
            
        tasks = []
        exchange_list = []
        
        for ex in exchanges:
            if ex == 'Binance': tasks.append(self._fetch_binance_price(base)); exchange_list.append(ex)
            elif ex == 'OKX': tasks.append(self._fetch_okx_price(base)); exchange_list.append(ex)
            elif ex == 'Bybit': tasks.append(self._fetch_bybit_price(base)); exchange_list.append(ex)
            elif ex == 'Gate.io': tasks.append(self._fetch_gate_price(base)); exchange_list.append(ex)
            elif ex == 'BingX': tasks.append(self._fetch_bingx_price(base)); exchange_list.append(ex)
            elif ex == 'KuCoin': tasks.append(self._fetch_kucoin_price(base)); exchange_list.append(ex)
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        price_report = {}
        for idx, price in enumerate(results):
            if isinstance(price, (int, float)) and price > 0:
                price_report[exchange_list[idx]] = float(price)
            elif isinstance(price, Exception):
                logger.debug(f"Error fetching price from {exchange_list[idx]}: {price}")
                
        return price_report

    # --- Exchange Fetchers ---

    async def _fetch_binance_price(self, base: str) -> float:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={base}USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data.get('price', 0))
        except: return 0

    async def _fetch_okx_price(self, base: str) -> float:
        try:
            url = f"https://www.okx.com/api/v5/market/ticker?instId={base}-USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data.get('data', [{}])[0].get('last', 0))
        except: return 0

    async def _fetch_bybit_price(self, base: str) -> float:
        try:
            url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={base}USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data.get('result', {}).get('list', [{}])[0].get('lastPrice', 0))
        except: return 0

    async def _fetch_gate_price(self, base: str) -> float:
        try:
            url = f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={base}_USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data[0].get('last', 0))
        except: return 0

    async def _fetch_bingx_price(self, base: str) -> float:
        try:
            url = f"https://open-api.bingx.com/openApi/spot/v1/ticker/24hr?symbol={base}-USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data.get('data', [{}])[0].get('lastPrice', 0))
        except: return 0

    async def _fetch_kucoin_price(self, base: str) -> float:
        try:
            url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={base}-USDT"
            async with self._session.get(url) as resp:
                data = await resp.json()
                return float(data.get('data', {}).get('price', 0))
        except: return 0

    # --- Exchange Fetchers ---

    async def _fetch_binance(self) -> Set[str]:
        url = "https://api.binance.com/api/v3/exchangeInfo"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['baseAsset'] for s in data.get('symbols', [])}

    async def _fetch_okx(self) -> Set[str]:
        url = "https://www.okx.com/api/v5/public/instruments?instType=SPOT"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['baseCcy'] for s in data.get('data', [])}

    async def _fetch_bybit(self) -> Set[str]:
        url = "https://api.bybit.com/v5/market/instruments-info?category=spot"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['baseCoin'] for s in data.get('result', {}).get('list', [])}

    async def _fetch_gate(self) -> Set[str]:
        url = "https://api.gateio.ws/api/v4/spot/currency_pairs"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['base'] for s in data if isinstance(s, dict)}

    async def _fetch_bingx(self) -> Set[str]:
        url = "https://open-api.bingx.com/openApi/spot/v1/common/symbols"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['symbol'].split('-')[0] for s in data.get('data', {}).get('symbols', [])}

    async def _fetch_kucoin(self) -> Set[str]:
        url = "https://api.kucoin.com/api/v1/symbols"
        async with self._session.get(url) as resp:
            data = await resp.json()
            return {s['baseCurrency'] for s in data.get('data', [])}

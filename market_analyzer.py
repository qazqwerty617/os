"""
MEXC Pump Monitor - Advanced Market Analysis
Order Book, Funding Rate, Open Interest, Liquidations
Optimized for high-concurrency data fetching
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque

import aiohttp

from config import config

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single order book level"""
    price: float
    quantity: float
    total: float = 0


@dataclass
class OrderBook:
    """Order book snapshot with analysis"""
    symbol: str
    timestamp: int
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    bid_wall_price: float = 0
    ask_wall_price: float = 0
    imbalance_ratio: float = 0
    spread_pct: float = 0
    
    def analyze(self):
        """Analyze order book"""
        if not self.bids or not self.asks:
            return
        
        best_bid = self.bids[0].price
        best_ask = self.asks[0].price
        mid_price = (best_bid + best_ask) / 2
        self.spread_pct = ((best_ask - best_bid) / mid_price) * 100
        
        # Calculate totals and find walls
        bid_vols = [b.quantity for b in self.bids[:20]]
        ask_vols = [a.quantity for a in self.asks[:20]]
        avg_bid = sum(bid_vols) / len(bid_vols) if bid_vols else 0
        avg_ask = sum(ask_vols) / len(ask_vols) if ask_vols else 0
        
        for bid in self.bids[:20]:
            if bid.quantity > avg_bid * 5:
                self.bid_wall_price = bid.price
                break
        
        for ask in self.asks[:20]:
            if ask.quantity > avg_ask * 5:
                self.ask_wall_price = ask.price
                break
        
        # Imbalance ratio (>1 more bids, <1 more asks)
        total_bids = sum(bid_vols[:10])
        total_asks = sum(ask_vols[:10])
        self.imbalance_ratio = total_bids / total_asks if total_asks > 0 else 1.0


@dataclass
class FundingInfo:
    """Funding rate data"""
    symbol: str
    funding_rate: float
    next_funding_time: int
    predicted_rate: float
    
    @property
    def is_extreme_long(self) -> bool:
        return self.funding_rate > config.pump.funding_rate_extreme
    
    @property
    def is_extreme_short(self) -> bool:
        return self.funding_rate < -config.pump.funding_rate_extreme


@dataclass
class OpenInterestData:
    """Open Interest tracking"""
    symbol: str
    timestamp: int
    open_interest: float
    open_interest_value: float
    oi_change_1h: float = 0
    oi_change_24h: float = 0


@dataclass
class LiquidationEvent:
    """Liquidation event"""
    symbol: str
    timestamp: int
    side: str
    quantity: float
    price: float
    value_usd: float


@dataclass
class MarketDepthAnalysis:
    """Complete market depth analysis result"""
    symbol: str
    timestamp: int
    order_book: Optional[OrderBook] = None
    funding: Optional[FundingInfo] = None
    open_interest: Optional[OpenInterestData] = None
    recent_liquidations: List[LiquidationEvent] = field(default_factory=list)
    short_pressure_score: int = 50
    
    def calculate_short_pressure(self):
        """Calculate how favorable conditions are for shorting"""
        scores = []
        
        # Order book imbalance
        if self.order_book:
            ratio = self.order_book.imbalance_ratio
            if ratio < 0.7: scores.append(80)
            elif ratio < 1.0: scores.append(60)
            else: scores.append(40)
        
        # Funding rate
        if self.funding:
            if self.funding.is_extreme_long: scores.append(90)
            elif self.funding.funding_rate > 0.05: scores.append(70)
            else: scores.append(50)
        
        # OI Change
        if self.open_interest:
            if self.open_interest.oi_change_1h > 20: scores.append(85)
            elif self.open_interest.oi_change_1h > 10: scores.append(70)
            else: scores.append(50)
        
        # Liquidations (Longs rekt = reversal?)
        long_vol = sum(l.value_usd for l in self.recent_liquidations if l.side == 'LONG')
        short_vol = sum(l.value_usd for l in self.recent_liquidations if l.side == 'SHORT')
        
        if long_vol > short_vol * 2: scores.append(30)
        elif short_vol > long_vol: scores.append(60)
        else: scores.append(50)
        
        self.short_pressure_score = int(sum(scores) / len(scores)) if scores else 50


class MarketAnalyzer:
    """
    Advanced market analysis engine
    Optimized for async IO
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.order_books: Dict[str, OrderBook] = {}
        self.funding_rates: Dict[str, FundingInfo] = {}
        self.open_interest: Dict[str, OpenInterestData] = {}
        self.liquidations: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.oi_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
    
    async def start(self):
        import ssl
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx))
        logger.info("Market analyzer started")
    
    async def stop(self):
        if self.session:
            await self.session.close()
    
    async def _request(self, url: str, params: Dict = None) -> Dict:
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Request error {url}: {e}")
        return {}
    
    async def fetch_order_book(self, symbol: str, depth: int = 20) -> Optional[OrderBook]:
        url = f"{config.mexc.rest_base_url}/api/v1/contract/depth/{symbol}"
        data = await self._request(url, {'limit': depth})
        if not data or 'data' not in data:
            return None
        
        d = data['data']
        bids = [OrderBookLevel(float(p), float(q)) for p, q in d.get('bids', [])[:depth]]
        asks = [OrderBookLevel(float(p), float(q)) for p, q in d.get('asks', [])[:depth]]
        
        ob = OrderBook(symbol, int(time.time()*1000), bids, asks)
        ob.analyze()
        self.order_books[symbol] = ob
        return ob
    
    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingInfo]:
        url = f"{config.mexc.rest_base_url}/api/v1/contract/funding_rate/{symbol}"
        data = await self._request(url)
        if not data or 'data' not in data:
            return None
        
        d = data['data']
        fi = FundingInfo(
            symbol,
            float(d.get('fundingRate', 0)) * 100,
            int(d.get('nextSettleTime', 0)),
            float(d.get('expectedFundingRate', 0)) * 100
        )
        self.funding_rates[symbol] = fi
        return fi
    
    async def fetch_open_interest(self, symbol: str) -> Optional[OpenInterestData]:
        url = f"{config.mexc.rest_base_url}/api/v1/contract/open_interest/{symbol}"
        data = await self._request(url)
        if not data or 'data' not in data:
            return None
        
        d = data['data']
        now = int(time.time()*1000)
        curr_oi = float(d.get('openInterest', 0))
        
        # OI Change Calc
        hist = self.oi_history[symbol]
        oi_1h = next((oi for ts, oi in reversed(hist) if ts <= now - 3600000), curr_oi)
        oi_24h = next((oi for ts, oi in reversed(hist) if ts <= now - 86400000), curr_oi)
        
        change_1h = ((curr_oi - oi_1h) / oi_1h * 100) if oi_1h else 0
        change_24h = ((curr_oi - oi_24h) / oi_24h * 100) if oi_24h else 0
        
        hist.append((now, curr_oi))
        self.oi_history[symbol] = [x for x in hist if x[0] > now - 90000000] # Clean old
        
        oi_data = OpenInterestData(
            symbol, now, curr_oi, float(d.get('openInterestValue', 0)),
            change_1h, change_24h
        )
        self.open_interest[symbol] = oi_data
        return oi_data
    
    async def analyze_symbol(self, symbol: str) -> MarketDepthAnalysis:
        ob, fr, oi = await asyncio.gather(
            self.fetch_order_book(symbol),
            self.fetch_funding_rate(symbol),
            self.fetch_open_interest(symbol),
            return_exceptions=True
        )
        
        analysis = MarketDepthAnalysis(
            symbol=symbol,
            timestamp=int(time.time()*1000),
            order_book=ob if not isinstance(ob, Exception) else None,
            funding=fr if not isinstance(fr, Exception) else None,
            open_interest=oi if not isinstance(oi, Exception) else None,
            recent_liquidations=self.liquidations.get(symbol, [])[-20:]
        )
        analysis.calculate_short_pressure()
        return analysis

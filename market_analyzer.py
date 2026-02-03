"""
MEXC Pump Monitor - Advanced Market Analysis
Order Book, Funding Rate, Open Interest, Liquidations
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import aiohttp

from config import config

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Single order book level"""
    price: float
    quantity: float
    total: float = 0  # Cumulative quantity


@dataclass
class OrderBook:
    """Order book snapshot"""
    symbol: str
    timestamp: int
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    
    # Analysis results
    bid_wall_price: float = 0
    ask_wall_price: float = 0
    imbalance_ratio: float = 0  # >1 = more bids, <1 = more asks
    spread_pct: float = 0
    
    def analyze(self):
        """Analyze order book for walls and imbalance"""
        if not self.bids or not self.asks:
            return
        
        # Calculate spread
        best_bid = self.bids[0].price
        best_ask = self.asks[0].price
        mid_price = (best_bid + best_ask) / 2
        self.spread_pct = ((best_ask - best_bid) / mid_price) * 100
        
        # Find walls (large orders)
        bid_volumes = [b.quantity for b in self.bids[:20]]
        ask_volumes = [a.quantity for a in self.asks[:20]]
        
        avg_bid = sum(bid_volumes) / len(bid_volumes) if bid_volumes else 0
        avg_ask = sum(ask_volumes) / len(ask_volumes) if ask_volumes else 0
        
        # Wall = 5x average volume
        for bid in self.bids[:20]:
            if bid.quantity > avg_bid * 5:
                self.bid_wall_price = bid.price
                break
        
        for ask in self.asks[:20]:
            if ask.quantity > avg_ask * 5:
                self.ask_wall_price = ask.price
                break
        
        # Imbalance ratio
        total_bids = sum(bid_volumes[:10])
        total_asks = sum(ask_volumes[:10])
        self.imbalance_ratio = total_bids / total_asks if total_asks > 0 else 1


@dataclass
class FundingInfo:
    """Funding rate data"""
    symbol: str
    funding_rate: float      # Current funding rate (%)
    next_funding_time: int   # Timestamp of next funding
    predicted_rate: float    # Predicted next rate
    
    @property
    def is_extreme_long(self) -> bool:
        """High positive = longs pay shorts = bullish sentiment"""
        return self.funding_rate > config.pump.funding_rate_extreme
    
    @property
    def is_extreme_short(self) -> bool:
        """High negative = shorts pay longs = bearish sentiment"""
        return self.funding_rate < -config.pump.funding_rate_extreme


@dataclass
class OpenInterestData:
    """Open Interest tracking"""
    symbol: str
    timestamp: int
    open_interest: float       # Current OI
    open_interest_value: float # OI in USD
    oi_change_1h: float = 0    # % change in 1 hour
    oi_change_24h: float = 0   # % change in 24 hours


@dataclass
class LiquidationEvent:
    """Liquidation event"""
    symbol: str
    timestamp: int
    side: str           # 'LONG' or 'SHORT'
    quantity: float
    price: float
    value_usd: float


@dataclass
class MarketDepthAnalysis:
    """Complete market depth analysis result"""
    symbol: str
    timestamp: int
    
    # Order book
    order_book: Optional[OrderBook] = None
    
    # Funding & OI
    funding: Optional[FundingInfo] = None
    open_interest: Optional[OpenInterestData] = None
    
    # Liquidations
    recent_liquidations: List[LiquidationEvent] = field(default_factory=list)
    long_liquidation_volume: float = 0
    short_liquidation_volume: float = 0
    
    # Scores (0-100)
    short_pressure_score: int = 50  # High = good for short
    
    def calculate_short_pressure(self):
        """Calculate how favorable conditions are for shorting"""
        scores = []
        
        # Order book imbalance (more asks = bearish)
        if self.order_book:
            if self.order_book.imbalance_ratio < 0.7:
                scores.append(80)  # Bearish imbalance
            elif self.order_book.imbalance_ratio < 1.0:
                scores.append(60)
            else:
                scores.append(40)
        
        # Funding rate (high positive = longs paying = potential reversal)  
        if self.funding:
            if self.funding.is_extreme_long:
                scores.append(90)  # Perfect for short
            elif self.funding.funding_rate > 0.05:
                scores.append(70)
            else:
                scores.append(50)
        
        # OI increase during pump = new longs = fuel for short
        if self.open_interest and self.open_interest.oi_change_1h > 20:
            scores.append(85)
        elif self.open_interest and self.open_interest.oi_change_1h > 10:
            scores.append(70)
        else:
            scores.append(50)
        
        # Long liquidations happening = cascade potential
        if self.long_liquidation_volume > self.short_liquidation_volume * 2:
            scores.append(30)  # Longs getting rekt, maybe bottom
        elif self.short_liquidation_volume > self.long_liquidation_volume:
            scores.append(60)  # Shorts getting rekt, pump continues
        else:
            scores.append(50)
        
        self.short_pressure_score = int(sum(scores) / len(scores)) if scores else 50


class MarketAnalyzer:
    """
    Advanced market analysis engine
    Tracks order book, funding rates, OI, and liquidations
    """
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Data storage
        self.order_books: Dict[str, OrderBook] = {}
        self.funding_rates: Dict[str, FundingInfo] = {}
        self.open_interest: Dict[str, OpenInterestData] = {}
        self.liquidations: Dict[str, List[LiquidationEvent]] = defaultdict(list)
        
        # Historical OI for change calculation
        self.oi_history: Dict[str, List[Tuple[int, float]]] = defaultdict(list)
    
    async def start(self):
        """Initialize analyzer"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(connector=connector)
        logger.info("Market analyzer started")

    
    async def stop(self):
        """Cleanup"""
        if self.session:
            await self.session.close()
    
    async def _request(self, url: str, params: Dict = None) -> Dict:
        """Make API request"""
        try:
            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Request failed: {e}")
        return {}
    
    async def fetch_order_book(self, symbol: str, depth: int = 20) -> Optional[OrderBook]:
        """Fetch order book for symbol"""
        url = f"{config.mexc.rest_base_url}/api/v1/contract/depth/{symbol}"
        data = await self._request(url, {'limit': depth})
        
        if not data or 'data' not in data:
            return None
        
        book_data = data['data']
        
        bids = [
            OrderBookLevel(price=float(b[0]), quantity=float(b[1]))
            for b in book_data.get('bids', [])[:depth]
        ]
        
        asks = [
            OrderBookLevel(price=float(a[0]), quantity=float(a[1]))
            for a in book_data.get('asks', [])[:depth]
        ]
        
        order_book = OrderBook(
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bids=bids,
            asks=asks
        )
        order_book.analyze()
        
        self.order_books[symbol] = order_book
        return order_book
    
    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingInfo]:
        """Fetch funding rate for symbol"""
        url = f"{config.mexc.rest_base_url}/api/v1/contract/funding_rate/{symbol}"
        data = await self._request(url)
        
        if not data or 'data' not in data:
            return None
        
        fr_data = data['data']
        
        funding = FundingInfo(
            symbol=symbol,
            funding_rate=float(fr_data.get('fundingRate', 0)) * 100,
            next_funding_time=int(fr_data.get('nextSettleTime', 0)),
            predicted_rate=float(fr_data.get('expectedFundingRate', 0)) * 100
        )
        
        self.funding_rates[symbol] = funding
        return funding
    
    async def fetch_open_interest(self, symbol: str) -> Optional[OpenInterestData]:
        """Fetch open interest for symbol"""
        url = f"{config.mexc.rest_base_url}/api/v1/contract/open_interest/{symbol}"
        data = await self._request(url)
        
        if not data or 'data' not in data:
            return None
        
        oi_data = data['data']
        current_oi = float(oi_data.get('openInterest', 0))
        current_time = int(time.time() * 1000)
        
        # Calculate OI changes
        oi_change_1h = 0
        oi_change_24h = 0
        
        history = self.oi_history[symbol]
        
        # 1 hour ago
        one_hour_ago = current_time - (60 * 60 * 1000)
        for ts, oi in reversed(history):
            if ts <= one_hour_ago:
                oi_change_1h = ((current_oi - oi) / oi) * 100 if oi > 0 else 0
                break
        
        # 24 hours ago
        one_day_ago = current_time - (24 * 60 * 60 * 1000)
        for ts, oi in reversed(history):
            if ts <= one_day_ago:
                oi_change_24h = ((current_oi - oi) / oi) * 100 if oi > 0 else 0
                break
        
        # Store in history
        history.append((current_time, current_oi))
        # Keep only 24h of history
        cutoff = current_time - (25 * 60 * 60 * 1000)
        self.oi_history[symbol] = [(t, o) for t, o in history if t > cutoff]
        
        oi_info = OpenInterestData(
            symbol=symbol,
            timestamp=current_time,
            open_interest=current_oi,
            open_interest_value=float(oi_data.get('openInterestValue', 0)),
            oi_change_1h=oi_change_1h,
            oi_change_24h=oi_change_24h
        )
        
        self.open_interest[symbol] = oi_info
        return oi_info
    
    async def analyze_symbol(self, symbol: str) -> MarketDepthAnalysis:
        """
        Perform full market depth analysis for symbol
        
        Returns:
            MarketDepthAnalysis with all data and scores
        """
        # Fetch all data concurrently
        order_book, funding, oi = await asyncio.gather(
            self.fetch_order_book(symbol),
            self.fetch_funding_rate(symbol),
            self.fetch_open_interest(symbol),
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(order_book, Exception):
            order_book = None
        if isinstance(funding, Exception):
            funding = None
        if isinstance(oi, Exception):
            oi = None
        
        analysis = MarketDepthAnalysis(
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            order_book=order_book,
            funding=funding,
            open_interest=oi,
            recent_liquidations=self.liquidations.get(symbol, [])[-20:]
        )
        
        # Calculate liquidation volumes
        recent_liqs = analysis.recent_liquidations
        one_hour_ago = int(time.time() * 1000) - (60 * 60 * 1000)
        
        for liq in recent_liqs:
            if liq.timestamp > one_hour_ago:
                if liq.side == 'LONG':
                    analysis.long_liquidation_volume += liq.value_usd
                else:
                    analysis.short_liquidation_volume += liq.value_usd
        
        analysis.calculate_short_pressure()
        
        return analysis
    
    async def scan_all_funding_rates(self, symbols: List[str]) -> Dict[str, FundingInfo]:
        """Scan funding rates for multiple symbols"""
        results = {}
        
        for symbol in symbols:
            try:
                funding = await self.fetch_funding_rate(symbol)
                if funding:
                    results[symbol] = funding
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                logger.error(f"Error fetching funding for {symbol}: {e}")
        
        return results
    
    def get_extreme_funding_symbols(self) -> List[Tuple[str, FundingInfo]]:
        """Get symbols with extreme funding rates"""
        extreme = []
        
        for symbol, funding in self.funding_rates.items():
            if funding.is_extreme_long or funding.is_extreme_short:
                extreme.append((symbol, funding))
        
        # Sort by absolute funding rate
        extreme.sort(key=lambda x: abs(x[1].funding_rate), reverse=True)
        
        return extreme
    
    def get_high_oi_change_symbols(self, min_change_pct: float = 20) -> List[Tuple[str, OpenInterestData]]:
        """Get symbols with high OI changes"""
        high_oi = []
        
        for symbol, oi in self.open_interest.items():
            if abs(oi.oi_change_1h) >= min_change_pct:
                high_oi.append((symbol, oi))
        
        high_oi.sort(key=lambda x: abs(x[1].oi_change_1h), reverse=True)
        
        return high_oi

"""
MEXC Pump Monitor - New Listings Detector
Monitors for new futures listings and alerts immediately
"""

import asyncio
import aiohttp
import time
import logging
from typing import Dict, List, Optional, Set, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ListingStatus(Enum):
    """Listing status"""
    ANNOUNCED = "ANNOUNCED"      # Announced but not live
    PENDING = "PENDING"          # Pre-market/coming soon
    LIVE = "LIVE"                # Just went live
    TRADING = "TRADING"          # Already trading


@dataclass
class NewListing:
    """New listing information"""
    symbol: str
    base_asset: str
    quote_asset: str
    
    # Timing
    detected_at: int
    listing_time: Optional[int] = None
    trading_start: Optional[int] = None
    
    # Status
    status: ListingStatus = ListingStatus.ANNOUNCED
    
    # Initial market data
    initial_price: Optional[float] = None
    current_price: Optional[float] = None
    price_change_pct: float = 0
    
    # Volume since listing
    volume_usd: float = 0
    trade_count: int = 0
    
    # Leverage info
    max_leverage: int = 20
    
    # Tokenomics (fetched separately)
    tokenomics: Optional[Dict] = None
    
    # Analysis
    pump_potential: int = 50  # 0-100 score
    risk_level: str = "MEDIUM"
    
    def time_since_listing(self) -> int:
        """Get seconds since listing"""
        if self.trading_start:
            return int(time.time()) - (self.trading_start // 1000)
        return 0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'base_asset': self.base_asset,
            'status': self.status.value,
            'detected_at': self.detected_at,
            'listing_time': self.listing_time,
            'initial_price': self.initial_price,
            'current_price': self.current_price,
            'price_change_pct': self.price_change_pct,
            'volume_usd': self.volume_usd,
            'max_leverage': self.max_leverage,
            'pump_potential': self.pump_potential,
            'risk_level': self.risk_level,
            'tokenomics': self.tokenomics
        }


class NewListingsDetector:
    """
    Monitors MEXC for new futures listings
    Alerts immediately when new trading pairs appear
    """
    
    # MEXC API endpoints
    FUTURES_SYMBOLS_URL = "https://contract.mexc.com/api/v1/contract/detail"
    ANNOUNCEMENTS_URL = "https://www.mexc.com/api/announcements"
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        
        # Known symbols (to detect new ones)
        self.known_symbols: Set[str] = set()
        
        # New listings
        self.new_listings: Dict[str, NewListing] = {}
        
        # Historical listings (last 24h)
        self.recent_listings: List[NewListing] = []
        
        # Callbacks
        self._callbacks: List[Callable] = []
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.stats = {
            'checks_performed': 0,
            'new_listings_found': 0,
            'last_check': None
        }
        
        self._running = False
    
    def is_recent_listing(self, symbol: str, window_hours: int = 24) -> bool:
        """Check if symbol was recently listed"""
        cutoff = int(time.time() * 1000) - (window_hours * 3600 * 1000)
        # Check new_listings dict
        if symbol in self.new_listings:
            return True
        # Check recent_listings list
        for listing in self.recent_listings:
            if listing.symbol == symbol and listing.detected_at > cutoff:
                return True
        return False
    
    def on_new_listing(self, callback: Callable):
        """Register callback for new listings"""
        self._callbacks.append(callback)
    
    async def start(self):
        """Start the detector"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)
        self._running = True

        
        # Initial symbol fetch
        await self._fetch_current_symbols()
        
        logger.info(f"📡 Listings Detector started - tracking {len(self.known_symbols)} symbols")
        
        # Start monitoring loop
        asyncio.create_task(self._monitor_loop())
    
    async def stop(self):
        """Stop the detector"""
        self._running = False
        if self._session:
            await self._session.close()
    
    async def _fetch_current_symbols(self) -> Set[str]:
        """Fetch current futures symbols from MEXC"""
        try:
            async with self._session.get(self.FUTURES_SYMBOLS_URL) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if data.get('success') and data.get('data'):
                        symbols = set()
                        for item in data['data']:
                            symbol = item.get('symbol', '')
                            if symbol:
                                symbols.add(symbol)
                                
                                # Store additional info
                                if symbol not in self.known_symbols:
                                    self.known_symbols.add(symbol)
                        
                        return symbols
        except Exception as e:
            logger.error(f"Error fetching symbols: {e}")
        
        return set()
    
    async def _monitor_loop(self):
        """Main monitoring loop"""
        while self._running:
            try:
                await self._check_for_new_listings()
                self.stats['checks_performed'] += 1
                self.stats['last_check'] = datetime.now().isoformat()
                
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(10)
    
    async def _check_for_new_listings(self):
        """Check for new listings"""
        current_symbols = await self._fetch_current_symbols()
        
        # Find new symbols
        new_symbols = current_symbols - self.known_symbols
        
        for symbol in new_symbols:
            logger.info(f"🆕 NEW LISTING DETECTED: {symbol}")
            
            listing = await self._create_listing(symbol)
            
            self.new_listings[symbol] = listing
            self.recent_listings.append(listing)
            self.stats['new_listings_found'] += 1
            
            # Notify callbacks
            await self._notify_new_listing(listing)
        
        # Update known symbols
        self.known_symbols = current_symbols
        
        # Cleanup old listings (keep last 24h)
        cutoff = int(time.time() * 1000) - (24 * 3600 * 1000)
        self.recent_listings = [l for l in self.recent_listings if l.detected_at > cutoff]
    
    async def _create_listing(self, symbol: str) -> NewListing:
        """Create listing object with initial data"""
        now = int(time.time() * 1000)
        
        # Parse symbol
        base_asset = symbol.replace("_USDT", "").replace("USDT", "")
        
        listing = NewListing(
            symbol=symbol,
            base_asset=base_asset,
            quote_asset="USDT",
            detected_at=now,
            trading_start=now,
            status=ListingStatus.LIVE
        )
        
        # Try to get initial price
        try:
            price_data = await self._fetch_ticker(symbol)
            if price_data:
                listing.initial_price = price_data.get('lastPrice', 0)
                listing.current_price = listing.initial_price
                listing.volume_usd = price_data.get('volume24', 0)
        except:
            pass
        
        # Calculate pump potential based on various factors
        listing.pump_potential = self._calculate_pump_potential(listing)
        listing.risk_level = self._calculate_risk_level(listing)
        
        return listing
    
    async def _fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """Fetch ticker data for symbol"""
        try:
            url = f"https://contract.mexc.com/api/v1/contract/ticker?symbol={symbol}"
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success') and data.get('data'):
                        return data['data']
        except:
            pass
        return None
    
    def _calculate_pump_potential(self, listing: NewListing) -> int:
        """Calculate pump potential score (0-100)"""
        score = 50  # Base score
        
        # New listings often pump
        time_since = listing.time_since_listing()
        if time_since < 300:  # First 5 minutes
            score += 30
        elif time_since < 900:  # First 15 minutes
            score += 20
        elif time_since < 3600:  # First hour
            score += 10
        
        # High initial volume = more interest
        if listing.volume_usd > 1_000_000:
            score += 15
        elif listing.volume_usd > 500_000:
            score += 10
        elif listing.volume_usd > 100_000:
            score += 5
        
        return min(100, max(0, score))
    
    def _calculate_risk_level(self, listing: NewListing) -> str:
        """Calculate risk level"""
        # New listings are inherently risky
        if listing.time_since_listing() < 300:
            return "EXTREME"
        elif listing.time_since_listing() < 900:
            return "HIGH"
        elif listing.time_since_listing() < 3600:
            return "MEDIUM"
        else:
            return "STANDARD"
    
    async def _notify_new_listing(self, listing: NewListing):
        """Notify callbacks about new listing"""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(listing)
                else:
                    callback(listing)
            except Exception as e:
                logger.error(f"Listing callback error: {e}")
    
    async def update_listing_price(self, symbol: str, price: float, volume: float = 0):
        """Update listing with current price"""
        if symbol in self.new_listings:
            listing = self.new_listings[symbol]
            listing.current_price = price
            
            if listing.initial_price and listing.initial_price > 0:
                listing.price_change_pct = ((price - listing.initial_price) / listing.initial_price) * 100
            
            if volume:
                listing.volume_usd = volume
            
            listing.pump_potential = self._calculate_pump_potential(listing)
    
    def get_hot_listings(self, max_age_minutes: int = 60) -> List[NewListing]:
        """Get recent listings sorted by pump potential"""
        cutoff = int(time.time() * 1000) - (max_age_minutes * 60 * 1000)
        
        recent = [l for l in self.recent_listings if l.detected_at > cutoff]
        return sorted(recent, key=lambda l: l.pump_potential, reverse=True)
    
    def get_listings_by_status(self, status: ListingStatus) -> List[NewListing]:
        """Get listings by status"""
        return [l for l in self.new_listings.values() if l.status == status]


@dataclass
class TokenDistribution:
    """Token distribution breakdown"""
    team_pct: float = 0           # Team/Founders
    investors_pct: float = 0      # VCs, Private Sale
    airdrop_pct: float = 0        # Community airdrop
    public_sale_pct: float = 0    # Public ICO/IDO
    liquidity_pct: float = 0      # DEX/CEX liquidity
    ecosystem_pct: float = 0      # Ecosystem/Development
    staking_pct: float = 0        # Staking rewards
    treasury_pct: float = 0       # DAO Treasury
    marketing_pct: float = 0      # Marketing
    advisors_pct: float = 0       # Advisors
    other_pct: float = 0          # Other/Unknown
    
    # Vesting info
    team_vesting_months: int = 0
    team_cliff_months: int = 0
    investor_vesting_months: int = 0
    
    # Unlock schedule 
    next_unlock_date: Optional[str] = None
    next_unlock_pct: float = 0
    next_unlock_category: str = ""
    
    # Risk indicators
    team_unlocked_pct: float = 0  # Already unlocked team tokens
    insider_concentration: float = 0  # Team + VCs combined
    
    def get_community_pct(self) -> float:
        """Get % going to community"""
        return self.airdrop_pct + self.public_sale_pct + self.ecosystem_pct
    
    def get_insider_pct(self) -> float:
        """Get % held by insiders"""
        return self.team_pct + self.investors_pct + self.advisors_pct
    
    def is_fair_launch(self) -> bool:
        """Check if relatively fair distribution"""
        return self.get_insider_pct() < 30
    
    def to_dict(self) -> Dict:
        return {
            'team': self.team_pct,
            'investors': self.investors_pct,
            'airdrop': self.airdrop_pct,
            'public_sale': self.public_sale_pct,
            'liquidity': self.liquidity_pct,
            'ecosystem': self.ecosystem_pct,
            'staking': self.staking_pct,
            'treasury': self.treasury_pct,
            'marketing': self.marketing_pct,
            'advisors': self.advisors_pct,
            'community_total': self.get_community_pct(),
            'insider_total': self.get_insider_pct(),
            'is_fair_launch': self.is_fair_launch(),
            'next_unlock': {
                'date': self.next_unlock_date,
                'pct': self.next_unlock_pct,
                'category': self.next_unlock_category
            },
            'team_vesting_months': self.team_vesting_months
        }
    
    def format_table(self) -> str:
        """Format as readable table"""
        lines = ["📊 TOKEN DISTRIBUTION", "━" * 30]
        
        if self.team_pct > 0:
            lines.append(f"👨‍💻 Team:        {self.team_pct:>5.1f}%")
        if self.investors_pct > 0:
            lines.append(f"💰 Investors:   {self.investors_pct:>5.1f}%")
        if self.advisors_pct > 0:
            lines.append(f"🎓 Advisors:    {self.advisors_pct:>5.1f}%")
        if self.airdrop_pct > 0:
            lines.append(f"🎁 Airdrop:     {self.airdrop_pct:>5.1f}%")
        if self.public_sale_pct > 0:
            lines.append(f"🛒 Public Sale: {self.public_sale_pct:>5.1f}%")
        if self.liquidity_pct > 0:
            lines.append(f"💧 Liquidity:   {self.liquidity_pct:>5.1f}%")
        if self.ecosystem_pct > 0:
            lines.append(f"🌐 Ecosystem:   {self.ecosystem_pct:>5.1f}%")
        if self.staking_pct > 0:
            lines.append(f"📈 Staking:     {self.staking_pct:>5.1f}%")
        if self.treasury_pct > 0:
            lines.append(f"🏦 Treasury:    {self.treasury_pct:>5.1f}%")
        if self.marketing_pct > 0:
            lines.append(f"📢 Marketing:   {self.marketing_pct:>5.1f}%")
        
        lines.append("━" * 30)
        lines.append(f"👥 Community:   {self.get_community_pct():>5.1f}%")
        lines.append(f"🔒 Insiders:    {self.get_insider_pct():>5.1f}%")
        
        if self.team_vesting_months > 0:
            lines.append("")
            lines.append(f"⏳ Team Vesting: {self.team_vesting_months} months")
            if self.team_cliff_months > 0:
                lines.append(f"🔐 Cliff: {self.team_cliff_months} months")
        
        if self.next_unlock_date:
            lines.append("")
            lines.append(f"⚠️ Next Unlock: {self.next_unlock_date}")
            lines.append(f"   {self.next_unlock_pct}% ({self.next_unlock_category})")
        
        # Risk warning
        if self.get_insider_pct() > 50:
            lines.append("")
            lines.append("🚨 HIGH INSIDER CONCENTRATION!")
        elif not self.is_fair_launch():
            lines.append("")
            lines.append("⚠️ High insider allocation")
        
        return "\n".join(lines)


@dataclass
class TokenInfo:
    """Token information and tokenomics"""
    symbol: str
    name: str
    
    # Supply data
    total_supply: float = 0
    circulating_supply: float = 0
    max_supply: Optional[float] = None
    
    # Market data
    market_cap: float = 0
    fully_diluted_valuation: float = 0
    
    # Price
    price_usd: float = 0
    price_change_24h: float = 0
    price_change_7d: float = 0
    
    # Volume
    volume_24h: float = 0
    
    # Holders (if available)
    holder_count: Optional[int] = None
    top_10_holders_pct: Optional[float] = None
    
    # Distribution breakdown
    distribution: Optional[TokenDistribution] = None
    
    # Risk factors
    is_meme: bool = False
    is_new: bool = False
    low_liquidity: bool = False
    high_concentration: bool = False
    
    # Links
    website: Optional[str] = None
    twitter: Optional[str] = None
    telegram: Optional[str] = None
    
    # Calculated scores
    tokenomics_score: int = 50  # 0-100
    risk_score: int = 50  # 0-100 (higher = riskier)
    
    def get_unlock_risk(self) -> str:
        """Assess unlock/vesting risk"""
        if self.distribution and self.distribution.next_unlock_pct > 10:
            return "HIGH"
        if self.fully_diluted_valuation > 0 and self.market_cap > 0:
            ratio = self.market_cap / self.fully_diluted_valuation
            if ratio < 0.2:
                return "HIGH"
            elif ratio < 0.5:
                return "MEDIUM"
        return "LOW"
    
    def format_full_report(self) -> str:
        """Format full tokenomics report"""
        circ_pct = (self.circulating_supply / self.total_supply * 100) if self.total_supply > 0 else 0
        mcap_fdv_ratio = (self.market_cap / self.fully_diluted_valuation * 100) if self.fully_diluted_valuation > 0 else 0
        
        lines = [
            f"🪙 {self.name} ({self.symbol})",
            "━" * 35,
            "",
            "💰 MARKET DATA",
            f"├ Price: ${self.price_usd:.8f}",
            f"├ 24h Change: {self.price_change_24h:+.1f}%",
            f"├ Market Cap: ${self.market_cap:,.0f}",
            f"├ FDV: ${self.fully_diluted_valuation:,.0f}",
            f"├ Volume 24h: ${self.volume_24h:,.0f}",
            f"└ MCap/FDV: {mcap_fdv_ratio:.1f}%",
            "",
            "📦 SUPPLY",
            f"├ Circulating: {self.circulating_supply:,.0f} ({circ_pct:.1f}%)",
            f"├ Total: {self.total_supply:,.0f}",
            f"└ Max: {self.max_supply:,.0f}" if self.max_supply else "└ Max: ∞",
        ]
        
        # Add distribution if available
        if self.distribution:
            lines.append("")
            lines.append(self.distribution.format_table())
        
        # Risk assessment
        lines.extend([
            "",
            "⚠️ RISK FACTORS",
            f"├ Is Meme: {'✅ YES' if self.is_meme else '❌ No'}",
            f"├ Is New (<30d): {'✅ YES' if self.is_new else '❌ No'}",
            f"├ Low Liquidity: {'✅ YES' if self.low_liquidity else '❌ No'}",
            f"├ Unlock Risk: {self.get_unlock_risk()}",
            f"└ Risk Score: {self.risk_score}/100",
        ])
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'total_supply': self.total_supply,
            'circulating_supply': self.circulating_supply,
            'market_cap': self.market_cap,
            'fdv': self.fully_diluted_valuation,
            'price_usd': self.price_usd,
            'price_change_24h': self.price_change_24h,
            'volume_24h': self.volume_24h,
            'holder_count': self.holder_count,
            'distribution': self.distribution.to_dict() if self.distribution else None,
            'tokenomics_score': self.tokenomics_score,
            'risk_score': self.risk_score,
            'is_meme': self.is_meme,
            'unlock_risk': self.get_unlock_risk(),
            'links': {
                'website': self.website,
                'twitter': self.twitter
            }
        }


class TokenomicsFetcher:
    """
    Fetches tokenomics data from multiple sources:
    - CoinGecko
    - DeFiLlama (unlocks)
    - Known tokens database
    """
    
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    DEFILLAMA_UNLOCKS_API = "https://api.llama.fi/protocol"
    
    # Known meme coins
    MEME_KEYWORDS = ['doge', 'shib', 'pepe', 'floki', 'bonk', 'wojak', 'chad', 'meme', 'inu', 'elon']
    
    # Known token distributions (pre-populated for common tokens)
    KNOWN_DISTRIBUTIONS = {
        'ARB': TokenDistribution(
            team_pct=26.9, investors_pct=17.5, airdrop_pct=11.5,
            ecosystem_pct=42.8, treasury_pct=1.3,
            team_vesting_months=48, team_cliff_months=12,
            next_unlock_date="2024-03-16", next_unlock_pct=2.75, next_unlock_category="Team"
        ),
        'OP': TokenDistribution(
            team_pct=19, investors_pct=17, airdrop_pct=19,
            ecosystem_pct=25, treasury_pct=20,
            team_vesting_months=48, team_cliff_months=12
        ),
        'APT': TokenDistribution(
            team_pct=19, investors_pct=13.5, ecosystem_pct=51.5,
            treasury_pct=16, team_vesting_months=48, team_cliff_months=12
        ),
        'SUI': TokenDistribution(
            team_pct=20, investors_pct=14, ecosystem_pct=50,
            treasury_pct=10, airdrop_pct=6,
            team_vesting_months=48, team_cliff_months=12
        ),
        'SEI': TokenDistribution(
            team_pct=20, investors_pct=20, airdrop_pct=3,
            ecosystem_pct=48, treasury_pct=9,
            team_vesting_months=48, team_cliff_months=12
        ),
        'TIA': TokenDistribution(
            team_pct=20, investors_pct=19.7, airdrop_pct=7.4,
            ecosystem_pct=26.8, public_sale_pct=26.1,
            team_vesting_months=48, team_cliff_months=12
        ),
        'JUP': TokenDistribution(
            team_pct=50, airdrop_pct=40, ecosystem_pct=10,
            team_vesting_months=24
        ),
        'STRK': TokenDistribution(
            team_pct=17, investors_pct=17, airdrop_pct=9,
            ecosystem_pct=50.1, treasury_pct=6.9,
            team_vesting_months=48, team_cliff_months=12
        ),
        'WLD': TokenDistribution(
            team_pct=25, investors_pct=13.5, airdrop_pct=43,
            ecosystem_pct=18.5,
            team_vesting_months=36, team_cliff_months=12
        ),
        'BLUR': TokenDistribution(
            team_pct=29, investors_pct=20, airdrop_pct=12,
            ecosystem_pct=39,
            team_vesting_months=48, team_cliff_months=12
        ),
        'PYTH': TokenDistribution(
            team_pct=22, investors_pct=10, airdrop_pct=6,
            ecosystem_pct=52, treasury_pct=10,
            team_vesting_months=36, team_cliff_months=6
        ),
        'JTO': TokenDistribution(
            team_pct=24.5, investors_pct=16.2, airdrop_pct=10,
            ecosystem_pct=34.3, treasury_pct=15,
            team_vesting_months=36, team_cliff_months=12
        ),
        'PEPE': TokenDistribution(
            liquidity_pct=93.1, ecosystem_pct=6.9,
            team_pct=0, investors_pct=0  # "Fair launch"
        ),
        'BONK': TokenDistribution(
            airdrop_pct=50, ecosystem_pct=20, marketing_pct=15,
            liquidity_pct=15, team_pct=0
        ),
        'DOGE': TokenDistribution(
            ecosystem_pct=100  # Mined, no team allocation
        ),
        'SHIB': TokenDistribution(
            liquidity_pct=50, ecosystem_pct=50  # Burned to VB
        ),
        'WIF': TokenDistribution(
            airdrop_pct=0, liquidity_pct=100, team_pct=0  # Fair launch
        ),
    }
    
    _coin_id_cache: Dict[str, str] = {} # Class-level cache for symbol -> coin_id
    
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, TokenInfo] = {}
        self._cache_ttl = 1800  # 30 minutes (longer cache for tokenomics)
        self._cache_times: Dict[str, float] = {}
    
    async def start(self):
        """Initialize session"""
        import ssl
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)

    
    async def stop(self):
        """Close session"""
        if self._session:
            await self._session.close()
    
    async def get_tokenomics(self, symbol: str) -> Optional[TokenInfo]:
        """
        Get tokenomics for a symbol
        
        Args:
            symbol: Token symbol (e.g., 'BTC', 'ETH')
        
        Returns:
            TokenInfo with all available data
        """
        # Check cache
        if symbol in self._cache:
            cache_time = self._cache_times.get(symbol, 0)
            if time.time() - cache_time < self._cache_ttl:
                return self._cache[symbol]
        
        # Fetch from CoinGecko
        token_info = await self._fetch_coingecko(symbol)
        
        if token_info:
            # Add known distribution if available
            symbol_upper = symbol.upper()
            if symbol_upper in self.KNOWN_DISTRIBUTIONS:
                token_info.distribution = self.KNOWN_DISTRIBUTIONS[symbol_upper]
            
            # Calculate scores
            token_info.tokenomics_score = self._calculate_tokenomics_score(token_info)
            token_info.risk_score = self._calculate_risk_score(token_info)
            
            # Cache
            self._cache[symbol] = token_info
            self._cache_times[symbol] = time.time()
        
        return token_info
    
    async def _fetch_coingecko(self, symbol: str) -> Optional[TokenInfo]:
        """Fetch from CoinGecko API"""
        if not self._session:
            await self.start()
        
        try:
            # 1. Check ID cache first
            coin_id = self._coin_id_cache.get(symbol.upper())
            
            if not coin_id:
                # 2. Search for coin
                search_url = f"{self.COINGECKO_API}/search?query={symbol}"
                async with self._session.get(search_url) as resp:
                    if resp.status == 429:
                        logger.warning(f"⚠️ CoinGecko Rate Limited (429) for {symbol}")
                        return None
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    coins = data.get('coins', [])
                    
                    if not coins:
                        logger.debug(f"🔍 No CoinGecko results for {symbol}")
                        return None
                    
                    # Exact symbol match
                    for coin in coins:
                        if coin.get('symbol', '').upper() == symbol.upper():
                            coin_id = coin.get('id')
                            break
                    
                    # Fuzzy match fallback (if symbol is part of the name or vice versa)
                    if not coin_id:
                        for coin in coins[:3]: # Check top 3 results
                            if symbol.upper() in coin.get('name', '').upper():
                                coin_id = coin.get('id')
                                break
                    
                    if not coin_id:
                        coin_id = coins[0].get('id')
                        
                if coin_id:
                    self._coin_id_cache[symbol.upper()] = coin_id

            if not coin_id:
                return None
            
            # Get detailed info
            coin_url = f"{self.COINGECKO_API}/coins/{coin_id}"
            async with self._session.get(coin_url) as resp:
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                
                market_data = data.get('market_data', {})
                
                token = TokenInfo(
                    symbol=symbol.upper(),
                    name=data.get('name', symbol),
                    total_supply=market_data.get('total_supply') or 0,
                    circulating_supply=market_data.get('circulating_supply') or 0,
                    max_supply=market_data.get('max_supply'),
                    market_cap=market_data.get('market_cap', {}).get('usd', 0),
                    fully_diluted_valuation=market_data.get('fully_diluted_valuation', {}).get('usd', 0),
                    price_usd=market_data.get('current_price', {}).get('usd', 0),
                    price_change_24h=market_data.get('price_change_percentage_24h') or 0,
                    price_change_7d=market_data.get('price_change_percentage_7d') or 0,
                    volume_24h=market_data.get('total_volume', {}).get('usd', 0),
                    website=data.get('links', {}).get('homepage', [None])[0],
                    twitter=data.get('links', {}).get('twitter_screen_name')
                )
                
                # Check if it's a meme coin
                name_lower = token.name.lower()
                symbol_lower = token.symbol.lower()
                categories = [c.lower() for c in data.get('categories', [])]
                
                token.is_meme = any(
                    kw in name_lower or kw in symbol_lower or 
                    any(kw in cat for cat in categories)
                    for kw in self.MEME_KEYWORDS
                ) or 'meme' in categories
                
                # Check if new (less than 30 days)
                genesis_date = data.get('genesis_date')
                if genesis_date:
                    try:
                        genesis = datetime.fromisoformat(genesis_date)
                        days_old = (datetime.now() - genesis).days
                        token.is_new = days_old < 30
                    except:
                        pass
                
                # Check liquidity
                if token.volume_24h < 100_000:
                    token.low_liquidity = True
                
                return token
                
        except Exception as e:
            logger.error(f"CoinGecko fetch error for {symbol}: {e}")
            return None
    
    def _calculate_tokenomics_score(self, token: TokenInfo) -> int:
        """Calculate tokenomics health score (0-100)"""
        score = 50
        
        # Good circulating/total ratio
        if token.total_supply > 0:
            circ_ratio = token.circulating_supply / token.total_supply
            if circ_ratio > 0.8:
                score += 20
            elif circ_ratio > 0.5:
                score += 10
            elif circ_ratio < 0.2:
                score -= 20
        
        # Market cap vs FDV
        if token.fully_diluted_valuation > 0 and token.market_cap > 0:
            mcap_fdv_ratio = token.market_cap / token.fully_diluted_valuation
            if mcap_fdv_ratio > 0.7:
                score += 15
            elif mcap_fdv_ratio < 0.3:
                score -= 15
        
        # Volume to market cap ratio (liquidity)
        if token.market_cap > 0:
            vol_mcap_ratio = token.volume_24h / token.market_cap
            if vol_mcap_ratio > 0.3:
                score += 10
            elif vol_mcap_ratio < 0.01:
                score -= 10
        
        # Established project (higher mcap)
        if token.market_cap > 1_000_000_000:
            score += 10
        elif token.market_cap < 10_000_000:
            score -= 10
        
        return max(0, min(100, score))
    
    def _calculate_risk_score(self, token: TokenInfo) -> int:
        """Calculate risk score (0-100, higher = riskier)"""
        risk = 30  # Base risk
        
        if token.is_meme:
            risk += 25
        
        if token.is_new:
            risk += 20
        
        if token.low_liquidity:
            risk += 20
        
        if token.high_concentration:
            risk += 15
        
        # Low market cap = higher risk
        if token.market_cap < 10_000_000:
            risk += 15
        elif token.market_cap < 100_000_000:
            risk += 10
        
        # High price volatility
        if abs(token.price_change_24h) > 20:
            risk += 10
        
        return max(0, min(100, risk))
    
    async def enrich_listing(self, listing: NewListing) -> NewListing:
        """Enrich listing with tokenomics data"""
        token_info = await self.get_tokenomics(listing.base_asset)
        
        if token_info:
            listing.tokenomics = token_info.to_dict()
            
            # Adjust pump potential based on tokenomics
            if token_info.is_meme:
                listing.pump_potential = min(100, listing.pump_potential + 10)
            
            if token_info.is_new:
                listing.pump_potential = min(100, listing.pump_potential + 15)
            
            if token_info.low_liquidity:
                listing.risk_level = "EXTREME"
        
        return listing
    
    async def fetch_token_unlocks(self, symbol: str) -> Optional[Dict]:
        """
        Fetch unlock schedule from Token Unlocks API
        Source: https://token.unlocks.app
        """
        if not self._session:
            await self.start()
        
        try:
            # Token Unlocks API (public endpoint)
            url = f"https://token.unlocks.app/api/v2/coins/{symbol.lower()}"
            
            async with self._session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    unlocks = []
                    for event in data.get('unlock_events', [])[:5]:
                        unlocks.append({
                            'date': event.get('date'),
                            'amount': event.get('amount'),
                            'pct': event.get('percentage', 0),
                            'category': event.get('category', 'Unknown'),
                            'usd_value': event.get('usd_value', 0)
                        })
                    
                    return {
                        'symbol': symbol,
                        'total_locked_pct': data.get('total_locked_percentage', 0),
                        'circulating_pct': data.get('circulating_percentage', 0),
                        'next_unlock': unlocks[0] if unlocks else None,
                        'upcoming_unlocks': unlocks,
                        'cliff_end_date': data.get('cliff_end_date'),
                        'vesting_end_date': data.get('vesting_end_date')
                    }
        except Exception as e:
            logger.debug(f"Token Unlocks fetch error for {symbol}: {e}")
        
        return None
    
    async def fetch_defillama_unlocks(self, protocol: str) -> Optional[Dict]:
        """
        Fetch token data from DeFiLlama
        Source: https://defillama.com
        """
        if not self._session:
            await self.start()
        
        try:
            url = f"https://api.llama.fi/protocol/{protocol.lower()}"
            
            async with self._session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    return {
                        'name': data.get('name'),
                        'symbol': data.get('symbol'),
                        'tvl': data.get('tvl', 0),
                        'mcap': data.get('mcap', 0),
                        'fdv': data.get('fdv', 0),
                        'category': data.get('category'),
                        'chains': data.get('chains', []),
                        'twitter': data.get('twitter'),
                        'url': data.get('url')
                    }
        except Exception as e:
            logger.debug(f"DeFiLlama fetch error for {protocol}: {e}")
        
        return None
    
    def get_research_links(self, symbol: str) -> Dict[str, str]:
        """
        Get research links for manual verification
        """
        symbol_lower = symbol.lower()
        symbol_upper = symbol.upper()
        
        return {
            'coingecko': f"https://www.coingecko.com/en/coins/{symbol_lower}",
            'coinmarketcap': f"https://coinmarketcap.com/currencies/{symbol_lower}/",
            'token_unlocks': f"https://token.unlocks.app/{symbol_lower}",
            'messari': f"https://messari.io/project/{symbol_lower}",
            'defillama': f"https://defillama.com/protocol/{symbol_lower}",
            'dune': f"https://dune.com/search?q={symbol_upper}",
            'etherscan': f"https://etherscan.io/token/{symbol_lower}",
            'whitepaper_search': f"https://www.google.com/search?q={symbol_upper}+tokenomics+whitepaper"
        }
    
    def format_research_links(self, symbol: str) -> str:
        """Format research links as readable list"""
        links = self.get_research_links(symbol)
        
        lines = [
            f"🔍 RESEARCH LINKS: {symbol.upper()}",
            "━" * 35,
            f"📊 CoinGecko: {links['coingecko']}",
            f"📈 CoinMarketCap: {links['coinmarketcap']}",
            f"🔓 Token Unlocks: {links['token_unlocks']}",
            f"📋 Messari: {links['messari']}",
            f"📺 DeFiLlama: {links['defillama']}",
            f"📘 Whitepaper: {links['whitepaper_search']}",
        ]
        
        return "\n".join(lines)
    
    async def get_full_tokenomics(self, symbol: str) -> Dict:
        """
        Get comprehensive tokenomics from all sources
        """
        result = {
            'symbol': symbol,
            'sources': [],
            'data': {}
        }
        
        # 1. CoinGecko (basic data)
        token_info = await self.get_tokenomics(symbol)
        if token_info:
            result['sources'].append('coingecko')
            result['data']['basic'] = token_info.to_dict()
            result['data']['full_report'] = token_info.format_full_report()
        
        # 2. Known distribution
        if symbol.upper() in self.KNOWN_DISTRIBUTIONS:
            result['sources'].append('known_db')
            dist = self.KNOWN_DISTRIBUTIONS[symbol.upper()]
            result['data']['distribution'] = dist.to_dict()
            result['data']['distribution_table'] = dist.format_table()
        
        # 3. Token Unlocks
        unlocks = await self.fetch_token_unlocks(symbol)
        if unlocks:
            result['sources'].append('token_unlocks')
            result['data']['unlocks'] = unlocks
        
        # 4. DeFiLlama
        llama = await self.fetch_defillama_unlocks(symbol)
        if llama:
            result['sources'].append('defillama')
            result['data']['protocol'] = llama
        
        # 5. Research links
        result['data']['research_links'] = self.get_research_links(symbol)
        
        return result
    
    def format_telegram_tokenomics(self, symbol: str, data: Dict) -> str:
        """Format tokenomics for Telegram message"""
        lines = [f"🪙 <b>TOKENOMICS: {symbol.upper()}</b>"]
        lines.append("━" * 30)
        
        # Basic data
        basic = data.get('data', {}).get('basic', {})
        if basic:
            lines.append(f"💰 Price: ${basic.get('price_usd', 0):.8f}")
            lines.append(f"📊 MCap: ${basic.get('market_cap', 0):,.0f}")
            lines.append(f"📈 FDV: ${basic.get('fdv', 0):,.0f}")
            if basic.get('market_cap') and basic.get('fdv'):
                ratio = basic['market_cap'] / basic['fdv'] * 100
                lines.append(f"🔒 MCap/FDV: {ratio:.1f}%")
        
        # Distribution
        dist = data.get('data', {}).get('distribution', {})
        if dist:
            lines.append("")
            lines.append("<b>📊 DISTRIBUTION:</b>")
            if dist.get('team'):
                lines.append(f"├ 👨‍💻 Team: {dist['team']}%")
            if dist.get('investors'):
                lines.append(f"├ 💰 Investors: {dist['investors']}%")
            if dist.get('airdrop'):
                lines.append(f"├ 🎁 Airdrop: {dist['airdrop']}%")
            if dist.get('ecosystem'):
                lines.append(f"├ 🌐 Ecosystem: {dist['ecosystem']}%")
            lines.append(f"├ 👥 Community: {dist.get('community_total', 0):.1f}%")
            lines.append(f"└ 🔒 Insiders: {dist.get('insider_total', 0):.1f}%")
            
            if dist.get('team_vesting_months'):
                lines.append(f"\n⏳ Vesting: {dist['team_vesting_months']} months")
        
        # Unlocks
        unlocks = data.get('data', {}).get('unlocks', {})
        if unlocks and unlocks.get('next_unlock'):
            nu = unlocks['next_unlock']
            lines.append("")
            lines.append("<b>🔓 NEXT UNLOCK:</b>")
            lines.append(f"├ Date: {nu.get('date', 'TBD')}")
            lines.append(f"├ Amount: {nu.get('pct', 0):.1f}%")
            lines.append(f"└ Category: {nu.get('category', 'Unknown')}")
        
        # Risk flags
        if basic.get('is_meme'):
            lines.append("\n⚠️ <b>MEME COIN - HIGH RISK</b>")
        if dist and dist.get('insider_total', 0) > 50:
            lines.append("🚨 <b>HIGH INSIDER CONCENTRATION!</b>")
        
        # Sources
        sources = data.get('sources', [])
        if sources:
            lines.append(f"\n📍 Sources: {', '.join(sources)}")
        
        return "\n".join(lines)

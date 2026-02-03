"""
MEXC Pump Monitor - Social Sentiment Analyzer
Twitter/Reddit/Telegram mention tracking and sentiment analysis
"""

import asyncio
import aiohttp
import time
import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """Sentiment levels"""
    EXTREME_FEAR = "EXTREME_FEAR"
    FEAR = "FEAR"
    NEUTRAL = "NEUTRAL"
    GREED = "GREED"
    EXTREME_GREED = "EXTREME_GREED"


@dataclass
class SocialMention:
    """Social media mention"""
    platform: str  # twitter, reddit, telegram
    symbol: str
    text: str
    timestamp: int
    
    # Sentiment
    sentiment_score: float = 0  # -1 to 1
    sentiment: str = "NEUTRAL"
    
    # Engagement
    likes: int = 0
    retweets: int = 0
    comments: int = 0
    
    # Influence
    author_followers: int = 0
    is_influencer: bool = False


@dataclass
class SymbolSentiment:
    """Aggregated sentiment for a symbol"""
    symbol: str
    
    # Mention counts
    mentions_1h: int = 0
    mentions_24h: int = 0
    mention_change_pct: float = 0  # vs previous hour
    
    # Sentiment scores
    avg_sentiment: float = 0  # -1 to 1
    sentiment_level: SentimentLevel = SentimentLevel.NEUTRAL
    positive_pct: float = 0
    negative_pct: float = 0
    
    # Trending
    is_trending: bool = False
    trending_rank: int = 0
    
    # Influencer activity
    influencer_mentions: int = 0
    
    # Keywords
    top_keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'mentions_1h': self.mentions_1h,
            'mentions_24h': self.mentions_24h,
            'mention_change_pct': self.mention_change_pct,
            'avg_sentiment': self.avg_sentiment,
            'sentiment_level': self.sentiment_level.value,
            'positive_pct': self.positive_pct,
            'is_trending': self.is_trending,
            'influencer_mentions': self.influencer_mentions
        }


class SentimentAnalyzer:
    """
    Social sentiment analysis engine
    Tracks mentions across Twitter, Reddit, Telegram
    """
    
    # Positive keywords (crypto context)
    POSITIVE_WORDS = {
        'moon', 'pump', 'bullish', 'rocket', 'explode', 'breakout', 'ath',
        'gem', 'alpha', 'buy', 'long', 'gains', 'profit', 'rich', 'lambo',
        'massive', 'huge', 'green', 'up', 'mooning', '100x', '10x', '1000x',
        'undervalued', 'accumulate', 'hodl', 'hold', 'strong', 'solid'
    }
    
    # Negative keywords
    NEGATIVE_WORDS = {
        'dump', 'crash', 'bearish', 'scam', 'rug', 'rugpull', 'dead', 'rip',
        'sell', 'short', 'fear', 'panic', 'loss', 'rekt', 'liquidated',
        'bleeding', 'red', 'down', 'falling', 'dropping', 'tanking',
        'overvalued', 'bubble', 'ponzi', 'exit', 'caution', 'warning'
    }
    
    # Influencer threshold
    INFLUENCER_FOLLOWERS = 50000
    
    def __init__(self):
        # Mention history per symbol
        self.mentions: Dict[str, deque] = {}
        self.max_mentions = 1000
        
        # Aggregated sentiment
        self.sentiment_cache: Dict[str, SymbolSentiment] = {}
        
        # Global trending
        self.trending_symbols: List[Tuple[str, int]] = []
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.stats = {
            'mentions_processed': 0,
            'positive_mentions': 0,
            'negative_mentions': 0
        }
    
    async def start(self):
        """Initialize"""
        self._session = aiohttp.ClientSession()
        logger.info("🐦 Sentiment Analyzer started")
    
    async def stop(self):
        """Cleanup"""
        if self._session:
            await self._session.close()
    
    def analyze_text(self, text: str) -> Tuple[float, str]:
        """
        Analyze sentiment of text
        
        Returns:
            (score, sentiment) where score is -1 to 1
        """
        text_lower = text.lower()
        words = set(re.findall(r'\w+', text_lower))
        
        positive_count = len(words & self.POSITIVE_WORDS)
        negative_count = len(words & self.NEGATIVE_WORDS)
        
        total = positive_count + negative_count
        
        if total == 0:
            return 0, "NEUTRAL"
        
        score = (positive_count - negative_count) / total
        
        if score > 0.3:
            sentiment = "POSITIVE"
        elif score < -0.3:
            sentiment = "NEGATIVE"
        else:
            sentiment = "NEUTRAL"
        
        return score, sentiment
    
    def record_mention(
        self,
        platform: str,
        symbol: str,
        text: str,
        likes: int = 0,
        retweets: int = 0,
        author_followers: int = 0
    ):
        """Record a social media mention"""
        score, sentiment = self.analyze_text(text)
        
        mention = SocialMention(
            platform=platform,
            symbol=symbol.upper(),
            text=text[:500],  # Truncate
            timestamp=int(time.time() * 1000),
            sentiment_score=score,
            sentiment=sentiment,
            likes=likes,
            retweets=retweets,
            author_followers=author_followers,
            is_influencer=author_followers >= self.INFLUENCER_FOLLOWERS
        )
        
        # Store
        if symbol not in self.mentions:
            self.mentions[symbol] = deque(maxlen=self.max_mentions)
        
        self.mentions[symbol].append(mention)
        
        # Update stats
        self.stats['mentions_processed'] += 1
        if sentiment == "POSITIVE":
            self.stats['positive_mentions'] += 1
        elif sentiment == "NEGATIVE":
            self.stats['negative_mentions'] += 1
        
        return mention
    
    def get_symbol_sentiment(self, symbol: str) -> SymbolSentiment:
        """Get aggregated sentiment for symbol"""
        symbol = symbol.upper()
        
        if symbol not in self.mentions:
            return SymbolSentiment(symbol=symbol)
        
        mentions = list(self.mentions[symbol])
        now = int(time.time() * 1000)
        hour_ago = now - 3600000
        day_ago = now - 86400000
        
        # Filter by time
        mentions_1h = [m for m in mentions if m.timestamp > hour_ago]
        mentions_24h = [m for m in mentions if m.timestamp > day_ago]
        
        # Previous hour for change calculation
        prev_hour = now - 7200000
        mentions_prev_h = [m for m in mentions if prev_hour < m.timestamp <= hour_ago]
        
        # Calculate change
        prev_count = len(mentions_prev_h) or 1
        change_pct = ((len(mentions_1h) - prev_count) / prev_count) * 100
        
        # Sentiment analysis
        if mentions_24h:
            scores = [m.sentiment_score for m in mentions_24h]
            avg_score = sum(scores) / len(scores)
            
            positive = len([m for m in mentions_24h if m.sentiment == "POSITIVE"])
            negative = len([m for m in mentions_24h if m.sentiment == "NEGATIVE"])
            total = len(mentions_24h)
            
            positive_pct = (positive / total) * 100
            negative_pct = (negative / total) * 100
        else:
            avg_score = 0
            positive_pct = 0
            negative_pct = 0
        
        # Determine level
        if avg_score > 0.5:
            level = SentimentLevel.EXTREME_GREED
        elif avg_score > 0.2:
            level = SentimentLevel.GREED
        elif avg_score < -0.5:
            level = SentimentLevel.EXTREME_FEAR
        elif avg_score < -0.2:
            level = SentimentLevel.FEAR
        else:
            level = SentimentLevel.NEUTRAL
        
        # Influencer mentions
        influencer_count = len([m for m in mentions_24h if m.is_influencer])
        
        # Trending detection
        is_trending = len(mentions_1h) > 10 and change_pct > 50
        
        sentiment = SymbolSentiment(
            symbol=symbol,
            mentions_1h=len(mentions_1h),
            mentions_24h=len(mentions_24h),
            mention_change_pct=change_pct,
            avg_sentiment=avg_score,
            sentiment_level=level,
            positive_pct=positive_pct,
            negative_pct=negative_pct,
            is_trending=is_trending,
            influencer_mentions=influencer_count
        )
        
        self.sentiment_cache[symbol] = sentiment
        return sentiment
    
    def get_trending_symbols(self, limit: int = 20) -> List[Tuple[str, SymbolSentiment]]:
        """Get trending symbols by mention count"""
        # Update all sentiment
        for symbol in self.mentions.keys():
            self.get_symbol_sentiment(symbol)
        
        # Sort by recent mentions
        sorted_symbols = sorted(
            self.sentiment_cache.items(),
            key=lambda x: x[1].mentions_1h,
            reverse=True
        )
        
        return sorted_symbols[:limit]
    
    def get_extreme_sentiment_symbols(self) -> Dict[str, List[SymbolSentiment]]:
        """Get symbols with extreme sentiment"""
        result = {
            'extreme_greed': [],
            'extreme_fear': []
        }
        
        for symbol in self.mentions.keys():
            sentiment = self.get_symbol_sentiment(symbol)
            
            if sentiment.sentiment_level == SentimentLevel.EXTREME_GREED:
                result['extreme_greed'].append(sentiment)
            elif sentiment.sentiment_level == SentimentLevel.EXTREME_FEAR:
                result['extreme_fear'].append(sentiment)
        
        return result
    
    async def fetch_reddit_mentions(self, subreddit: str = "cryptocurrency") -> List[SocialMention]:
        """Fetch mentions from Reddit (simplified)"""
        # Note: In production, use Reddit API with proper auth
        mentions = []
        
        try:
            url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=50"
            headers = {'User-Agent': 'PumpMonitor/1.0'}
            
            async with self._session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    posts = data.get('data', {}).get('children', [])
                    
                    for post in posts:
                        post_data = post.get('data', {})
                        title = post_data.get('title', '')
                        selftext = post_data.get('selftext', '')
                        text = f"{title} {selftext}"
                        
                        # Extract symbols ($XXX or XXX)
                        symbols = re.findall(r'\$([A-Z]{2,10})\b', text.upper())
                        symbols += re.findall(r'\b([A-Z]{2,6})USDT\b', text.upper())
                        
                        for symbol in set(symbols):
                            mention = self.record_mention(
                                platform='reddit',
                                symbol=symbol,
                                text=text[:500],
                                likes=post_data.get('ups', 0),
                                comments=post_data.get('num_comments', 0)
                            )
                            mentions.append(mention)
        except Exception as e:
            logger.error(f"Reddit fetch error: {e}")
        
        return mentions


class CVDAnalyzer:
    """
    Cumulative Volume Delta (CVD) Analyzer
    Tracks order flow imbalance - buy vs sell pressure
    """
    
    def __init__(self):
        # CVD per symbol
        self.cvd: Dict[str, float] = {}
        
        # Delta history
        self.delta_history: Dict[str, deque] = {}
        self.max_history = 500
        
        # Stats
        self.stats = {
            'trades_processed': 0,
            'total_buy_volume': 0,
            'total_sell_volume': 0
        }
    
    def record_trade(
        self,
        symbol: str,
        price: float,
        quantity: float,
        is_buyer_maker: bool  # True = sell aggressor, False = buy aggressor
    ):
        """
        Record a trade for CVD calculation
        
        is_buyer_maker=True means the aggressor was SELLING
        is_buyer_maker=False means the aggressor was BUYING
        """
        volume = price * quantity
        
        # Delta: positive = buy pressure, negative = sell pressure
        if is_buyer_maker:
            delta = -volume  # Sell aggressor
            self.stats['total_sell_volume'] += volume
        else:
            delta = volume  # Buy aggressor
            self.stats['total_buy_volume'] += volume
        
        # Update CVD
        if symbol not in self.cvd:
            self.cvd[symbol] = 0
            self.delta_history[symbol] = deque(maxlen=self.max_history)
        
        self.cvd[symbol] += delta
        self.delta_history[symbol].append({
            'timestamp': int(time.time() * 1000),
            'delta': delta,
            'cvd': self.cvd[symbol],
            'price': price
        })
        
        self.stats['trades_processed'] += 1
    
    def get_cvd(self, symbol: str) -> float:
        """Get current CVD for symbol"""
        return self.cvd.get(symbol, 0)
    
    def get_delta_1m(self, symbol: str) -> float:
        """Get delta for last 1 minute"""
        if symbol not in self.delta_history:
            return 0
        
        now = int(time.time() * 1000)
        minute_ago = now - 60000
        
        recent = [d['delta'] for d in self.delta_history[symbol] if d['timestamp'] > minute_ago]
        return sum(recent)
    
    def get_cvd_divergence(self, symbol: str) -> Optional[str]:
        """
        Detect CVD divergence
        
        Returns:
            'BULLISH' - Price down, CVD up (accumulation)
            'BEARISH' - Price up, CVD down (distribution)
            None - No divergence
        """
        if symbol not in self.delta_history:
            return None
        
        history = list(self.delta_history[symbol])
        
        if len(history) < 20:
            return None
        
        # Compare first half to second half
        first_half = history[:len(history)//2]
        second_half = history[len(history)//2:]
        
        price_start = first_half[0]['price']
        price_end = second_half[-1]['price']
        cvd_start = first_half[0]['cvd']
        cvd_end = second_half[-1]['cvd']
        
        price_change = (price_end - price_start) / price_start
        cvd_change = cvd_end - cvd_start
        
        # Divergence detection
        if price_change < -0.02 and cvd_change > 0:
            return 'BULLISH'  # Price down but buying pressure
        elif price_change > 0.02 and cvd_change < 0:
            return 'BEARISH'  # Price up but selling pressure
        
        return None
    
    def get_buy_sell_ratio(self, symbol: str, minutes: int = 5) -> float:
        """Get buy/sell volume ratio"""
        if symbol not in self.delta_history:
            return 1.0
        
        now = int(time.time() * 1000)
        cutoff = now - (minutes * 60000)
        
        recent = [d for d in self.delta_history[symbol] if d['timestamp'] > cutoff]
        
        buy_vol = sum(d['delta'] for d in recent if d['delta'] > 0)
        sell_vol = abs(sum(d['delta'] for d in recent if d['delta'] < 0))
        
        if sell_vol == 0:
            return 10.0 if buy_vol > 0 else 1.0
        
        return buy_vol / sell_vol
    
    def get_analysis(self, symbol: str) -> Dict:
        """Get full CVD analysis for symbol"""
        return {
            'symbol': symbol,
            'cvd': self.get_cvd(symbol),
            'delta_1m': self.get_delta_1m(symbol),
            'divergence': self.get_cvd_divergence(symbol),
            'buy_sell_ratio': self.get_buy_sell_ratio(symbol),
            'signal': self._get_signal(symbol)
        }
    
    def _get_signal(self, symbol: str) -> str:
        """Get trading signal based on CVD"""
        divergence = self.get_cvd_divergence(symbol)
        ratio = self.get_buy_sell_ratio(symbol)
        delta_1m = self.get_delta_1m(symbol)
        
        if divergence == 'BEARISH' and ratio < 0.7:
            return 'STRONG_SELL'
        elif divergence == 'BULLISH' and ratio > 1.5:
            return 'STRONG_BUY'
        elif delta_1m < -100000:  # Heavy selling
            return 'SELL'
        elif delta_1m > 100000:  # Heavy buying
            return 'BUY'
        
        return 'NEUTRAL'

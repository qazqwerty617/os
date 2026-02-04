"""
MEXC Pump Monitor - Market Sentiment NLP
Optimized sentiment analysis for trading decisions
"""

import asyncio
import aiohttp
import ssl
import re
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """Sentiment levels"""
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


# Level emojis
LEVEL_EMOJIS = {
    SentimentLevel.EXTREME_FEAR: '😱',
    SentimentLevel.FEAR: '😰',
    SentimentLevel.NEUTRAL: '😐',
    SentimentLevel.GREED: '🤑',
    SentimentLevel.EXTREME_GREED: '🤩'
}

# Bullish keywords (word -> weight)
BULLISH_KEYWORDS = {
    'moon': 2.0, 'mooning': 2.0, 'rocket': 1.8, '🚀': 1.8, 'pump': 1.5,
    'bullish': 1.5, 'breakout': 1.5, 'ath': 1.5, 'all time high': 1.5,
    'buy': 1.0, 'long': 1.0, 'accumulate': 1.2, 'hodl': 1.0,
    'undervalued': 1.3, 'gem': 1.2, 'buy the dip': 1.3,
    'bullrun': 1.2, 'rally': 1.1, 'support': 0.8, 'bounce': 0.8,
    'green': 0.7, 'gains': 0.9, 'profit': 0.8, 'uptrend': 1.0,
    'adoption': 1.0, 'partnership': 0.9, 'listing': 1.0,
}

# Bearish keywords (word -> weight, already negative)
BEARISH_KEYWORDS = {
    'crash': -2.0, 'dump': -1.8, 'scam': -2.0, 'rug': -2.5, 'rugpull': -2.5,
    'ponzi': -2.0, 'fraud': -2.0, 'bearish': -1.5, 'sell': -1.0,
    'short': -1.0, 'dead': -1.5, 'rip': -1.5, 'rekt': -1.5,
    'down': -0.7, 'red': -0.7, 'loss': -0.8, 'fear': -1.0,
    'resistance': -0.5, 'rejection': -0.8, 'breakdown': -1.2,
    'warning': -1.0, 'caution': -0.8, 'overvalued': -1.0,
    'bubble': -1.2, 'correction': -0.8,
}


@dataclass
class SentimentData:
    """Sentiment data"""
    symbol: str
    timestamp: int
    twitter_score: float = 0
    reddit_score: float = 0
    news_score: float = 0
    overall_score: float = 0
    twitter_mentions: int = 0
    reddit_mentions: int = 0
    news_mentions: int = 0
    sentiment_change_1h: float = 0
    sentiment_change_24h: float = 0
    mentions_change_1h: float = 0
    level: SentimentLevel = SentimentLevel.NEUTRAL
    bullish_phrases: List[str] = field(default_factory=list)
    bearish_phrases: List[str] = field(default_factory=list)


@dataclass
class SocialPost:
    """Social media post"""
    source: str  # 'twitter', 'reddit', 'news'
    text: str
    timestamp: int
    sentiment: float
    engagement: int
    author_influence: float


class MarketSentimentNLP:
    """
    Optimized Market Sentiment NLP Analyzer
    
    Analyzes:
    - Twitter/X crypto posts
    - Reddit discussions
    - News articles
    """
    
    SOURCE_WEIGHTS = {'twitter': 0.3, 'reddit': 0.3, 'news': 0.4}
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        self.sentiment_history: Dict[str, List[SentimentData]] = defaultdict(list)
        self.max_history = 1000
        self.current_sentiment: Dict[str, SentimentData] = {}
        self.seen_posts: set = set()
        self.max_seen = 10000
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        
        self.stats = {
            'posts_analyzed': 0,
            'symbols_tracked': 0,
            'alerts_sent': 0
        }
    
    async def start(self):
        self._running = True
        asyncio.create_task(self._analysis_loop())
        logger.info("🎭 Market Sentiment NLP started")
    
    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_ctx)
            )
        return self._session
    
    async def _analysis_loop(self):
        while self._running:
            try:
                await self._check_extremes()
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sentiment analysis error: {e}")
                await asyncio.sleep(60)
    
    async def _check_extremes(self):
        for symbol, data in self.current_sentiment.items():
            if data.level in (SentimentLevel.EXTREME_FEAR, SentimentLevel.EXTREME_GREED):
                if self.telegram and abs(data.overall_score) > 0.7:
                    emoji = LEVEL_EMOJIS.get(data.level, "❓")
                    await self.telegram.send_message(
                        f"{emoji} <b>SENTIMENT ALERT:</b> {symbol}\n"
                        f"Level: {data.level.value}\n"
                        f"Score: {data.overall_score:.2f}"
                    )
                    self.stats['alerts_sent'] += 1
    
    def analyze_text(self, text: str, symbol: str = None) -> float:
        """Analyze sentiment of text, returns -1 to 1"""
        if not text:
            return 0
        
        text_lower = text.lower()
        score = 0
        matches = 0
        
        for keyword, weight in BULLISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight
                matches += 1
        
        for keyword, weight in BEARISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight
                matches += 1
        
        if matches > 0:
            score = score / (matches + 2)
        
        # Emphasis modifiers
        caps_ratio = sum(1 for c in text if c.isupper()) / (len(text) + 1)
        if caps_ratio > 0.5:
            score *= 1.2
        
        if text.count('!') >= 3:
            score *= 1.1
        
        if text.count('?') >= 2:
            score *= 0.8
        
        return max(-1, min(1, score))
    
    async def analyze_post(self, post: SocialPost) -> float:
        """Analyze post with engagement weighting"""
        base = self.analyze_text(post.text)
        engagement_weight = min(2.0, 1 + (post.engagement / 1000))
        influence_weight = 0.5 + (post.author_influence * 0.5)
        
        self.stats['posts_analyzed'] += 1
        return max(-1, min(1, base * engagement_weight * influence_weight))
    
    async def update_symbol_sentiment(self, symbol: str, posts: List[SocialPost]) -> SentimentData:
        """Update sentiment for symbol from posts"""
        timestamp = int(time.time() * 1000)
        
        scores = {'twitter': [], 'reddit': [], 'news': []}
        bullish_phrases, bearish_phrases = [], []
        
        for post in posts:
            post_hash = hash(post.text[:100])
            if post_hash in self.seen_posts:
                continue
            self.seen_posts.add(post_hash)
            
            sentiment = await self.analyze_post(post)
            
            if post.source in scores:
                scores[post.source].append(sentiment)
            
            if sentiment > 0.3:
                bullish_phrases.append(post.text[:50])
            elif sentiment < -0.3:
                bearish_phrases.append(post.text[:50])
        
        # Calculate averages
        twitter_avg = sum(scores['twitter']) / len(scores['twitter']) if scores['twitter'] else 0
        reddit_avg = sum(scores['reddit']) / len(scores['reddit']) if scores['reddit'] else 0
        news_avg = sum(scores['news']) / len(scores['news']) if scores['news'] else 0
        
        overall = (
            twitter_avg * self.SOURCE_WEIGHTS['twitter'] +
            reddit_avg * self.SOURCE_WEIGHTS['reddit'] +
            news_avg * self.SOURCE_WEIGHTS['news']
        )
        
        # Determine level
        if overall >= 0.6:
            level = SentimentLevel.EXTREME_GREED
        elif overall >= 0.2:
            level = SentimentLevel.GREED
        elif overall <= -0.6:
            level = SentimentLevel.EXTREME_FEAR
        elif overall <= -0.2:
            level = SentimentLevel.FEAR
        else:
            level = SentimentLevel.NEUTRAL
        
        # Calculate 1h change
        prev = self.current_sentiment.get(symbol)
        sentiment_change = 0
        if prev and (timestamp - prev.timestamp <= 3600000):
            sentiment_change = overall - prev.overall_score
        
        data = SentimentData(
            symbol=symbol,
            timestamp=timestamp,
            twitter_score=round(twitter_avg, 3),
            reddit_score=round(reddit_avg, 3),
            news_score=round(news_avg, 3),
            overall_score=round(overall, 3),
            twitter_mentions=len(scores['twitter']),
            reddit_mentions=len(scores['reddit']),
            news_mentions=len(scores['news']),
            sentiment_change_1h=round(sentiment_change, 3),
            level=level,
            bullish_phrases=bullish_phrases[:5],
            bearish_phrases=bearish_phrases[:5]
        )
        
        self.current_sentiment[symbol] = data
        self.sentiment_history[symbol].append(data)
        if len(self.sentiment_history[symbol]) > self.max_history:
            self.sentiment_history[symbol] = self.sentiment_history[symbol][-self.max_history:]
        
        self.stats['symbols_tracked'] = len(self.current_sentiment)
        
        if len(self.seen_posts) > self.max_seen:
            self.seen_posts = set(list(self.seen_posts)[-self.max_seen // 2:])
        
        return data
    
    def get_sentiment(self, symbol: str) -> Optional[SentimentData]:
        return self.current_sentiment.get(symbol)
    
    def get_most_bullish(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        return sorted(
            self.current_sentiment.items(),
            key=lambda x: x[1].overall_score,
            reverse=True
        )[:limit]
    
    def get_most_bearish(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        return sorted(
            self.current_sentiment.items(),
            key=lambda x: x[1].overall_score
        )[:limit]
    
    def get_trending_up(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        return sorted(
            [(s, d) for s, d in self.current_sentiment.items() if d.sentiment_change_1h > 0.1],
            key=lambda x: x[1].sentiment_change_1h,
            reverse=True
        )[:limit]
    
    def analyze_for_trading(self, symbol: str, signal_type: str = 'short') -> Dict:
        """Analyze sentiment for trading decision"""
        data = self.current_sentiment.get(symbol)
        
        if not data:
            return {'recommendation': 'neutral', 'confidence': 0, 'reason': 'No data'}
        
        # Trading recommendations based on level and signal type
        recommendations = {
            ('short', SentimentLevel.EXTREME_GREED): ('strong_confirm', 0.9, 'Extreme greed - excellent short'),
            ('short', SentimentLevel.GREED): ('confirm', 0.7, 'Greed supports short'),
            ('short', SentimentLevel.EXTREME_FEAR): ('avoid', 0.8, 'Extreme fear - avoid shorting'),
            ('long', SentimentLevel.EXTREME_FEAR): ('strong_confirm', 0.9, 'Extreme fear - excellent long'),
            ('long', SentimentLevel.FEAR): ('confirm', 0.7, 'Fear supports long'),
            ('long', SentimentLevel.EXTREME_GREED): ('avoid', 0.8, 'Extreme greed - avoid longing'),
        }
        
        key = (signal_type, data.level)
        if key in recommendations:
            rec, conf, reason = recommendations[key]
            return {'recommendation': rec, 'confidence': conf, 'reason': reason}
        
        return {'recommendation': 'neutral', 'confidence': 0.5, 'reason': 'Neutral sentiment'}
    
    def format_sentiment(self, data: SentimentData) -> str:
        emoji = LEVEL_EMOJIS.get(data.level, '❓')
        return f"""
🎭 <b>SENTIMENT: {data.symbol}</b>

{emoji} Level: <b>{data.level.value.upper()}</b>
📊 Score: {data.overall_score:+.2f}

📱 Twitter: {data.twitter_score:+.2f} ({data.twitter_mentions} mentions)
🔴 Reddit: {data.reddit_score:+.2f} ({data.reddit_mentions} mentions)
📰 News: {data.news_score:+.2f} ({data.news_mentions} mentions)

📈 1h Change: {data.sentiment_change_1h:+.2f}
"""
    
    def get_stats(self) -> Dict:
        return {
            **self.stats,
            'extreme_greed_count': sum(1 for d in self.current_sentiment.values() if d.level == SentimentLevel.EXTREME_GREED),
            'extreme_fear_count': sum(1 for d in self.current_sentiment.values() if d.level == SentimentLevel.EXTREME_FEAR)
        }

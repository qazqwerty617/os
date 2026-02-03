"""
MEXC Pump Monitor - Twitter/X Sentiment Analyzer
Crypto sentiment analysis from social media
"""

import asyncio
import aiohttp
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta
from collections import deque
from enum import Enum

logger = logging.getLogger("TwitterSentiment")


class SentimentLevel(Enum):
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


@dataclass
class Tweet:
    """Parsed tweet data"""
    text: str
    author: str
    timestamp: datetime
    likes: int = 0
    retweets: int = 0
    sentiment_score: float = 0.0  # -1 to 1
    tokens_mentioned: List[str] = field(default_factory=list)


@dataclass
class TokenSentiment:
    """Sentiment analysis for a specific token"""
    symbol: str
    sentiment_score: float  # -100 to 100
    level: SentimentLevel
    tweet_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    trending_score: float  # 0-100
    influential_mentions: List[str]  # Top influencer mentions
    keywords: List[str]
    timestamp: datetime


class TwitterSentimentAnalyzer:
    """
    Twitter/X Sentiment Analysis
    - Keyword-based sentiment scoring
    - Influencer tracking
    - Trend detection
    
    Note: Uses keyword-based analysis (no API required)
    For enhanced features, add Twitter API Bearer Token
    """
    
    def __init__(self, bearer_token: Optional[str] = None):
        self.bearer_token = bearer_token or os.getenv('TWITTER_BEARER_TOKEN')
        self._session: Optional[aiohttp.ClientSession] = None
        self.cache: Dict[str, TokenSentiment] = {}
        self.tweet_history: Dict[str, deque] = {}
        self.max_history = 1000
        
        # Sentiment keywords (weighted)
        self.bullish_keywords = {
            # Strong bullish (weight 2)
            'moon': 2, 'pump': 2, 'bullish': 2, 'breakout': 2, 'ath': 2,
            'rocket': 2, '🚀': 2, 'mooning': 2, 'gains': 2, 'profit': 2,
            'buy': 1.5, 'long': 1.5, 'накачка': 2, 'рост': 1.5, 'лонг': 1.5,
            # Moderate bullish (weight 1)
            'bullrun': 1, 'green': 1, 'up': 1, 'surge': 1, 'rally': 1,
            'support': 1, 'bounce': 1, 'recovery': 1, 'accumulate': 1,
            'hodl': 1, 'hold': 1, 'diamond': 1, '💎': 1, '📈': 1.5,
        }
        
        self.bearish_keywords = {
            # Strong bearish (weight 2)
            'dump': 2, 'crash': 2, 'scam': 2, 'rug': 2, 'bearish': 2,
            'rekt': 2, 'dead': 2, 'sell': 1.5, 'short': 1.5, 'падение': 2,
            'скам': 2, 'шорт': 1.5, '💀': 2, '📉': 1.5,
            # Moderate bearish (weight 1)
            'fear': 1, 'red': 1, 'down': 1, 'drop': 1, 'decline': 1,
            'resistance': 1, 'breakdown': 1, 'weak': 1, 'loss': 1,
            'panic': 1, 'fud': 1, 'warning': 1,
        }
        
        # Known crypto influencers (for weighting)
        self.influencers = {
            'elonmusk', 'cabortrader', 'cryptokaleo', 'thescalpingpro',
            'altcoingordon', 'trader_xy', 'cryptoyoda', 'whalechart',
            'mooncarl', 'thecryptolark', 'coingecko', 'binance'
        }
        
        logger.info("🐦 Twitter Sentiment Analyzer initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    def analyze_text(self, text: str) -> Tuple[float, List[str]]:
        """
        Analyze sentiment of text
        Returns: (score from -1 to 1, list of detected keywords)
        """
        text_lower = text.lower()
        bullish_score = 0
        bearish_score = 0
        keywords = []
        
        for word, weight in self.bullish_keywords.items():
            if word in text_lower:
                bullish_score += weight
                keywords.append(f"+{word}")
        
        for word, weight in self.bearish_keywords.items():
            if word in text_lower:
                bearish_score += weight
                keywords.append(f"-{word}")
        
        total = bullish_score + bearish_score
        if total == 0:
            return 0.0, keywords
        
        # Normalize to -1 to 1
        score = (bullish_score - bearish_score) / max(total, 1)
        return round(score, 3), keywords
    
    def extract_tokens(self, text: str) -> List[str]:
        """Extract crypto token mentions from text"""
        # Match $TOKEN or #TOKEN patterns
        pattern = r'[\$\#]([A-Z]{2,10})'
        matches = re.findall(pattern, text.upper())
        
        # Also check for common token names
        common_tokens = ['BTC', 'ETH', 'SOL', 'DOGE', 'PEPE', 'WIF', 'BONK', 
                        'XRP', 'ADA', 'AVAX', 'MATIC', 'LINK', 'DOT']
        for token in common_tokens:
            if token in text.upper() and token not in matches:
                matches.append(token)
        
        return list(set(matches))
    
    def process_tweet(self, text: str, author: str = "", 
                     likes: int = 0, retweets: int = 0) -> Tweet:
        """Process a single tweet"""
        sentiment, keywords = self.analyze_text(text)
        tokens = self.extract_tokens(text)
        
        # Weight by engagement
        engagement_multiplier = 1.0
        if likes > 1000 or retweets > 500:
            engagement_multiplier = 1.5
        if likes > 10000 or retweets > 5000:
            engagement_multiplier = 2.0
        
        # Weight by influencer status
        if author.lower() in self.influencers:
            engagement_multiplier *= 1.5
        
        tweet = Tweet(
            text=text[:280],
            author=author,
            timestamp=datetime.now(),
            likes=likes,
            retweets=retweets,
            sentiment_score=sentiment * engagement_multiplier,
            tokens_mentioned=tokens
        )
        
        # Store in history for each mentioned token
        for token in tokens:
            if token not in self.tweet_history:
                self.tweet_history[token] = deque(maxlen=self.max_history)
            self.tweet_history[token].append(tweet)
        
        return tweet
    
    def get_token_sentiment(self, symbol: str, 
                           time_window_hours: int = 24) -> TokenSentiment:
        """Get aggregated sentiment for a token"""
        symbol = symbol.upper().replace('_USDT', '').replace('USDT', '')
        
        tweets = list(self.tweet_history.get(symbol, []))
        
        # Filter by time window
        cutoff = datetime.now() - timedelta(hours=time_window_hours)
        recent_tweets = [t for t in tweets if t.timestamp > cutoff]
        
        if not recent_tweets:
            return TokenSentiment(
                symbol=symbol,
                sentiment_score=0,
                level=SentimentLevel.NEUTRAL,
                tweet_count=0,
                positive_count=0,
                negative_count=0,
                neutral_count=0,
                trending_score=0,
                influential_mentions=[],
                keywords=[],
                timestamp=datetime.now()
            )
        
        # Calculate scores
        total_sentiment = sum(t.sentiment_score for t in recent_tweets)
        avg_sentiment = total_sentiment / len(recent_tweets)
        
        positive = sum(1 for t in recent_tweets if t.sentiment_score > 0.2)
        negative = sum(1 for t in recent_tweets if t.sentiment_score < -0.2)
        neutral = len(recent_tweets) - positive - negative
        
        # Determine level
        score_normalized = avg_sentiment * 100
        if score_normalized >= 50:
            level = SentimentLevel.EXTREME_GREED
        elif score_normalized >= 20:
            level = SentimentLevel.GREED
        elif score_normalized <= -50:
            level = SentimentLevel.EXTREME_FEAR
        elif score_normalized <= -20:
            level = SentimentLevel.FEAR
        else:
            level = SentimentLevel.NEUTRAL
        
        # Trending score based on volume
        base_tweets = 10  # Expected tweets per 24h for average token
        trending_score = min(100, (len(recent_tweets) / base_tweets) * 50)
        
        # Get influential mentions
        influential = [t.author for t in recent_tweets 
                      if t.author.lower() in self.influencers]
        
        # Extract all keywords
        all_keywords = []
        for t in recent_tweets[:50]:
            _, kw = self.analyze_text(t.text)
            all_keywords.extend(kw)
        
        # Count keyword frequency
        keyword_counts = {}
        for kw in all_keywords:
            keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        top_keywords = sorted(keyword_counts.keys(), 
                             key=lambda x: keyword_counts[x], 
                             reverse=True)[:10]
        
        sentiment = TokenSentiment(
            symbol=symbol,
            sentiment_score=round(score_normalized, 1),
            level=level,
            tweet_count=len(recent_tweets),
            positive_count=positive,
            negative_count=negative,
            neutral_count=neutral,
            trending_score=round(trending_score, 1),
            influential_mentions=list(set(influential))[:5],
            keywords=top_keywords,
            timestamp=datetime.now()
        )
        
        self.cache[symbol] = sentiment
        return sentiment
    
    async def fetch_from_api(self, query: str, max_results: int = 100) -> List[Tweet]:
        """Fetch tweets from Twitter API (requires Bearer Token)"""
        if not self.bearer_token:
            logger.warning("Twitter API not configured (no bearer token)")
            return []
        
        try:
            session = await self._get_session()
            
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {"Authorization": f"Bearer {self.bearer_token}"}
            params = {
                "query": f"{query} -is:retweet lang:en",
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,public_metrics,author_id"
            }
            
            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    tweets = []
                    for tweet_data in data.get('data', []):
                        metrics = tweet_data.get('public_metrics', {})
                        tweet = self.process_tweet(
                            text=tweet_data.get('text', ''),
                            author=str(tweet_data.get('author_id', '')),
                            likes=metrics.get('like_count', 0),
                            retweets=metrics.get('retweet_count', 0)
                        )
                        tweets.append(tweet)
                    return tweets
                else:
                    logger.error(f"Twitter API error: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Twitter fetch error: {e}")
            return []
    
    def format_telegram_alert(self, sentiment: TokenSentiment) -> str:
        """Format sentiment as Telegram message"""
        level_emoji = {
            SentimentLevel.EXTREME_GREED: "🤑🤑",
            SentimentLevel.GREED: "😊",
            SentimentLevel.NEUTRAL: "😐",
            SentimentLevel.FEAR: "😰",
            SentimentLevel.EXTREME_FEAR: "😱😱"
        }
        
        emoji = level_emoji.get(sentiment.level, "❓")
        direction = "📈" if sentiment.sentiment_score > 0 else "📉" if sentiment.sentiment_score < 0 else "➖"
        
        return f"""
🐦 <b>TWITTER SENTIMENT</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪙 <b>Token:</b> #{sentiment.symbol}
{direction} <b>Score:</b> {sentiment.sentiment_score:+.1f}/100
📊 <b>Level:</b> {sentiment.level.value.replace('_', ' ').title()}

<b>📈 Stats (24h):</b>
• Tweets: {sentiment.tweet_count}
• Positive: {sentiment.positive_count} | Negative: {sentiment.negative_count}
• Trending: {sentiment.trending_score:.0f}/100

<b>🔑 Keywords:</b> {', '.join(sentiment.keywords[:5]) if sentiment.keywords else 'None'}
"""

    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()


# Convenience instance
twitter_sentiment = TwitterSentimentAnalyzer()

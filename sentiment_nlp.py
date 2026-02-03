"""
MEXC Pump Monitor - Market Sentiment NLP
Анализ настроений Twitter, Reddit и новостей с помощью NLP
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
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class SentimentLevel(Enum):
    """Уровни sentiment"""
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


@dataclass
class SentimentData:
    """Данные о sentiment"""
    symbol: str
    timestamp: int
    
    # Scores (-1 to 1)
    twitter_score: float = 0
    reddit_score: float = 0
    news_score: float = 0
    overall_score: float = 0
    
    # Volumes
    twitter_mentions: int = 0
    reddit_mentions: int = 0
    news_mentions: int = 0
    
    # Trends
    sentiment_change_1h: float = 0
    sentiment_change_24h: float = 0
    mentions_change_1h: float = 0
    
    # Classification
    level: SentimentLevel = SentimentLevel.NEUTRAL
    
    # Key phrases
    bullish_phrases: List[str] = field(default_factory=list)
    bearish_phrases: List[str] = field(default_factory=list)


@dataclass
class SocialPost:
    """Пост из соц сети"""
    source: str  # 'twitter', 'reddit', 'news'
    text: str
    timestamp: int
    sentiment: float  # -1 to 1
    engagement: int  # likes, upvotes, etc.
    author_influence: float  # 0 to 1


class MarketSentimentNLP:
    """
    🎭 Market Sentiment NLP Analyzer
    
    Анализирует:
    - Twitter/X посты о криптовалютах
    - Reddit обсуждения (r/cryptocurrency, r/bitcoin, etc.)
    - Новостные статьи
    - Telegram каналы
    
    Использует:
    - Keyword-based sentiment
    - Phrase patterns
    - Engagement-weighted scoring
    """
    
    # Bullish keywords and phrases
    BULLISH_KEYWORDS = {
        # Strong bullish
        'moon': 2.0, 'mooning': 2.0, 'rocket': 1.8, '🚀': 1.8, 'pump': 1.5,
        'bullish': 1.5, 'breakout': 1.5, 'ath': 1.5, 'all time high': 1.5,
        'buy': 1.0, 'long': 1.0, 'accumulate': 1.2, 'hodl': 1.0,
        'undervalued': 1.3, 'gem': 1.2, 'buy the dip': 1.3,
        
        # Moderate bullish
        'bullrun': 1.2, 'rally': 1.1, 'support': 0.8, 'bounce': 0.8,
        'green': 0.7, 'gains': 0.9, 'profit': 0.8, 'uptrend': 1.0,
        'adoption': 1.0, 'partnership': 0.9, 'listing': 1.0,
    }
    
    # Bearish keywords and phrases
    BEARISH_KEYWORDS = {
        # Strong bearish
        'crash': -2.0, 'dump': -1.8, 'scam': -2.0, 'rug': -2.5, 'rugpull': -2.5,
        'ponzi': -2.0, 'fraud': -2.0, 'bearish': -1.5, 'sell': -1.0,
        'short': -1.0, 'dead': -1.5, 'rip': -1.5, 'rekt': -1.5,
        
        # Moderate bearish
        'down': -0.7, 'red': -0.7, 'loss': -0.8, 'fear': -1.0,
        'resistance': -0.5, 'rejection': -0.8, 'breakdown': -1.2,
        'warning': -1.0, 'caution': -0.8, 'overvalued': -1.0,
        'bubble': -1.2, 'correction': -0.8,
    }
    
    # Neutral/noise words to filter
    NOISE_WORDS = {'the', 'is', 'at', 'to', 'a', 'in', 'for', 'on', 'of', 'and', 'or'}
    
    # Crypto-specific patterns
    PRICE_PATTERNS = [
        r'\$[\d,]+\.?\d*[kmb]?',  # $50k, $1,234
        r'[\d,]+\.?\d*\s*(usd|usdt|dollars?)',
    ]
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Sentiment history per symbol
        self.sentiment_history: Dict[str, List[SentimentData]] = defaultdict(list)
        self.max_history = 1000
        
        # Current sentiment cache
        self.current_sentiment: Dict[str, SentimentData] = {}
        
        # Post cache for deduplication
        self.seen_posts: set = set()
        self.max_seen = 10000
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.stats = {
            'posts_analyzed': 0,
            'symbols_tracked': 0,
            'alerts_sent': 0
        }
        
        self._running = False
    
    async def start(self):
        """Запустить анализатор"""
        self._running = True
        asyncio.create_task(self._analysis_loop())
        logger.info("🎭 Market Sentiment NLP started")
    
    async def stop(self):
        """Остановить анализатор"""
        self._running = False
        if self._session:
            await self._session.close()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get HTTP session"""
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_ctx)
            )
        return self._session
    
    async def _analysis_loop(self):
        """Основной цикл анализа"""
        while self._running:
            try:
                # Analyze trending topics
                await self._analyze_trending()
                
                # Check for sentiment extremes
                await self._check_extremes()
                
                await asyncio.sleep(300)  # Every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sentiment analysis error: {e}")
                await asyncio.sleep(60)
    
    async def _analyze_trending(self):
        """Анализировать трендовые темы"""
        # This would integrate with:
        # - Twitter API
        # - Reddit API
        # - LunarCrush API
        # - Santiment API
        pass
    
    async def _check_extremes(self):
        """Проверить экстремальные значения sentiment"""
        for symbol, data in self.current_sentiment.items():
            if data.level in [SentimentLevel.EXTREME_FEAR, SentimentLevel.EXTREME_GREED]:
                # Alert on extreme sentiment
                if self.telegram and abs(data.overall_score) > 0.7:
                    emoji = "😱" if data.level == SentimentLevel.EXTREME_FEAR else "🤑"
                    await self.telegram.send_message(
                        f"{emoji} <b>SENTIMENT ALERT:</b> {symbol}\n"
                        f"Level: {data.level.value}\n"
                        f"Score: {data.overall_score:.2f}"
                    )
                    self.stats['alerts_sent'] += 1
    
    def analyze_text(self, text: str, symbol: str = None) -> float:
        """
        Анализировать sentiment текста
        
        Args:
            text: Текст для анализа
            symbol: Символ криптовалюты (опционально)
        
        Returns:
            Sentiment score от -1 (bearish) до 1 (bullish)
        """
        if not text:
            return 0
        
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        
        if not words:
            return 0
        
        score = 0
        matches = 0
        
        # Check bullish keywords
        for keyword, weight in self.BULLISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight
                matches += 1
        
        # Check bearish keywords
        for keyword, weight in self.BEARISH_KEYWORDS.items():
            if keyword in text_lower:
                score += weight  # Already negative
                matches += 1
        
        # Normalize
        if matches > 0:
            score = score / (matches + 2)  # Dampening factor
        
        # Check for specific patterns
        # CAPS emphasis
        caps_ratio = sum(1 for c in text if c.isupper()) / (len(text) + 1)
        if caps_ratio > 0.5:
            score *= 1.2  # Amplify sentiment for ALL CAPS
        
        # Exclamation emphasis
        exclamation_count = text.count('!')
        if exclamation_count >= 3:
            score *= 1.1
        
        # Question marks reduce confidence
        question_count = text.count('?')
        if question_count >= 2:
            score *= 0.8
        
        # Clamp to [-1, 1]
        return max(-1, min(1, score))
    
    async def analyze_post(self, post: SocialPost) -> float:
        """
        Анализировать пост с учётом engagement
        """
        base_sentiment = self.analyze_text(post.text)
        
        # Weight by engagement
        engagement_weight = min(2.0, 1 + (post.engagement / 1000))
        
        # Weight by author influence
        influence_weight = 0.5 + (post.author_influence * 0.5)
        
        weighted_sentiment = base_sentiment * engagement_weight * influence_weight
        
        self.stats['posts_analyzed'] += 1
        
        return max(-1, min(1, weighted_sentiment))
    
    async def update_symbol_sentiment(
        self,
        symbol: str,
        posts: List[SocialPost]
    ) -> SentimentData:
        """
        Обновить sentiment для символа
        """
        timestamp = int(time.time() * 1000)
        
        twitter_scores = []
        reddit_scores = []
        news_scores = []
        
        bullish_phrases = []
        bearish_phrases = []
        
        for post in posts:
            # Deduplicate
            post_hash = hash(post.text[:100])
            if post_hash in self.seen_posts:
                continue
            self.seen_posts.add(post_hash)
            
            sentiment = await self.analyze_post(post)
            
            if post.source == 'twitter':
                twitter_scores.append(sentiment)
            elif post.source == 'reddit':
                reddit_scores.append(sentiment)
            elif post.source == 'news':
                news_scores.append(sentiment)
            
            # Extract key phrases
            if sentiment > 0.3:
                bullish_phrases.append(post.text[:50])
            elif sentiment < -0.3:
                bearish_phrases.append(post.text[:50])
        
        # Calculate averages
        twitter_score = sum(twitter_scores) / len(twitter_scores) if twitter_scores else 0
        reddit_score = sum(reddit_scores) / len(reddit_scores) if reddit_scores else 0
        news_score = sum(news_scores) / len(news_scores) if news_scores else 0
        
        # Weighted overall score (news has more weight)
        overall_score = (
            twitter_score * 0.3 +
            reddit_score * 0.3 +
            news_score * 0.4
        )
        
        # Determine level
        if overall_score >= 0.6:
            level = SentimentLevel.EXTREME_GREED
        elif overall_score >= 0.2:
            level = SentimentLevel.GREED
        elif overall_score <= -0.6:
            level = SentimentLevel.EXTREME_FEAR
        elif overall_score <= -0.2:
            level = SentimentLevel.FEAR
        else:
            level = SentimentLevel.NEUTRAL
        
        # Calculate changes
        prev_sentiment = self.current_sentiment.get(symbol)
        sentiment_change_1h = 0
        if prev_sentiment:
            if timestamp - prev_sentiment.timestamp <= 3600000:
                sentiment_change_1h = overall_score - prev_sentiment.overall_score
        
        data = SentimentData(
            symbol=symbol,
            timestamp=timestamp,
            twitter_score=round(twitter_score, 3),
            reddit_score=round(reddit_score, 3),
            news_score=round(news_score, 3),
            overall_score=round(overall_score, 3),
            twitter_mentions=len(twitter_scores),
            reddit_mentions=len(reddit_scores),
            news_mentions=len(news_scores),
            sentiment_change_1h=round(sentiment_change_1h, 3),
            level=level,
            bullish_phrases=bullish_phrases[:5],
            bearish_phrases=bearish_phrases[:5]
        )
        
        # Store
        self.current_sentiment[symbol] = data
        self.sentiment_history[symbol].append(data)
        if len(self.sentiment_history[symbol]) > self.max_history:
            self.sentiment_history[symbol] = self.sentiment_history[symbol][-self.max_history:]
        
        self.stats['symbols_tracked'] = len(self.current_sentiment)
        
        # Cleanup seen posts
        if len(self.seen_posts) > self.max_seen:
            self.seen_posts = set(list(self.seen_posts)[-self.max_seen // 2:])
        
        return data
    
    def get_sentiment(self, symbol: str) -> Optional[SentimentData]:
        """Получить текущий sentiment для символа"""
        return self.current_sentiment.get(symbol)
    
    def get_most_bullish(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        """Получить самые bullish символы"""
        sorted_sentiment = sorted(
            self.current_sentiment.items(),
            key=lambda x: x[1].overall_score,
            reverse=True
        )
        return sorted_sentiment[:limit]
    
    def get_most_bearish(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        """Получить самые bearish символы"""
        sorted_sentiment = sorted(
            self.current_sentiment.items(),
            key=lambda x: x[1].overall_score
        )
        return sorted_sentiment[:limit]
    
    def get_trending_up(self, limit: int = 10) -> List[Tuple[str, SentimentData]]:
        """Получить символы с растущим sentiment"""
        trending = [
            (s, d) for s, d in self.current_sentiment.items()
            if d.sentiment_change_1h > 0.1
        ]
        return sorted(trending, key=lambda x: x[1].sentiment_change_1h, reverse=True)[:limit]
    
    def analyze_for_trading(self, symbol: str, signal_type: str = 'short') -> Dict:
        """
        Проанализировать sentiment для торгового решения
        
        Args:
            symbol: Символ
            signal_type: 'short' или 'long'
        
        Returns:
            Dict с рекомендацией
        """
        sentiment = self.current_sentiment.get(symbol)
        
        if not sentiment:
            return {
                'recommendation': 'neutral',
                'confidence': 0,
                'reason': 'No sentiment data available'
            }
        
        if signal_type == 'short':
            # For shorts: extreme greed is good (contrarian)
            if sentiment.level == SentimentLevel.EXTREME_GREED:
                return {
                    'recommendation': 'strong_confirm',
                    'confidence': 0.9,
                    'reason': 'Extreme greed - excellent short opportunity'
                }
            elif sentiment.level == SentimentLevel.GREED:
                return {
                    'recommendation': 'confirm',
                    'confidence': 0.7,
                    'reason': 'Greed sentiment supports short'
                }
            elif sentiment.level == SentimentLevel.EXTREME_FEAR:
                return {
                    'recommendation': 'avoid',
                    'confidence': 0.8,
                    'reason': 'Extreme fear - avoid shorting'
                }
            else:
                return {
                    'recommendation': 'neutral',
                    'confidence': 0.5,
                    'reason': 'Neutral sentiment'
                }
        else:  # long
            if sentiment.level == SentimentLevel.EXTREME_FEAR:
                return {
                    'recommendation': 'strong_confirm',
                    'confidence': 0.9,
                    'reason': 'Extreme fear - excellent long opportunity'
                }
            elif sentiment.level == SentimentLevel.FEAR:
                return {
                    'recommendation': 'confirm',
                    'confidence': 0.7,
                    'reason': 'Fear sentiment supports long'
                }
            elif sentiment.level == SentimentLevel.EXTREME_GREED:
                return {
                    'recommendation': 'avoid',
                    'confidence': 0.8,
                    'reason': 'Extreme greed - avoid longing'
                }
            else:
                return {
                    'recommendation': 'neutral',
                    'confidence': 0.5,
                    'reason': 'Neutral sentiment'
                }
    
    def format_sentiment(self, data: SentimentData) -> str:
        """Форматировать sentiment для отображения"""
        level_emoji = {
            SentimentLevel.EXTREME_FEAR: '😱',
            SentimentLevel.FEAR: '😰',
            SentimentLevel.NEUTRAL: '😐',
            SentimentLevel.GREED: '🤑',
            SentimentLevel.EXTREME_GREED: '🤩'
        }
        
        emoji = level_emoji.get(data.level, '❓')
        
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
        """Получить статистику"""
        return {
            **self.stats,
            'extreme_greed_count': sum(
                1 for d in self.current_sentiment.values()
                if d.level == SentimentLevel.EXTREME_GREED
            ),
            'extreme_fear_count': sum(
                1 for d in self.current_sentiment.values()
                if d.level == SentimentLevel.EXTREME_FEAR
            )
        }

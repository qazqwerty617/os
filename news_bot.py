"""
MEXC Pump Monitor - News Bot
Парсинг крипто-новостей из различных источников
"""

import asyncio
import logging
import os
import re
import time
import aiohttp
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from datetime import datetime, timedelta
from enum import Enum
import json
from collections import defaultdict
from config import config
from local_model import local_brain # Zero-config AI logic

logger = logging.getLogger(__name__)


class NewsSource(Enum):
    """Источники новостей"""
    COINDESK = "coindesk"
    COINTELEGRAPH = "cointelegraph"
    CRYPTONEWS = "cryptonews"
    TWITTER = "twitter"
    REDDIT = "reddit"
    TELEGRAM = "telegram"
    THEBLOCK = "theblock"
    DECRYPT = "decrypt"
    WHALE_ALERT = "whale_alert"
    COINDAR = "coindar"
    WATCHER_GURU = "watcher_guru"
    TRADINGVIEW = "tradingview"


class NewsSentiment(Enum):
    """Сентимент новости"""
    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"


@dataclass
class NewsItem:
    """Новостная статья"""
    news_id: str
    source: NewsSource
    title: str
    summary: str
    url: str
    timestamp: int
    
    # Analysis
    sentiment: NewsSentiment = NewsSentiment.NEUTRAL
    sentiment_score: float = 0  # -1 to 1
    
    # Related tokens
    mentioned_tokens: List[str] = field(default_factory=list)
    
    # Impact
    importance: int = 50  # 0-100
    
    # Categories
    categories: List[str] = field(default_factory=list)


class NewsBot:
    """
    📰 News Bot
    
    Функции:
    - Парсинг новостей с криптосайтов
    - Анализ сентимента
    - Определение упомянутых токенов
    - Алерты на важные новости
    - Telegram уведомления
    """
    
    # Bullish keywords
    BULLISH_KEYWORDS = [
        'surge', 'soar', 'rally', 'pump', 'moon', 'bullish', 'breakout',
        'partnership', 'adoption', 'launch', 'listing', 'upgrade',
        'record high', 'ath', 'all-time high', 'институциональные',
        'рост', 'памп', 'партнёрство', 'листинг', 'бычий'
    ]
    
    # Bearish keywords
    BEARISH_KEYWORDS = [
        'crash', 'dump', 'plunge', 'drop', 'bearish', 'hack', 'exploit',
        'ban', 'regulation', 'sec', 'lawsuit', 'fraud', 'scam',
        'bankrupt', 'insolvent', 'delisting', 'падение', 'дамп',
        'хак', 'взлом', 'запрет', 'регулирование', 'медвежий'
    ]
    
    # Ignore these "noise" keywords
    IGNORE_KEYWORDS = [
        'price analysis', 'price prediction', 'market outlook', 'top crypto',
        'can hit', 'could reach', 'predicts', 'opinion', 'daily digest',
        'borrowing shifts', 'etfs bounce', 'volumes plunge', 'price analysis',
        'анализ цены', 'прогноз', 'мнение', 'топ криптовалют',
        'nvidia', 'nvda', 'amazon', 'amzn', 'stocks', 'equity', 'nasdaq', 'nyse',
        'trumprx', 'earnings report', 'q4 earnings', 'fed pivot', 'interest rates'
    ]
    
    # Common crypto tokens to track
    TRACKED_TOKENS = [
        'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'SHIB', 'AVAX',
        'DOT', 'LINK', 'MATIC', 'UNI', 'ATOM', 'LTC', 'BCH', 'NEAR',
        'APT', 'ARB', 'OP', 'SUI', 'SEI', 'TIA', 'JUP', 'PEPE', 'WIF',
        'BONK', 'FLOKI', 'MEME', 'AI', 'FET', 'RNDR', 'INJ', 'TRX'
    ]
    
    RSS_FEEDS = {
        NewsSource.COINDESK: "https://www.coindesk.com/arc/outboundfeeds/rss/",
        NewsSource.COINTELEGRAPH: "https://cointelegraph.com/rss",
        NewsSource.CRYPTONEWS: "https://cryptopanic.com/news/rss/", # CryptoPanic aggregator
        NewsSource.THEBLOCK: "https://www.theblock.co/rss.xml",
        NewsSource.DECRYPT: "https://decrypt.co/feed",
        NewsSource.WATCHER_GURU: "https://watcher.guru/news/feed", # Direct fast news
        NewsSource.TRADINGVIEW: "https://www.tradingview.com/news/feed/", # TradingView news
    }
    
    SEEN_IDS_FILE = "data/seen_news_ids.json"
    
    def __init__(self, telegram=None, openrouter=None):
        self.telegram = telegram
        self.openrouter = openrouter
        self._session: Optional[aiohttp.ClientSession] = None
        
        # News storage (Optimized for VPS with limited RAM)
        self.news: List[NewsItem] = []
        self.max_news = 200  # Reduced from 500 to save RAM
        
        # Connection pool limit
        self._request_semaphore = asyncio.Semaphore(5)  # Max 5 concurrent requests
        
        # Seen news (to avoid duplicates) - load from disk
        self._seen_ids: set = self._load_seen_ids()
        self._max_seen_ids = 1500  # Hard limit for memory
        
        # Callbacks
        self._callbacks: List[Callable] = []
        self._ai_lock = asyncio.Semaphore(1) # Strict queue for AI requests
        self._key_index = 0  # Round-robin index for multiple keys
        
        # Stats
        self.stats = {
            'news_fetched': 0,
            'alerts_sent': 0,
            'sources_active': 0
        }
        
        self._running = False
    
    def _load_seen_ids(self) -> set:
        """Load seen news IDs from disk to prevent duplicates after restart"""
        import os
        if os.path.exists(self.SEEN_IDS_FILE):
            try:
                with open(self.SEEN_IDS_FILE, 'r') as f:
                    data = json.load(f)
                    # Keep only last 1000 IDs to prevent file bloat
                    return set(data[-1000:] if len(data) > 1000 else data)
            except Exception as e:
                logger.debug(f"Could not load seen IDs: {e}")
        return set()
    
    def _save_seen_ids(self):
        """Save seen news IDs to disk"""
        import os
        
        # Trim in-memory set to prevent memory leak
        if len(self._seen_ids) > 2000:
            self._seen_ids = set(list(self._seen_ids)[-1000:])
        
        os.makedirs(os.path.dirname(self.SEEN_IDS_FILE), exist_ok=True)
        try:
            with open(self.SEEN_IDS_FILE, 'w') as f:
                json.dump(list(self._seen_ids)[-1000:], f)  # Keep last 1000
        except Exception as e:
            logger.debug(f"Could not save seen IDs: {e}")
    
    def _trim_seen_ids(self):
        """Trim seen IDs in memory to prevent RAM exhaustion"""
        if len(self._seen_ids) > self._max_seen_ids:
            # Convert to list, keep last 1000, convert back to set
            self._seen_ids = set(list(self._seen_ids)[-1000:])
            logger.debug(f"Trimmed _seen_ids to {len(self._seen_ids)} items")

    async def _fetch_url_retry(self, url: str, timeout: int = 30, retries: int = 2) -> Optional[str]:
        """Fetch URL with retry and exponential backoff"""
        for attempt in range(retries + 1):
            try:
                session = await self._get_session()
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.text()
            except Exception as e:
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    logger.debug(f"Fetch failed {url[:50]}...: {e}")
        return None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get aiohttp session with connection limits"""
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            # Limit connections to prevent memory/connection exhaustion
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=10,  # Max 10 total connections
                limit_per_host=3  # Max 3 per host
            )
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def start(self):
        """Запустить бота"""
        self._running = True
        asyncio.create_task(self._fetch_loop())
        logger.info("📰 News Bot started")
    
    async def stop(self):
        """Остановить"""
        self._running = False
        if self._session:
            await self._session.close()
    
    def on_news(self, callback: Callable):
        """Подписаться на новости"""
        self._callbacks.append(callback)
    
    async def _notify_callbacks(self, news: 'NewsItem'):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(news)
                else:
                    cb(news)
            except Exception as e:
                logger.debug(f"News callback: {e}")
    
    async def _fetch_loop(self):
        """Цикл получения новостей"""
        import gc
        heartbeat_counter = 0
        gc_counter = 0
        while self._running:
            try:
                await self._fetch_all_sources()
                self._save_seen_ids()  # Persist seen IDs to disk
                self._trim_seen_ids()  # Trim in-memory set
                heartbeat_counter += 1
                gc_counter += 1
                
                # GC every 10 iterations (10 minutes)
                if gc_counter >= 10:
                    gc.collect()
                    gc_counter = 0
                    logger.debug("🧹 Garbage collected")
                
                # Heartbeat каждые 30 минут (30 итераций по 60 сек)
                if heartbeat_counter >= 30:
                    logger.info(f"📰 NEWS BOT ALIVE | Fetched: {self.stats['news_fetched']} | Alerts: {self.stats['alerts_sent']} | News: {len(self.news)} | Seen: {len(self._seen_ids)}")
                    heartbeat_counter = 0
                await asyncio.sleep(60)  # Every 1 minute (Freshest news)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"News fetch error: {e}")
                await asyncio.sleep(60)
    
    async def _fetch_all_sources(self):
        """Получить новости со всех источников"""
        tasks = [
            self._fetch_coindesk(),
            self._fetch_cointelegraph(),
            self._fetch_cryptopanic_rss(),
            self._fetch_rss_source(NewsSource.THEBLOCK),
            self._fetch_rss_source(NewsSource.DECRYPT),
            self._fetch_rss_source(NewsSource.WATCHER_GURU),
            self._fetch_tradingview(),
            self._fetch_whale_alert(),
            self._fetch_coindar()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _fetch_coindesk(self):
        """Получить новости с CoinDesk"""
        async with self._request_semaphore:
            text = await self._fetch_url_retry("https://www.coindesk.com/arc/outboundfeeds/rss/")
            if text:
                await self._parse_rss(text, NewsSource.COINDESK)
    
    async def _fetch_cointelegraph(self):
        """Получить новости с CoinTelegraph"""
        async with self._request_semaphore:
            text = await self._fetch_url_retry("https://cointelegraph.com/rss")
            if text:
                await self._parse_rss(text, NewsSource.COINTELEGRAPH)
    
    async def _fetch_cryptopanic_rss(self):
        """Получить новости с CryptoPanic (Агрегатор Twitter/Reddit/News)"""
        try:
            async with self._request_semaphore:
                session = await self._get_session()
                url = self.RSS_FEEDS[NewsSource.CRYPTONEWS]
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        await self._parse_rss(text, NewsSource.CRYPTONEWS)
        except Exception as e:
            logger.debug(f"CryptoPanic fetch failed: {e}")

    async def _fetch_tradingview(self):
        """Получить новости с TradingView (технический анализ и рыночные инсайты)"""
        try:
            async with self._request_semaphore:
                session = await self._get_session()
                url = self.RSS_FEEDS[NewsSource.TRADINGVIEW]

                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        await self._parse_rss(text, NewsSource.TRADINGVIEW)

        except Exception as e:
            logger.debug(f"TradingView fetch failed: {e}")

    async def _fetch_rss_source(self, source: NewsSource):
        """Универсальный загрузчик для RSS"""
        try:
            async with self._request_semaphore:
                session = await self._get_session()
                url = self.RSS_FEEDS.get(source)
                if not url: return
                
                async with session.get(url, timeout=30) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        await self._parse_rss(text, source)
        except Exception as e:
            logger.debug(f"RSS source {source.value} fetch failed: {e}")

    async def _fetch_whale_alert(self):
        """Получить данные о крупных транзакциях (Whale Alert)"""
        try:
            api_key = os.getenv('WHALE_ALERT_API_KEY')
            if not api_key or api_key == 'your_whale_alert_api_key_here':
                return
                
            # Последние 10 минут, минимальная сумма $1M
            start_time = int(time.time()) - 600
            url = f"https://api.whale-alert.io/v1/transactions?api_key={api_key}&min_value=1000000&start={start_time}"
            
            async with self._request_semaphore:
                session = await self._get_session()
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for tx in data.get('transactions', []):
                            tx_id = f"whale_{tx.get('hash')}"
                            if tx_id in self._seen_ids: continue
                            self._seen_ids.add(tx_id)
                            
                            symbol = tx.get('symbol', '').upper()
                            amount = round(tx.get('amount', 0), 2)
                            usd_value = round(tx.get('amount_usd', 0), 0)
                            from_addr = tx.get('from', {}).get('owner_type', 'unknown')
                            to_addr = tx.get('to', {}).get('owner_type', 'unknown')
                            
                            # Формируем заголовок для AI
                            title = f"WHALE: {amount} {symbol} (${usd_value:,.0f}) from {from_addr} to {to_addr}"
                            
                            # AI должен понять: inflow к бирже = падение, outflow от биржи = рост
                            ai_analysis = await self._analyze_with_groq(title, "Whale tracking alert", [symbol])
                            
                            news = NewsItem(
                                news_id=tx_id,
                                source=NewsSource.WHALE_ALERT,
                                title=title,
                                summary=f"Hash: {tx.get('hash')}",
                                url=f"https://whale-alert.io/transaction/ethereum/{tx.get('hash')}", # simplified
                                timestamp=int(time.time() * 1000),
                                sentiment=NewsSentiment(ai_analysis['sentiment']) if ai_analysis else NewsSentiment.NEUTRAL,
                                sentiment_score=ai_analysis['score'] if ai_analysis else 0,
                                mentioned_tokens=[symbol],
                                importance=ai_analysis['importance'] if ai_analysis else 70
                            )
                            self.news.append(news)
                            if news.importance >= 80:
                                 await self._send_alert(news)
        except Exception as e:
            logger.debug(f"Whale Alert fetch failed: {e}")

    async def _fetch_coindar(self):
        """Получить события календаря (Coindar)"""
        try:
            api_key = os.getenv('COINDAR_API_KEY')
            if not api_key or api_key == 'your_coindar_api_key_here':
                return
                
            url = f"https://coindar.org/api/v2/events?access_token={api_key}&page=1&page_size=10&order_by=date_start&order_direction=asc"
            
            async with self._request_semaphore:
                session = await self._get_session()
                async with session.get(url, timeout=15) as resp:
                    if resp.status == 200:
                        events = await resp.json()
                        for ev in events:
                            ev_id = f"coindar_{ev.get('id')}"
                            if ev_id in self._seen_ids: continue
                            self._seen_ids.add(ev_id)
                            
                            title = f"EVENT: {ev.get('caption')} ({ev.get('coin_symbol')})"
                            tokens = [ev.get('coin_symbol', '').upper()]
                            
                            ai_analysis = await self._analyze_with_groq(title, ev.get('source', ''), tokens)
                            
                            news = NewsItem(
                                news_id=ev_id,
                                source=NewsSource.COINDAR,
                                title=title,
                                summary=ev.get('caption', ''),
                                url=ev.get('source', 'https://coindar.org'),
                                timestamp=int(time.time() * 1000),
                                sentiment=NewsSentiment(ai_analysis['sentiment']) if ai_analysis else NewsSentiment.NEUTRAL,
                                sentiment_score=ai_analysis['score'] if ai_analysis else 0,
                                mentioned_tokens=tokens,
                                importance=ai_analysis['importance'] if ai_analysis else 60
                            )
                            self.news.append(news)
                            if news.importance >= 80:
                                 await self._send_alert(news)
        except Exception as e:
            logger.debug(f"Coindar fetch failed: {e}")

    async def _fetch_crypto_news_api(self):
        """Получить новости через API (CryptoPanic: Twitter/Reddit/Telegram)"""
        try:
            # Используем актуальный API v2 для получения самых горячих новостей
            api_key = os.getenv('CRYPTOPANIC_API_KEY')
            # Filters: hot, rising, important, bull, bear
            url = f"https://cryptopanic.com/api/developer/v2/posts/?auth_token={api_key}&filter=hot"
            
            session = await self._get_session()
            async with session.get(url, timeout=20) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get('results', [])[:15]:
                        title = self._clean_html(item.get('title', ''))
                        url = item.get('url', '')
                        kind = item.get('kind', 'news') # news, media, twitter, reddit
                        
                        source_map = {
                            'twitter': NewsSource.TWITTER,
                            'reddit': NewsSource.REDDIT,
                            'news': NewsSource.CRYPTONEWS,
                            'media': NewsSource.CRYPTONEWS
                        }
                        source = source_map.get(kind, NewsSource.CRYPTONEWS)
                        
                        news_id = f"cp_{item.get('id', hash(title))}"
                        if news_id in self._seen_ids:
                            continue
                        
                        self._seen_ids.add(news_id)
                        
                        # Extract basic info
                        tokens = [c.get('code') for c in item.get('currencies', [])]
                        if not tokens:
                            tokens = self._extract_tokens(title)
                        
                        if self._is_noise(title):
                            continue
                            
                        # AI Analysis
                        sentiment = NewsSentiment.NEUTRAL
                        score = 0
                        importance = 50
                        ru_title = title
                        
                        if config.groq.api_keys:
                            ai_analysis = await self._analyze_with_groq(title, "", tokens)
                            if ai_analysis:
                                sentiment = NewsSentiment(ai_analysis['sentiment'])
                                score = ai_analysis['score']
                                importance = ai_analysis['importance']
                                ru_title = ai_analysis.get('ru_title', title)

                        news = NewsItem(
                            news_id=news_id,
                            source=source,
                            title=title,
                            summary="",
                            url=url,
                            timestamp=int(time.time() * 1000),
                            sentiment=sentiment,
                            sentiment_score=score,
                            mentioned_tokens=tokens,
                            importance=importance
                        )
                        
                        # Signal logic
                        direction, dir_conf = local_brain.predict_direction(title)
                        if direction != "NEUTRAL" and dir_conf > 60:
                            news.signal_text = f"🎯 <b>SIGNAL: {'🟢' if direction == 'LONG' else '🔴'} {direction} {tokens[0] if tokens else 'MARKET'}</b>"
                        
                        self._cached_translation = ru_title
                        self.news.append(news)
                        
                        if importance >= 80:
                            await self._send_alert(news)
                        await self._notify_callbacks(news)
                            
        except Exception as e:
            logger.debug(f"CryptoPanic API fetch failed: {e}")

    async def _parse_rss(self, xml_text: str, source: NewsSource):
        """Парсинг RSS"""
        try:
            # Simple XML parsing without external libs
            items = re.findall(r'<item>(.*?)</item>', xml_text, re.DOTALL)
            
            for item_xml in items[:10]:  # Last 10 items
                title_match = re.search(r'<title>(.*?)</title>', item_xml)
                link_match = re.search(r'<link>(.*?)</link>', item_xml)
                desc_match = re.search(r'<description>(.*?)</description>', item_xml)
                
                if not title_match:
                    continue
                
                title = self._clean_html(title_match.group(1))
                link = link_match.group(1) if link_match else ""
                description = self._clean_html(desc_match.group(1)) if desc_match else ""
                
                news_id = f"{source.value}_{hash(title)}"
                
                if news_id in self._seen_ids:
                    continue
                
                self._seen_ids.add(news_id)
                
                # Analyze
                sentiment, score = self._analyze_sentiment(title + " " + description)
                tokens = self._extract_tokens(title + " " + description)
                if self._is_noise(title):
                    continue
                
                # Pre-calculate importance with heuristics
                heuristic_importance = self._calculate_importance(title, tokens, sentiment)
                
                # Only use Groq for potentially important news (saves API quota)
                # Use Groq if: has crypto tokens OR heuristic importance >= 60
                use_groq = config.groq.api_keys and (tokens or heuristic_importance >= 60)
                
                if use_groq:
                    ai_analysis = await self._analyze_with_groq(title, description, tokens)
                    if ai_analysis:
                        sentiment = NewsSentiment(ai_analysis['sentiment'])
                        score = ai_analysis['score']
                        importance = ai_analysis['importance']
                        self._cached_translation = ai_analysis.get('ru_title')
                    else:
                         importance = heuristic_importance
                else:
                    # LOCAL MODEL fallback (The "Lazy" request)
                    # Use Naive Bayes classifier trained on heuristics
                    label, confidence = local_brain.predict(title + " " + description)
                    
                    if label == 'noise':
                        # Downgrade score massively
                        importance = 10 
                    else:
                        # Use standard calc but boost if model is confident
                        importance = self._calculate_importance(title, tokens, sentiment)
                        if confidence > 70:
                             importance += 10
                    
                    # Basic rule check still applies as safety net
                    if self._is_noise(title):
                        importance = 0
                        
                # 3. DIRECTION & SIGNAL (The "Actionable" part)
                direction, dir_conf = local_brain.predict_direction(title + " " + description)
                signal_text = ""
                
                if direction != "NEUTRAL" and dir_conf > 60:
                    # We have a directional signal
                    # Find primary token
                    primary_token = tokens[0] if tokens else "MARKET"
                    emoji_dir = "🟢" if direction == "LONG" else "🔴"
                    signal_text = f"🎯 <b>SIGNAL: {emoji_dir} {direction} {primary_token}</b> ({int(dir_conf)}%)"

                news = NewsItem(
                    news_id=news_id,
                    source=source,
                    title=title,
                    summary=description[:200],
                    url=link,
                    timestamp=int(time.time() * 1000),
                    sentiment=sentiment,
                    sentiment_score=score,
                    mentioned_tokens=tokens,
                    importance=importance
                )
                
                # Store AI analysis for _send_alert (signal, ru_title, etc)
                if 'ai_analysis' in dir() and ai_analysis:
                    news._ai_analysis = ai_analysis
                news.signal_text = signal_text
                
                self.news.append(news)
                self.stats['news_fetched'] += 1
                
                # === ULTRA-STRICT FILTERING ===
                # Only 100% news: Important AND Reliable
                ai_data = getattr(news, '_ai_analysis', {})
                reliability = ai_data.get('reliability', 50)
                
                if importance >= 90 and reliability >= 85:
                    await self._send_alert(news)
                elif "BINANCE" in title.upper() and "LISTING" in title.upper():
                    await self._send_alert(news)
                
                await self._notify_callbacks(news)
            
            if len(self.news) > self.max_news:
                self.news = self.news[-self.max_news:]
        except Exception as e:
            logger.error(f"RSS parse error: {e}")
    
    def _clean_html(self, text: str) -> str:
        """Очистить HTML теги"""
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'&[a-zA-Z]+;', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _analyze_sentiment(self, text: str) -> tuple:
        """Анализ сентимента"""
        text_lower = text.lower()
        
        bullish_count = sum(1 for kw in self.BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in self.BEARISH_KEYWORDS if kw in text_lower)
        
        total = bullish_count + bearish_count
        if total == 0:
            return NewsSentiment.NEUTRAL, 0
        
        score = (bullish_count - bearish_count) / total
        
        if score > 0.5:
            return NewsSentiment.VERY_BULLISH, score
        elif score > 0.2:
            return NewsSentiment.BULLISH, score
        elif score < -0.5:
            return NewsSentiment.VERY_BEARISH, score
        elif score < -0.2:
            return NewsSentiment.BEARISH, score
        else:
            return NewsSentiment.NEUTRAL, score
    
    def _is_noise(self, text: str) -> bool:
        """Check if news is likely noise/clickbait"""
        text_lower = text.lower()
        if any(kw in text_lower for kw in self.IGNORE_KEYWORDS):
            return True
        return False

    def _extract_tokens(self, text: str) -> List[str]:
        """Извлечь упомянутые токены"""
        text_upper = text.upper()
        found = []
        
        for token in self.TRACKED_TOKENS:
            if token in text_upper or f"${token}" in text_upper:
                found.append(token)
        
        # Also check full names
        name_map = {
            'BITCOIN': 'BTC', 'ETHEREUM': 'ETH', 'SOLANA': 'SOL',
            'RIPPLE': 'XRP', 'CARDANO': 'ADA', 'DOGECOIN': 'DOGE'
        }
        
        for name, symbol in name_map.items():
            if name in text_upper and symbol not in found:
                found.append(symbol)
        
        return found
    
    def _calculate_importance(
        self,
        title: str,
        tokens: List[str],
        sentiment: NewsSentiment
    ) -> int:
        """Рассчитать важность новости"""
        importance = 50
        
        # Penalize if no tokens found (generic news)
        if not tokens:
            importance -= 15
        else:
            importance += len(tokens) * 3  # Reduced from 5
        
        # Strong sentiment = important
        if sentiment in [NewsSentiment.VERY_BULLISH, NewsSentiment.VERY_BEARISH]:
            importance += 15 # Reduced from 20
        
        # Key words boost (Critical events)
        title_lower = title.lower()
        
        # HACKS / SECURITY (High Priority)
        if any(kw in title_lower for kw in ['hack', 'exploit', 'взлом', 'scam', 'drain']):
            importance += 35
            
        # LISTINGS (High Priority)
        if any(kw in title_lower for kw in ['binance listing', 'coinbase listing', 'upbit listing', 'листинг']):
            importance += 30
            
        # REGULATION / SEC
        if any(kw in title_lower for kw in ['sec', 'lawsuit', 'ban', 'doj', 'arrest']):
            importance += 25
            
        # Noise reduction (Analysis/Predictions)
        if any(kw in title_lower for kw in ['analysis', 'predict', 'could', 'might']):
            importance -= 20

        return min(100, max(0, importance))

    def _get_current_key(self) -> Tuple[Optional[str], int]:
        """Get the next API key in the rotation and its index"""
        if not config.groq.api_keys:
            return None, 0
        
        idx = self._key_index % len(config.groq.api_keys)
        key = config.groq.api_keys[idx]
        self._key_index += 1
        return key, idx

    async def _analyze_with_groq(self, title: str, summary: str, tokens: List[str]) -> Optional[Dict]:
        """
        Analyze news with IDEAL FILTERS:
        1. Fake/Clickbait Detection
        2. Source Reliability  
        3. Crypto Relevance
        4. Actionability Score
        """
        async with self._ai_lock:
            try:
                prompt = f"""You are a professional crypto news analyst. Analyze this news.

TITLE: {title}
SUMMARY: {summary}
TOKENS: {', '.join(tokens) if tokens else 'None'}

RESPOND IN JSON:

{{
  "importance": <0-100>,
  "sentiment": "<very_bullish|bullish|neutral|bearish|very_bearish>",
  "score": <-1.0 to 1.0>,
  "is_fake": <true|false>,
  "is_clickbait": <true|false>,
  "is_crypto_relevant": <true|false>,
  "is_actionable": <true|false>,
  "reliability": <0-100>,
  "category": "<listing|hack|regulation|partnership|whale|rumor|analysis|other>",
  "urgency": "<immediate|hours|days|none>",
  "signal": "<LONG|SHORT|NEUTRAL>",
  "primary_token": "<SYMBOL or null>",
  "ru_title": "<Russian translation>"
}}

RULES:

IMPORTANCE:
- 95-100: Hacks, exploits, major exchange down
- 90-95: Binance/Coinbase listings, SEC decisions
- 80-89: Fortune 500 partnership, protocol upgrade
- 60-79: Medium exchange listings, tech news
- 40-59: General crypto news
- 20-39: Analysis, predictions
- 0-19: Irrelevant, noise

IS_FAKE = true if: prediction, "could reach", pump language, unverified
IS_CLICKBAIT = true if: question headline, "you won't believe", top 10 lists
IS_CRYPTO_RELEVANT = false if: only stocks/politics with no crypto link
IS_ACTIONABLE = true if: specific token + catalyst + breaking news

RELIABILITY:
- 90-100: Official, SEC, exchange blogs
- 70-89: CoinDesk, CoinTelegraph, Reuters
- 50-69: Watcher.Guru, Decrypt
- 30-49: Twitter influencers
- 0-29: Rumors, shills

SIGNAL:
- LONG: Very bullish news (listings, partnerships, adoption)
- SHORT: Very bearish (hacks, SEC lawsuits, delistings)
- NEUTRAL: Mixed or unclear

RU_TITLE: Professional Russian translation

JSON ONLY. BE ULTRA-CONSERVATIVE. IF NOT 100% SURE, LOWER THE RELIABILITY AND IMPORTANCE."""

                # 1. Attempt Groq with rotation
                if config.groq.api_keys:
                    max_retries = len(config.groq.api_keys)
                    for attempt in range(max_retries):
                        api_key, key_idx = self._get_current_key()
                        if not api_key: break
                        
                        logger.debug(f"🤖 Groq Analysis attempt {attempt+1}/{max_retries}")
                        await asyncio.sleep(2.0) # Rate limit safety

                        session = await self._get_session()
                        try:
                            async with session.post(
                                f"{config.groq.base_url}/chat/completions",
                                headers={
                                    "Authorization": f"Bearer {api_key}",
                                    "Content-Type": "application/json"
                                },
                                json={
                                    "model": config.groq.model,
                                    "messages": [{"role": "user", "content": prompt}],
                                    "temperature": 0.1,
                                    "max_tokens": 500
                                },
                                timeout=15
                            ) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    content = data['choices'][0]['message']['content']
                                    
                                    if '{' in content and '}' in content:
                                        try:
                                            start = content.find('{')
                                            end = content.rfind('}') + 1
                                            result = json.loads(content[start:end])
                                            
                                            # Filter out noise/fakes
                                            if result.get('is_fake', False) or not result.get('is_crypto_relevant', True):
                                                result['importance'] = 0
                                            
                                            return result
                                        except:
                                            continue
                        except Exception as e:
                            logger.debug(f"Groq iteration error: {e}")
                            continue

                # 2. Fallback to OpenRouter (Reliable Backup with Smart Tiering)
                if self.openrouter:
                    # Heuristic to detect high-impact news before calling AI
                    urgent_kw = ["listing", "binance", "coinbase", "hack", "exploit", "sec", "lawsuit", "court", "etf", "blackrock", "scam", "breach"]
                    is_urgent = any(kw in title.lower() or kw in summary.lower() for kw in urgent_kw)
                    
                    if is_urgent:
                        logger.info(f"� CRITICAL NEWS: {title[:40]}... (Using TOP MODELS)")
                    else:
                        logger.info(f"🔄 OpenRouter fallback: {title[:40]}...")
                        
                    try:
                        return await self.openrouter.analyze_news(title, summary, tokens, high_impact=is_urgent)
                    except Exception as e:
                        logger.error(f"OpenRouter news fallback failed: {e}")

                return None
            except Exception as e:
                logger.error(f"AI News analysis logic failed: {e}")
                return None

    async def _translate_text(self, text: str) -> str:
        """Translate text to Russian using Groq (Fallback)"""
        async with self._ai_lock:
            max_retries = len(config.groq.api_keys)
            if max_retries == 0: return text
            
            for attempt in range(max_retries):
                try:
                    api_key, key_idx = self._get_current_key()
                    if not api_key: return text
                    
                    await asyncio.sleep(2.5)
                    
                    prompt = f"Translate this crypto news headline to professional Russian. Only return the translation, no extra text:\n\n{text}"
                    
                    session = await self._get_session()
                    async with session.post(
                        f"{config.groq.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": config.groq.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.1
                        },
                        timeout=10
                    ) as resp:
                        if resp.status == 200:
                            res_json = await resp.json()
                            translation = res_json['choices'][0]['message']['content'].strip()
                            return translation.replace('"', '').replace('«', '').replace('»', '')
                        elif resp.status in [401, 429]:
                            logger.warning(f"⚠️ Translation failed (Error {resp.status}) on Key {key_idx + 1}. Cooling down...")
                            await asyncio.sleep(5 if resp.status == 429 else 1)
                            if attempt < max_retries - 1: continue
                        return text
                except Exception:
                    if attempt < max_retries - 1: continue
                    return text
            return text

    async def handle_external_listing(self, symbol: str, exchange: str):
        """Handle listings from GlobalListingWatcher as news"""
        logger.info(f"🆕 External listing detected: {symbol} on {exchange}")
        
        # Create a synthetic news item for the listing
        news_id = f"listing_{exchange}_{symbol}_{int(time.time())}"
        title = f"BINANCE NEW LISTING: {symbol}" if "BINANCE" in exchange.upper() else f"NEW LISTING: {symbol} on {exchange}"
        
        # Map exchange to correct announcement URL
        exchange_urls = {
            'binance': 'https://www.binance.com/en/support/announcement/new-cryptocurrency-listing',
            'bingx': 'https://bingx.com/en/support/announcement/',
            'okx': 'https://www.okx.com/support/hc/en-us/sections/360000030652-New-Listings',
            'bybit': 'https://announcements.bybit.com/en/new-coin-listings/',
            'gate': 'https://www.gate.io/articlelist/ann/0',
            'gate.io': 'https://www.gate.io/articlelist/ann/0',
            'kucoin': 'https://www.kucoin.com/news/categories/new-listings',
            'bitget': 'https://www.bitget.com/support/sections/new-listings',
            'mexc': 'https://www.mexc.com/support/sections/360000679912',
        }
        listing_url = exchange_urls.get(exchange.lower(), f'https://www.google.com/search?q={symbol}+listing+{exchange}')
        
        news = NewsItem(
            news_id=news_id,
            source=NewsSource.WATCHER_GURU, # Use as proxy
            title=title,
            summary=f"Exchange {exchange} has just listed {symbol}. This is a high-volatility event.",
            url=listing_url,
            timestamp=int(time.time() * 1000),
            sentiment=NewsSentiment.VERY_BULLISH,
            sentiment_score=0.9,
            mentioned_tokens=[symbol.upper()],
            importance=100 # Listings are always 100
        )
        
        # Add AI data directly to bypass analysis for 100% hits
        news._ai_analysis = {
            'importance': 100,
            'sentiment': 'very_bullish',
            'score': 0.9,
            'reliability': 100,
            'category': 'listing',
            'urgency': 'immediate',
            'signal': 'LONG',
            'primary_token': symbol.upper(),
            'ru_title': f"🔥 ЛИСТИНГ: {symbol} на {exchange.upper()}"
        }
        
        self.news.append(news)
        await self._send_alert(news)

    async def _send_alert(self, news: NewsItem):
        """Отправить алерт с сигналом LONG/SHORT"""
        if not self.telegram:
            return
        
        # Get cached AI analysis
        ai_data = getattr(news, '_ai_analysis', {})
        
        # Signal emoji
        signal = ai_data.get('signal', 'NEUTRAL')
        signal_emoji = {'LONG': '🟢 LONG', 'SHORT': '🔴 SHORT', 'NEUTRAL': '⚪ NEUTRAL'}
        signal_text = signal_emoji.get(signal, '⚪ NEUTRAL')
        
        # Sentiment emoji
        sentiment_emoji = {
            NewsSentiment.VERY_BULLISH: "🚀",
            NewsSentiment.BULLISH: "📈",
            NewsSentiment.NEUTRAL: "📰",
            NewsSentiment.BEARISH: "📉",
            NewsSentiment.VERY_BEARISH: "💀"
        }
        emoji = sentiment_emoji.get(news.sentiment, "📰")
        
        # Tokens - prefer AI-detected primary_token
        ai_token = ai_data.get('primary_token')
        if ai_token and ai_token != 'null' and ai_token.upper() != 'NULL':
            primary_token = ai_token.upper()
        elif news.mentioned_tokens:
            primary_token = news.mentioned_tokens[0]
        else:
            primary_token = None
        
        # Russian title from AI (with fallback)
        ru_title = ai_data.get('ru_title')
        if not ru_title or ru_title == news.title:
            logger.info(f"🔄 Translating news: {news.title[:40]}...")
            ru_title = await self._translate_text(news.title)

        
        # Category
        category = ai_data.get('category', 'other').upper()
        reliability = ai_data.get('reliability', 50)
        # Build token line
        token_line = f"📊 <b>Токен:</b> #{primary_token}" if primary_token else "📊 <b>Токен:</b> Общий рынок"
        trade_link = f'👉 <a href="https://futures.mexc.com/exchange/{primary_token}_USDT"><b>ТОРГОВАТЬ {primary_token}</b></a>' if primary_token else ''
        
        msg = f"""
{emoji} <b>{ru_title}</b>
━━━━━━━━━━━━━━━━━━
<i>{news.title}</i>

🎯 <b>СИГНАЛ: {signal_text}</b>

{token_line}
⚡ <b>Важность:</b> {news.importance}/100
📁 <b>Категория:</b> {category}
🔒 <b>Достоверность:</b> {reliability}/100

🔗 <a href="{news.url}">Читать оригинал</a>
{trade_link}
""" if news.url else f"""
{trade_link}
"""
        
        await self.telegram.send_message(msg)
        self.stats['alerts_sent'] += 1
        logger.info(f"📨 ALERT SENT: {signal} {primary_token or 'MARKET'} | {news.title[:40]}...")
    
    def get_recent_news(self, limit: int = 20) -> List[NewsItem]:
        """Получить последние новости"""
        return sorted(self.news, key=lambda n: n.timestamp, reverse=True)[:limit]
    
    def get_news_by_token(self, token: str) -> List[NewsItem]:
        """Получить новости по токену"""
        return [n for n in self.news if token.upper() in n.mentioned_tokens]
    
    def get_sentiment_summary(self) -> Dict:
        """Сводка сентимента"""
        recent = self.get_recent_news(50)
        
        if not recent:
            return {'overall': 'neutral', 'score': 0}
        
        scores = [n.sentiment_score for n in recent]
        avg_score = sum(scores) / len(scores)
        
        bullish = len([n for n in recent if n.sentiment_score > 0.2])
        bearish = len([n for n in recent if n.sentiment_score < -0.2])
        
        return {
            'overall': 'bullish' if avg_score > 0.1 else 'bearish' if avg_score < -0.1 else 'neutral',
            'score': round(avg_score, 3),
            'bullish_count': bullish,
            'bearish_count': bearish,
            'total': len(recent)
        }

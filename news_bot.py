"""
MEXC Pump Monitor - News Bot
Парсинг крипто-новостей из различных источников
"""

import asyncio
import logging
import time
import re
import aiohttp
from typing import Dict, List, Optional, Callable
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
        'анализ цены', 'прогноз', 'мнение', 'топ криптовалют'
    ]
    
    # Common crypto tokens to track
    TRACKED_TOKENS = [
        'BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'SHIB', 'AVAX',
        'DOT', 'LINK', 'MATIC', 'UNI', 'ATOM', 'LTC', 'BCH', 'NEAR',
        'APT', 'ARB', 'OP', 'SUI', 'SEI', 'TIA', 'JUP', 'PEPE', 'WIF',
        'BONK', 'FLOKI', 'MEME', 'AI', 'FET', 'RNDR', 'INJ', 'TRX'
    ]
    
    # RSS Feed URLs
    RSS_FEEDS = {
        NewsSource.COINDESK: "https://www.coindesk.com/arc/outboundfeeds/rss/",
        NewsSource.COINTELEGRAPH: "https://cointelegraph.com/rss",
    }
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        self._session: Optional[aiohttp.ClientSession] = None
        
        # News storage
        self.news: List[NewsItem] = []
        self.max_news = 500
        
        # Seen news (to avoid duplicates)
        self._seen_ids: set = set()
        
        # Callbacks
        self._callbacks: List[Callable] = []
        
        # Stats
        self.stats = {
            'news_fetched': 0,
            'alerts_sent': 0,
            'sources_active': 0
        }
        
        self._running = False
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get aiohttp session"""
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
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
    
    async def _fetch_loop(self):
        """Цикл получения новостей"""
        while self._running:
            try:
                await self._fetch_all_sources()
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
            self._fetch_crypto_news_api()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _fetch_coindesk(self):
        """Получить новости с CoinDesk"""
        try:
            session = await self._get_session()
            url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
            
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    await self._parse_rss(text, NewsSource.COINDESK)
                    
        except Exception as e:
            logger.debug(f"CoinDesk fetch failed: {e}")
    
    async def _fetch_cointelegraph(self):
        """Получить новости с CoinTelegraph"""
        try:
            session = await self._get_session()
            url = "https://cointelegraph.com/rss"
            
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    await self._parse_rss(text, NewsSource.COINTELEGRAPH)
                    
        except Exception as e:
            logger.debug(f"CoinTelegraph fetch failed: {e}")
    
    async def _fetch_crypto_news_api(self):
        """Получить новости через API (симуляция)"""
        # В реальности здесь был бы вызов API типа CryptoCompare News
        pass
    
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
                    
                if self._is_noise(title):
                    continue
                
                # Use DeepSeek if enabled
                if config.deepseek.api_key:
                    ds_analysis = await self._analyze_with_deepseek(title, description, tokens)
                    if ds_analysis:
                        sentiment = NewsSentiment(ds_analysis['sentiment'])
                        score = ds_analysis['score']
                        importance = ds_analysis['importance']
                        # Translation logic handled later or integrated? 
                        # Let's use the translation from DeepSeek if available
                        self._cached_translation = ds_analysis.get('ru_title')
                    else:
                         importance = self._calculate_importance(title, tokens, sentiment)
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
                
                # Attach signal to news object (hacky but works for alert)
                news.signal_text = signal_text
                
                self.news.append(news)
                self.stats['news_fetched'] += 1
                
                # Alert if important (Higher threshold)
                if importance >= 80:
                    await self._send_alert(news)
                
                # Notify callbacks
                for cb in self._callbacks:
                    try:
                        if asyncio.iscoroutinefunction(cb):
                            await cb(news)
                        else:
                            cb(news)
                    except Exception as e:
                        logger.error(f"News callback error: {e}")
            
            # Cleanup old
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

    async def _analyze_with_deepseek(self, title: str, summary: str, tokens: List[str]) -> Optional[Dict]:
        """Analyze news using DeepSeek AI"""
        try:
            if not config.deepseek.api_key: return None
            
            prompt = f"""
            Analyze this crypto news for a trading bot.
            Title: {title}
            Summary: {summary}
            Tokens: {', '.join(tokens)}
            
            Respond in JSON format with:
            1. importance (0-100 integer): Rate how critical this logic is for price. 
               - Hacks/Sec/Listings = 90-100
               - Partnerships/Technology = 50-80
               - Opinion/Analysis/Prediction = 0-20
            2. sentiment (string): very_bullish, bullish, neutral, bearish, very_bearish
            3. score (float -1.0 to 1.0): Sentiment score
            4. ru_title (string): Translate title to Russian professionally
            
            JSON ONLY. No markdown.
            """
            
            session = await self._get_session()
            headers = {
                "Authorization": f"Bearer {config.deepseek.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": config.deepseek.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1
            }
            
            async with session.post(f"{config.deepseek.base_url}/chat/completions", headers=headers, json=data, timeout=10) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    content = res_json['choices'][0]['message']['content']
                    # Clean markdown if present
                    content = content.replace('```json', '').replace('```', '').strip()
                    return json.loads(content)
                else:
                    logger.warning(f"DeepSeek error: {resp.status} {await resp.text()}")
                    return None
        except Exception as e:
            logger.error(f"DeepSeek analysis failed: {e}")
            return None

        return text # Return original if failed
    
    async def _send_alert(self, news: NewsItem):
        """Отправить алерт"""
        if not self.telegram:
            return
        
        sentiment_emoji = {
            NewsSentiment.VERY_BULLISH: "🚀🟢",
            NewsSentiment.BULLISH: "🟢",
            NewsSentiment.NEUTRAL: "⚪",
            NewsSentiment.BEARISH: "🔴",
            NewsSentiment.VERY_BEARISH: "💀🔴"
        }
        
        emoji = sentiment_emoji.get(news.sentiment, "📰")
        tokens_str = ", ".join(news.mentioned_tokens) if news.mentioned_tokens else "N/A"
        
        # Check cache from DeepSeek first
        if hasattr(self, '_cached_translation') and self._cached_translation:
             ru_title = self._cached_translation
             self._cached_translation = None # Reset
        else:
             ru_title = await self._translate_text(news.title)
             
        # Add Signal if exists
        signal_line = getattr(news, 'signal_text', "")
        if signal_line:
            signal_line = f"\n{signal_line}\n"
        
        msg = f"""
📰 <b>CRYPTO NEWS / КРИПТО НОВОСТЬ</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{ru_title}</b>
<i>({news.title})</i>
{signal_line}
📊 <b>Tokens / Токены:</b> {tokens_str}
🎯 <b>Importance / Важность:</b> {news.importance}/100
📈 <b>Sentiment / Сентимент:</b> {news.sentiment.value}

🔗 <a href="{news.url}">Read More / Читать далее</a>
👉 <a href="https://futures.mexc.com/exchange/{news.mentioned_tokens[0] if news.mentioned_tokens else 'BTC'}_USDT"><b>TRADE NOW</b></a>
📡 Source / Источник: {news.source.value.title()}
"""
        
        await self.telegram.send_message(msg)
        self.stats['alerts_sent'] += 1
    
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

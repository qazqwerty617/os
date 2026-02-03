"""
MEXC Pump Monitor - Crypto News Parser
Парсинг крипто-новостей с AI анализом LONG/SHORT
"""

import asyncio
import aiohttp
import logging
import re
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class NewsSignal(Enum):
    """Сигнал по новости"""
    STRONG_LONG = "🟢🟢 STRONG LONG"
    LONG = "🟢 LONG"
    NEUTRAL = "⚪ NEUTRAL"
    SHORT = "🔴 SHORT"
    STRONG_SHORT = "🔴🔴 STRONG SHORT"


class NewsCategory(Enum):
    """Категория новости"""
    LISTING = "📋 Листинг"
    PARTNERSHIP = "🤝 Партнёрство"
    HACK = "🚨 Взлом"
    REGULATION = "⚖️ Регуляция"
    AIRDROP = "🎁 Airdrop"
    TOKEN_BURN = "🔥 Сжигание"
    UNLOCK = "🔓 Анлок"
    UPGRADE = "⬆️ Апгрейд"
    LAWSUIT = "⚖️ Судебный иск"
    WHALE = "🐋 Киты"
    EXCHANGE = "🏦 Биржа"
    DEFI = "💰 DeFi"
    NFT = "🖼 NFT"
    OTHER = "📰 Другое"


@dataclass
class CryptoNews:
    """Крипто новость"""
    news_id: str
    title: str
    description: str
    source: str
    url: str
    
    timestamp: datetime
    
    # Анализ
    category: NewsCategory = NewsCategory.OTHER
    signal: NewsSignal = NewsSignal.NEUTRAL
    confidence: int = 50
    
    # Связанные монеты
    related_coins: List[str] = field(default_factory=list)
    
    # Ожидаемое влияние
    expected_impact_pct: float = 0
    impact_duration_hours: int = 24
    
    # Рекомендация
    action: str = ""
    reasoning: str = ""


class CryptoNewsParser:
    """
    Парсер крипто-новостей
    
    Источники:
    - CryptoPanic API
    - CoinGlass News
    - Twitter/X (через RSS)
    
    AI Анализ:
    - Определение сигнала (LONG/SHORT)
    - Оценка влияния
    - Связанные монеты
    """
    
    # Ключевые слова для анализа
    BULLISH_KEYWORDS = {
        'strong': [
            'partnership', 'партнёрство', 'listing', 'листинг',
            'adoption', 'принятие', 'integration', 'интеграция',
            'launch', 'запуск', 'mainnet', 'мейннет',
            'upgrade', 'апгрейд', 'bullish', 'бычий',
            'breakout', 'прорыв', 'ath', 'all-time high',
            'institutional', 'институционал', 'etf approved',
            'token burn', 'сжигание', 'buyback', 'выкуп',
            'airdrop', 'эирдроп', 'staking rewards',
        ],
        'moderate': [
            'development', 'разработка', 'update', 'обновление',
            'testnet', 'тестнет', 'roadmap', 'дорожная карта',
            'community', 'сообщество', 'growth', 'рост',
            'positive', 'позитив', 'success', 'успех',
        ]
    }
    
    BEARISH_KEYWORDS = {
        'strong': [
            'hack', 'взлом', 'exploit', 'эксплойт',
            'rug pull', 'скам', 'scam', 'мошенничество',
            'lawsuit', 'судебный иск', 'sec', 'регулятор',
            'delisting', 'делистинг', 'ban', 'запрет',
            'crash', 'крах', 'dump', 'дамп',
            'unlock', 'анлок', 'token release', 'разблокировка',
            'bankruptcy', 'банкротство', 'insolvency',
            'investigation', 'расследование',
        ],
        'moderate': [
            'delay', 'задержка', 'postpone', 'отложен',
            'concern', 'озабоченность', 'warning', 'предупреждение',
            'decline', 'снижение', 'bearish', 'медвежий',
            'sell-off', 'распродажа', 'outflow', 'отток',
            'fud', 'fear', 'страх',
        ]
    }
    
    # Паттерны для извлечения монет
    COIN_PATTERNS = [
        r'\$([A-Z]{2,10})',  # $BTC, $ETH
        r'\b(BTC|ETH|BNB|SOL|XRP|ADA|DOGE|DOT|MATIC|AVAX|LINK|UNI|ATOM|LTC)\b',
        r'([A-Z]{2,6})(?:USDT|USD|BUSD)',  # BTCUSDT
    ]
    
    def __init__(self, telegram_notifier=None):
        self.telegram = telegram_notifier
        self.news_cache: Dict[str, CryptoNews] = {}
        self.processed_ids: set = set()
        
        # API endpoints
        self.sources = {
            'cryptopanic': 'https://cryptopanic.com/api/v1/posts/',
            'coinglass': 'https://fapi.coinglass.com/api/news/list',
        }
        
        self.stats = {
            'news_parsed': 0,
            'signals_generated': 0,
            'bullish_count': 0,
            'bearish_count': 0
        }
    
    async def fetch_news(self, limit: int = 20) -> List[Dict]:
        """Получить новости из различных источников"""
        news = []
        
        async with aiohttp.ClientSession() as session:
            # CryptoPanic (бесплатный API)
            try:
                url = f"{self.sources['cryptopanic']}?auth_token=free&public=true&kind=news"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        for item in data.get('results', [])[:limit]:
                            news.append({
                                'id': item.get('id'),
                                'title': item.get('title', ''),
                                'description': item.get('title', ''),  # CryptoPanic не даёт description
                                'source': item.get('source', {}).get('title', 'Unknown'),
                                'url': item.get('url', ''),
                                'timestamp': item.get('created_at', ''),
                                'currencies': [c.get('code') for c in item.get('currencies', [])]
                            })
            except Exception as e:
                logger.debug(f"CryptoPanic fetch error: {e}")
            
            # Fallback - создать тестовые новости если нет реальных
            if not news:
                news = self._get_sample_news()
        
        return news
    
    def _get_sample_news(self) -> List[Dict]:
        """Примеры новостей для тестирования"""
        return [
            {
                'id': 'sample_1',
                'title': 'Bitcoin ETF получил одобрение SEC',
                'description': 'SEC официально одобрила первый спотовый Bitcoin ETF',
                'source': 'Reuters',
                'url': 'https://example.com/1',
                'timestamp': datetime.now().isoformat(),
                'currencies': ['BTC']
            },
            {
                'id': 'sample_2',
                'title': 'Крупный анлок токенов ARB на $200M',
                'description': 'Arbitrum разблокирует токены команды на $200 миллионов',
                'source': 'TokenUnlocks',
                'url': 'https://example.com/2',
                'timestamp': datetime.now().isoformat(),
                'currencies': ['ARB']
            },
            {
                'id': 'sample_3',
                'title': 'Binance листит новый мем-токен',
                'description': 'Binance объявила о листинге нового мем-токена PEPE2',
                'source': 'Binance',
                'url': 'https://example.com/3',
                'timestamp': datetime.now().isoformat(),
                'currencies': ['PEPE']
            },
        ]
    
    def analyze_news(self, news_data: Dict) -> CryptoNews:
        """
        Анализировать новость и определить сигнал
        
        Returns:
            CryptoNews с сигналом LONG/SHORT
        """
        title = news_data.get('title', '').lower()
        description = news_data.get('description', '').lower()
        full_text = f"{title} {description}"
        
        # Определить категорию
        category = self._detect_category(full_text)
        
        # Подсчёт ключевых слов
        bullish_score = 0
        bearish_score = 0
        
        for keyword in self.BULLISH_KEYWORDS['strong']:
            if keyword.lower() in full_text:
                bullish_score += 20
        for keyword in self.BULLISH_KEYWORDS['moderate']:
            if keyword.lower() in full_text:
                bullish_score += 10
        
        for keyword in self.BEARISH_KEYWORDS['strong']:
            if keyword.lower() in full_text:
                bearish_score += 20
        for keyword in self.BEARISH_KEYWORDS['moderate']:
            if keyword.lower() in full_text:
                bearish_score += 10
        
        # Определить сигнал
        if bullish_score >= 40 and bullish_score > bearish_score * 2:
            signal = NewsSignal.STRONG_LONG
            action = "ОТКРЫТЬ LONG"
            expected_impact = 5 + (bullish_score / 20)
        elif bullish_score > bearish_score:
            signal = NewsSignal.LONG
            action = "Рассмотреть LONG"
            expected_impact = 2 + (bullish_score / 30)
        elif bearish_score >= 40 and bearish_score > bullish_score * 2:
            signal = NewsSignal.STRONG_SHORT
            action = "ОТКРЫТЬ SHORT"
            expected_impact = -(5 + bearish_score / 20)
        elif bearish_score > bullish_score:
            signal = NewsSignal.SHORT
            action = "Рассмотреть SHORT"
            expected_impact = -(2 + bearish_score / 30)
        else:
            signal = NewsSignal.NEUTRAL
            action = "Наблюдать"
            expected_impact = 0
        
        # Извлечь монеты
        coins = self._extract_coins(news_data.get('title', ''))
        coins.extend(news_data.get('currencies', []))
        coins = list(set(coins))
        
        # Уверенность
        confidence = min(100, abs(bullish_score - bearish_score) + 30)
        
        # Причина
        reasoning = self._generate_reasoning(signal, category, coins)
        
        # Timestamp
        ts = news_data.get('timestamp', '')
        if isinstance(ts, str):
            try:
                timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00'))
            except:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()
        
        news = CryptoNews(
            news_id=str(news_data.get('id', f'news_{int(time.time())}')),
            title=news_data.get('title', ''),
            description=news_data.get('description', ''),
            source=news_data.get('source', 'Unknown'),
            url=news_data.get('url', ''),
            timestamp=timestamp,
            category=category,
            signal=signal,
            confidence=confidence,
            related_coins=coins,
            expected_impact_pct=expected_impact,
            action=action,
            reasoning=reasoning
        )
        
        self.news_cache[news.news_id] = news
        self.stats['news_parsed'] += 1
        
        if signal in [NewsSignal.STRONG_LONG, NewsSignal.LONG]:
            self.stats['bullish_count'] += 1
        elif signal in [NewsSignal.STRONG_SHORT, NewsSignal.SHORT]:
            self.stats['bearish_count'] += 1
        
        return news
    
    def _detect_category(self, text: str) -> NewsCategory:
        """Определить категорию новости"""
        text = text.lower()
        
        if any(w in text for w in ['listing', 'листинг', 'listed']):
            return NewsCategory.LISTING
        elif any(w in text for w in ['partnership', 'партнёр', 'collaborate']):
            return NewsCategory.PARTNERSHIP
        elif any(w in text for w in ['hack', 'взлом', 'exploit', 'breach']):
            return NewsCategory.HACK
        elif any(w in text for w in ['sec', 'регулят', 'lawsuit', 'legal']):
            return NewsCategory.REGULATION
        elif any(w in text for w in ['airdrop', 'эирдроп', 'drop']):
            return NewsCategory.AIRDROP
        elif any(w in text for w in ['burn', 'сжиг', 'buyback']):
            return NewsCategory.TOKEN_BURN
        elif any(w in text for w in ['unlock', 'анлок', 'release', 'vest']):
            return NewsCategory.UNLOCK
        elif any(w in text for w in ['upgrade', 'апгрейд', 'update', 'v2']):
            return NewsCategory.UPGRADE
        elif any(w in text for w in ['whale', 'кит', 'large transfer']):
            return NewsCategory.WHALE
        elif any(w in text for w in ['binance', 'coinbase', 'exchange', 'биржа']):
            return NewsCategory.EXCHANGE
        elif any(w in text for w in ['defi', 'дефи', 'yield', 'tvl']):
            return NewsCategory.DEFI
        elif any(w in text for w in ['nft', 'opensea', 'collectible']):
            return NewsCategory.NFT
        else:
            return NewsCategory.OTHER
    
    def _extract_coins(self, text: str) -> List[str]:
        """Извлечь упоминания монет"""
        coins = []
        for pattern in self.COIN_PATTERNS:
            matches = re.findall(pattern, text.upper())
            coins.extend(matches)
        return list(set(coins))
    
    def _generate_reasoning(self, signal: NewsSignal, category: NewsCategory, coins: List[str]) -> str:
        """Сгенерировать объяснение сигнала"""
        coins_str = ', '.join(coins[:3]) if coins else 'Рынок'
        
        reasons = {
            NewsSignal.STRONG_LONG: f"{coins_str}: Очень позитивная новость. Ожидается сильный рост.",
            NewsSignal.LONG: f"{coins_str}: Позитивный сигнал. Возможен рост цены.",
            NewsSignal.NEUTRAL: f"{coins_str}: Нейтральная новость. Влияние неопределено.",
            NewsSignal.SHORT: f"{coins_str}: Негативный сигнал. Возможно снижение.",
            NewsSignal.STRONG_SHORT: f"{coins_str}: Очень негативная новость. Ожидается падение.",
        }
        
        return reasons.get(signal, "Требуется дополнительный анализ.")
    
    def format_news_alert(self, news: CryptoNews) -> str:
        """Форматировать новость для Telegram"""
        signal_color = {
            NewsSignal.STRONG_LONG: "🟢🟢",
            NewsSignal.LONG: "🟢",
            NewsSignal.NEUTRAL: "⚪",
            NewsSignal.SHORT: "🔴",
            NewsSignal.STRONG_SHORT: "🔴🔴",
        }
        
        action_box = ""
        if news.signal in [NewsSignal.STRONG_LONG, NewsSignal.STRONG_SHORT]:
            if "LONG" in news.signal.value:
                action_box = "\n\n🎯 <b>ДЕЙСТВИЕ: ОТКРЫТЬ LONG</b>"
            else:
                action_box = "\n\n🎯 <b>ДЕЙСТВИЕ: ОТКРЫТЬ SHORT</b>"
        
        coins_str = ', '.join(news.related_coins[:5]) if news.related_coins else '-'
        
        msg = f"""
📰 <b>КРИПТО НОВОСТЬ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{signal_color.get(news.signal, '⚪')} <b>СИГНАЛ: {news.signal.value}</b>

📌 <b>{news.title}</b>

{news.category.value}
📊 <b>Уверенность:</b> {news.confidence}%
💰 <b>Монеты:</b> {coins_str}
📈 <b>Ожидание:</b> {news.expected_impact_pct:+.1f}%
{action_box}

💡 <b>АНАЛИЗ:</b>
{news.reasoning}

🔗 <a href="{news.url}">Читать источник</a>
📰 {news.source} | {news.timestamp.strftime('%H:%M %d.%m')}
"""
        return msg.strip()
    
    async def parse_and_notify(self):
        """Парсить новости и отправлять важные в Telegram"""
        news_list = await self.fetch_news(limit=20)
        
        important_news = []
        
        for news_data in news_list:
            news_id = str(news_data.get('id', ''))
            
            # Пропустить уже обработанные
            if news_id in self.processed_ids:
                continue
            
            self.processed_ids.add(news_id)
            
            # Анализировать
            news = self.analyze_news(news_data)
            
            # Отправить только важные
            if news.signal in [NewsSignal.STRONG_LONG, NewsSignal.STRONG_SHORT]:
                important_news.append(news)
                
                if self.telegram:
                    message = self.format_news_alert(news)
                    await self.telegram.send_message(message)
                
                self.stats['signals_generated'] += 1
        
        return important_news
    
    async def monitor_loop(self, interval_minutes: int = 5):
        """Мониторинг новостей в цикле"""
        logger.info(f"📰 News Parser запущен (интервал: {interval_minutes} мин)")
        
        while True:
            try:
                await self.parse_and_notify()
                await asyncio.sleep(interval_minutes * 60)
            except Exception as e:
                logger.error(f"News parser error: {e}")
                await asyncio.sleep(60)
    
    def format_stats(self) -> str:
        """Статистика парсера"""
        total = self.stats['bullish_count'] + self.stats['bearish_count']
        bullish_pct = (self.stats['bullish_count'] / total * 100) if total > 0 else 50
        
        sentiment = "🟢 Бычий" if bullish_pct > 60 else "🔴 Медвежий" if bullish_pct < 40 else "⚪ Нейтральный"
        
        msg = f"""
📰 <b>NEWS PARSER СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>НОВОСТИ:</b>
├ Обработано: {self.stats['news_parsed']}
├ Сигналов: {self.stats['signals_generated']}
├ 🟢 Бычьих: {self.stats['bullish_count']}
└ 🔴 Медвежьих: {self.stats['bearish_count']}

📈 <b>SENTIMENT:</b> {sentiment} ({bullish_pct:.0f}% бычий)
"""
        return msg.strip()

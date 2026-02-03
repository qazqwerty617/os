"""
MEXC Pump Monitor - GPT-4 News Analyzer
Advanced news analysis using OpenAI GPT-4 API
"""

import asyncio
import aiohttp
import logging
import os
import json
from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger("GPT4Analyzer")


class SignalDirection(Enum):
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class GPT4Analysis:
    """Result of GPT-4 news analysis"""
    symbol: str
    headline: str
    direction: SignalDirection
    confidence: float  # 0-100
    summary_en: str
    summary_ru: str
    key_points: List[str]
    trading_recommendation: str
    risk_level: str  # low, medium, high
    time_horizon: str  # short, medium, long
    raw_response: Optional[str] = None


class GPT4NewsAnalyzer:
    """
    GPT-4 Powered News Analysis
    - Deep understanding of crypto news
    - Multi-language support
    - Trading signal extraction
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4-turbo-preview"  # or gpt-4, gpt-3.5-turbo
        self._session: Optional[aiohttp.ClientSession] = None
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            logger.info("🤖 GPT-4 News Analyzer initialized")
        else:
            logger.warning("⚠️ GPT-4 disabled (no OPENAI_API_KEY)")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def analyze_news(self, symbol: str, headline: str, 
                          content: str = "") -> Optional[GPT4Analysis]:
        """Analyze a news article (GPT-4 with Local Fallback)"""
        if not self.enabled:
            return self._analyze_local(symbol, headline, content)
        
        try:
            session = await self._get_session()
            
            prompt = f"""You are a professional crypto trading analyst. Analyze this news and provide trading insights.

TOKEN: {symbol}
HEADLINE: {headline}
CONTENT: {content[:1000] if content else 'No additional content'}

Respond in JSON format:
{{
    "direction": "strong_bullish|bullish|neutral|bearish|strong_bearish",
    "confidence": 0-100,
    "summary_en": "Brief English summary (1-2 sentences)",
    "summary_ru": "Краткое резюме на русском (1-2 предложения)",
    "key_points": ["point1", "point2", "point3"],
    "trading_recommendation": "Specific action: BUY/SELL/HOLD with reasoning",
    "risk_level": "low|medium|high",
    "time_horizon": "short (hours)|medium (days)|long (weeks)"
}}

Be concise and actionable. Focus on price impact."""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a crypto trading analyst. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 500
            }
            
            async with session.post(self.base_url, headers=headers, json=data) as response:
                if response.status != 200:
                    error = await response.text()
                    logger.error(f"GPT-4 API error: {error}")
                    return self._analyze_local(symbol, headline, content)
                
                result = await response.json()
                content_resp = result['choices'][0]['message']['content']
                
                try:
                    if "```json" in content_resp:
                        content_resp = content_resp.split("```json")[1].split("```")[0]
                    elif "```" in content_resp:
                        content_resp = content_resp.split("```")[1].split("```")[0]
                    
                    parsed = json.loads(content_resp.strip())
                except json.JSONDecodeError:
                    return self._analyze_local(symbol, headline, content)
                
                return GPT4Analysis(
                    symbol=symbol,
                    headline=headline,
                    direction=SignalDirection(parsed.get('direction', 'neutral')),
                    confidence=float(parsed.get('confidence', 50)),
                    summary_en=parsed.get('summary_en', ''),
                    summary_ru=parsed.get('summary_ru', ''),
                    key_points=parsed.get('key_points', []),
                    trading_recommendation=parsed.get('trading_recommendation', ''),
                    risk_level=parsed.get('risk_level', 'medium'),
                    time_horizon=parsed.get('time_horizon', 'short'),
                    raw_response=content_resp
                )
                
        except Exception as e:
            logger.error(f"GPT-4 analysis error: {e}")
            return self._analyze_local(symbol, headline, content)

    def _analyze_local(self, symbol: str, headline: str, content: str) -> GPT4Analysis:
        """Local rule-based analysis without API keys"""
        text = (headline + " " + content).lower()
        
        # Keyword scoring
        bullish_terms = ['partnership', 'launch', 'mainnet', 'listing', 'burn', 
                        'buyback', 'growth', 'surge', 'record', 'adopt', 'bull',
                        'integration', 'funding', 'secure', 'live']
        bearish_terms = ['hack', 'exploit', 'delist', 'ban', 'regulator', 
                        'lawsuit', 'crash', 'dump', 'breach', 'scam', 'bear',
                        'halt', 'suspend', 'investigation', 'fine']
        
        score = 0
        key_points = []
        
        for term in bullish_terms:
            if term in text:
                score += 1
                key_points.append(f"Bullish: {term}")
                
        for term in bearish_terms:
            if term in text:
                score -= 1.5
                key_points.append(f"Bearish: {term}")
        
        if score >= 2:
            direction = SignalDirection.STRONG_BULLISH
            rec = "High-conviction Buy"
        elif score >= 0.5:
            direction = SignalDirection.BULLISH
            rec = "Moderate Buy"
        elif score <= -2:
            direction = SignalDirection.STRONG_BEARISH
            rec = "Sell / Short immediately"
        elif score <= -0.5:
            direction = SignalDirection.BEARISH
            rec = "Reduce exposure"
        else:
            direction = SignalDirection.NEUTRAL
            rec = "Wait for volatility"
            
        confidence = min(50 + abs(score) * 10, 95)
        
        return GPT4Analysis(
            symbol=symbol,
            headline=headline,
            direction=direction,
            confidence=confidence,
            summary_en=f"Local analysis detected keywords: {', '.join(key_points)}",
            summary_ru=f"Локальный анализ нашел: {', '.join(key_points)}",
            key_points=key_points or ["No major keywords"],
            trading_recommendation=rec,
            risk_level="High" if score < 0 else "Medium",
            time_horizon="Short",
            raw_response="Local Fallback Mode"
        )
    
    async def analyze_multiple(self, news_items: List[Dict]) -> List[GPT4Analysis]:
        """Analyze multiple news items (with rate limiting)"""
        results = []
        for item in news_items[:5]:  # Limit to 5 to avoid rate limits
            analysis = await self.analyze_news(
                item.get('symbol', 'UNKNOWN'),
                item.get('title', ''),
                item.get('content', '')
            )
            if analysis:
                results.append(analysis)
            await asyncio.sleep(1)  # Rate limit
        return results
    
    async def get_market_sentiment(self, headlines: List[str]) -> Dict:
        """Get overall market sentiment from multiple headlines"""
        if not self.enabled or not headlines:
            return {"sentiment": "neutral", "confidence": 50}
        
        try:
            session = await self._get_session()
            
            prompt = f"""Analyze these crypto news headlines and determine overall market sentiment.

HEADLINES:
{chr(10).join(f'- {h}' for h in headlines[:10])}

Respond in JSON:
{{
    "sentiment": "bullish|bearish|neutral",
    "confidence": 0-100,
    "dominant_theme": "brief description",
    "risk_factors": ["factor1", "factor2"]
}}"""

            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-3.5-turbo",  # Cheaper for batch
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 200
            }
            
            async with session.post(self.base_url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    content = result['choices'][0]['message']['content']
                    try:
                        if "```" in content:
                            content = content.split("```")[1].split("```")[0]
                            if content.startswith("json"):
                                content = content[4:]
                        return json.loads(content.strip())
                    except:
                        pass
            
            return {"sentiment": "neutral", "confidence": 50}
            
        except Exception as e:
            logger.error(f"Market sentiment error: {e}")
            return {"sentiment": "neutral", "confidence": 50}
    
    def format_telegram_alert(self, analysis: GPT4Analysis) -> str:
        """Format analysis as Telegram message"""
        direction_emoji = {
            SignalDirection.STRONG_BULLISH: "🚀🚀",
            SignalDirection.BULLISH: "📈",
            SignalDirection.NEUTRAL: "➖",
            SignalDirection.BEARISH: "📉",
            SignalDirection.STRONG_BEARISH: "💥💥"
        }
        
        emoji = direction_emoji.get(analysis.direction, "❓")
        
        return f"""
🤖 <b>GPT-4 ANALYSIS</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪙 <b>Token:</b> #{analysis.symbol}
📰 <b>News:</b> {analysis.headline[:80]}...

<b>🎯 Direction:</b> {analysis.direction.value.upper()}
<b>📊 Confidence:</b> {analysis.confidence:.0f}%
<b>⚠️ Risk:</b> {analysis.risk_level}
<b>⏱️ Horizon:</b> {analysis.time_horizon}

<b>💡 Recommendation:</b>
{analysis.trading_recommendation}

<b>🇷🇺 Резюме:</b>
{analysis.summary_ru}
"""

    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()


# Convenience instance
gpt4_analyzer = GPT4NewsAnalyzer()

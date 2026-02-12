"""
MEXC Pump Monitor - Groq AI Analyzer
Ultra-fast analysis using Groq Cloud API (Llama-3)
"""

import asyncio
import aiohttp
import logging
import json
import random
from typing import Optional, Dict, List
from config import config

logger = logging.getLogger("GroqAnalyzer")

class GroqAnalyzer:
    """
    Groq-powered AI Analyzer
    Speeds: 200-300+ tokens per second
    Features: 
    - Economic event result analysis
    - Sentiment extraction
    - Key rotation for reliability
    """
    
    def __init__(self):
        self.api_keys = config.groq.api_keys
        self.base_url = config.groq.base_url
        self.model = config.groq.model
        self._session: Optional[aiohttp.ClientSession] = None
        self.enabled = len(self.api_keys) > 0
        
        # Key rotation
        self._key_index = 0
        
        if self.enabled:
            logger.info(f"🚀 Groq Analyzer initialized with {len(self.api_keys)} keys")
        else:
            logger.warning("⚠️ Groq disabled (no GROQ_API_KEY)")

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _get_next_key(self) -> str:
        """Rotate through API keys"""
        if not self.api_keys:
            return ""
        key = self.api_keys[self._key_index]
        self._key_index = (self._key_index + 1) % len(self.api_keys)
        return key

    async def analyze_economic_result(self, event_title: str, actual: str, forecast: str, previous: str, description: str = "") -> Optional[Dict]:
        """
        Analyze economic data release and give a trading verdict
        """
        if not self.enabled:
            return None
            
        prompt = f"""You are an elite quantitative macro-analyst at a global crypto hedge fund. Perform a SURGICALLY PRECISE analysis of this economic data release.

EVENT: {event_title}
ACTUAL: {actual}
FORECAST: {forecast}
PREVIOUS: {previous}
DESCRIPTION: {description}

STRICT ANALYSIS STEPS:
1. DELTA CALCULATION: Quantify the 'surprise' between Actual and Forecast.
2. MACRO LOGIC: Explain EXACTLY why this is Bullish/Bearish for BTC (e.g., "Weak NFP = Dovish Fed = Bullish Risk").
3. VOLATILITY PROJECTION: Estimate the immediate (5-15 min) BTC % move based on this delta size and historical correlation.

Respond in JSON format:
{{
    "verdict": "LONG|SHORT|NEUTRAL",
    "impact_severity": "HIGH|MEDIUM|LOW",
    "importance": "Rate 1-10 (precise scale)",
    "btc_move_projection": "BTC % expected move (e.g. +1.45% or -0.85%)",
    "delta_analysis": "Calculated delta and its mathematical significance",
    "summary": "1 sentence technical summary in Russian (NO generic words)",
    "key_points": [
        "Point 1: Exact numerical impact in Russian",
        "Point 2: Institutional sentiment outcome in Russian"
    ],
    "market_reaction_expected": "Precise BTC price action scenario in Russian"
}}

STRICT RULE: Avoid "volatility expected" or "could be". Use specific percentages and directional bias.
Be direct. Be precise. Be mathematical."""

        try:
            session = await self._get_session()
            headers = {
                "Authorization": f"Bearer {self._get_next_key()}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a professional financial analyst. Always respond with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }
            
            async with session.post(self.base_url + "/chat/completions", headers=headers, json=data) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Groq API Error ({response.status}): {text}")
                    return None
                    
                result = await response.json()
                content = result['choices'][0]['message']['content']
                return json.loads(content)
                
        except Exception as e:
            logger.error(f"Groq analysis failed: {e}")
            return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

# Global instance
groq_analyzer = GroqAnalyzer()

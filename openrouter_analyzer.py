import aiohttp
import asyncio
import logging
import os
import json
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger("OpenRouterAnalyzer")

class OpenRouterAnalyzer:
    """
    OpenRouter API Integration (Multi-model & Free fallback)
    - Supports Llama-3, Qwen, Mistral via OpenRouter
    - API Key rotation
    - Fallback for Groq when rate limits hit
    """
    
    def __init__(self, api_keys: Optional[List[str]] = None):
        # Use config if available, otherwise fallback to env
        try:
            from config import config
            raw_key = config.openrouter.api_key if config.openrouter.api_key else os.getenv('OPENROUTER_API_KEY', '')
            self.api_keys = api_keys or raw_key.split(',')
        except Exception as e:
            logger.debug(f"Config import failed in analyzer: {e}")
            self.api_keys = api_keys or os.getenv('OPENROUTER_API_KEY', '').split(',')
            
        # Paranoia cleaning: remove spaces, newlines, and quotes
        self.api_keys = [k.strip().strip("'").strip('"') for k in self.api_keys if k.strip()]
        self.current_key_index = 0
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        # Smart Tiering: High-performance free models
        self.top_models = [
            "meta-llama/llama-3.3-70b-instruct:free",
            "meta-llama/llama-3.1-70b-instruct:free"
        ]
        
        # Regular pool: Stable backup models
        self.regular_models = [
            "meta-llama/llama-3.1-8b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "openrouter/free"
        ]
        
        self.session = None
        self.enabled = len(self.api_keys) > 0
        if self.enabled:
            logger.info(f"🚀 OpenRouter Analyzer initialized with {len(self.api_keys)} keys (Session-optimized)")
        else:
            logger.warning("⚠️ OpenRouter disabled (no OPENROUTER_API_KEY)")

    def _get_current_key(self) -> str:
        if not self.api_keys:
            return ""
        return self.api_keys[self.current_key_index]

    def _rotate_key(self):
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"🔄 Rotated to OpenRouter API key #{self.current_key_index}")

    async def analyze_event_result(self, event_data: Dict[str, Any], actual_data: str, high_impact: bool = False) -> Optional[Dict[str, Any]]:
        """Analyze economic event outcome with tier selection and global fallback"""
        if not self.enabled:
            return None

        event_title = event_data.get('title', 'Unknown Event')
        forecast = event_data.get('forecast', 'N/A')
        actual = actual_data
        
        prompt = f"""
Analyze this economic event outcome and provide a high-precision trading verdict for BTC/Crypto.
EVENT: {event_title}
ACTUAL: {actual}
FORECAST: {forecast}
IMPORTANCE: {event_data.get('impact', 'MEDIUM')}

STRICT RULE: The 'reason' field MUST be in PROFESSIONAL RUSSIAN (РУССКИЙ ЯЗЫК). 
Return ONLY a JSON object:
{{
  "verdict": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": 0-100,
  "reason": "Technical macro analysis in Russian",
  "projected_move": "Expected move size in %",
  "importance_score": 1-10
}}
"""
        system_prompt = "You are a professional crypto analyst at a hedge fund. You always respond in Russian and valid JSON."
        
        # 1. Try preferred models first
        preferred = self.top_models if high_impact else self.regular_models
        for model in preferred:
            result = await self._make_request(prompt, model, system_prompt)
            if result: return result
            
        # 2. Global fallback to EVERYTHING else if preferred failed
        all_others = self.regular_models if high_impact else self.top_models
        for model in all_others:
            result = await self._make_request(prompt, model, system_prompt)
            if result: return result
            
        return None

    async def analyze_news(self, title: str, summary: str, tokens: List[str], high_impact: bool = False) -> Optional[Dict]:
        """Analyze news item with tier selection and global fallback"""
        if not self.enabled:
            return None
            
        prompt = f"""Analyze this crypto news for sentiment and importance:
TITLE: {title}
SUMMARY: {summary}
TOKENS: {', '.join(tokens) if tokens else 'None'}

Return ONLY a JSON:
{{
  "importance": 0-100,
  "sentiment": "very_bullish|bullish|neutral|bearish|very_bearish",
  "score": -1.0 to 1.0,
  "is_fake": boolean,
  "is_crypto_relevant": boolean,
  "is_actionable": boolean,
  "reliability": 0-100,
  "category": "listing|hack|regulation|partnership|whale|rumor|other",
  "signal": "LONG|SHORT|NEUTRAL",
  "ru_title": "Clean, natural Russian translation of the headline"
}}
STRICT RULE: 'ru_title' MUST be in high-quality financial Russian.
"""
        system_prompt = "You are an expert crypto news analyst. Respond in valid JSON."
        
        # 1. Try preferred tier
        preferred = self.top_models if high_impact else self.regular_models
        for model in preferred:
            result = await self._make_request(prompt, model, system_prompt)
            if result: return result
            
        # 2. Global fallback to the other tier
        all_others = self.regular_models if high_impact else self.top_models
        for model in all_others:
            result = await self._make_request(prompt, model, system_prompt)
            if result: return result
            
        return None

    async def _make_request(self, prompt: str, model: str, system_prompt: str = "Financial analyst") -> Optional[Dict]:
        """Make request to OpenRouter with retries and session reuse"""
        if not self.session or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
            
        headers = {
            "Authorization": f"Bearer {self._get_current_key()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/qazqwerty617/OS",
            "X-Title": "MEXC Pump Monitor"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }

        try:
            logger.debug(f"📡 Sending OpenRouter request to {model}...")
            async with self.session.post(self.base_url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'choices' not in data or not data['choices']:
                        logger.error(f"❌ OpenRouter empty response for {model}: {data}")
                        return None
                        
                    content = data['choices'][0]['message']['content'].strip()
                    logger.info(f"✅ OpenRouter Success [{model}]: {content[:50]}...")
                    
                    # Flexible JSON extraction
                    try:
                        return json.loads(content)
                    except:
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()
                        return json.loads(content)
                        
                elif resp.status == 429:
                    logger.warning(f"⚠️ OpenRouter Rate Limit for {model}")
                    self._rotate_key()
                elif resp.status == 401:
                    logger.error(f"❌ Invalid OpenRouter API Key")
                    self._rotate_key()
                elif resp.status == 404:
                    logger.error(f"❌ OpenRouter 404: Model {model} not found/available. Skipping.")
                else:
                    error_text = await resp.text()
                    logger.error(f"❌ OpenRouter API Error {resp.status} for {model}: {error_text[:100]}")
        except Exception as e:
            logger.error(f"💥 OpenRouter Fatal error ({model}): {str(e)[:100]}")
            
        return None

    async def close(self):
        """Cleanup session on shutdown"""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug("OpenRouter session closed")

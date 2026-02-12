import asyncio
import logging
import json
from unittest.mock import MagicMock, AsyncMock, patch
from news_bot import NewsBot, NewsSource, NewsItem
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestFallback")

async def test_fast_fallback():
    """Тест мгновенного переключения на OpenRouter при 429 от Groq"""
    print("\n🧪 Тестирование мгновенного фоллбека...")
    
    # Mock OpenRouter
    mock_or = MagicMock()
    mock_or.analyze_news = AsyncMock(return_value={"importance": 85, "sentiment": "bullish", "ru_title": "Тест фоллбека"})
    
    bot = NewsBot(openrouter=mock_or)
    
    # Эмулируем 429 от Groq
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.__aenter__.return_value = mock_resp
    
    with patch('aiohttp.ClientSession.post', return_value=mock_resp):
        result = await bot._analyze_with_groq("Test Title", "Test Summary", ["BTC"])
        
    if result and result.get('ru_title') == "Тест фоллбека":
        print("✅ Успех: Система переключилась на OpenRouter при ошибке 429")
    else:
        print("❌ Ошибка: Фоллбек не сработал")

async def test_translation_fallback():
    """Тест резервного перевода через OpenRouter"""
    print("\n🧪 Тестирование резервного перевода...")
    
    mock_or = MagicMock()
    # Эмулируем ответ от OpenRouterAnalyzer._make_request
    mock_or._make_request = AsyncMock(return_value={"choices": [{"message": {"content": "Переведенный заголовок"}}]})
    
    bot = NewsBot(openrouter=mock_or)
    
    # Эмулируем 429 от Groq для перевода
    mock_resp = AsyncMock()
    mock_resp.status = 429
    mock_resp.__aenter__.return_value = mock_resp
    
    with patch('aiohttp.ClientSession.post', return_value=mock_resp):
        translation = await bot._translate_text("Original Title")
        
    if translation == "Переведенный заголовок":
        print("✅ Успех: Резервный перевод через OpenRouter работает")
    else:
        print(f"❌ Ошибка: Перевод не сработал (получено: {translation})")

if __name__ == "__main__":
    asyncio.run(test_fast_fallback())
    asyncio.run(test_translation_fallback())

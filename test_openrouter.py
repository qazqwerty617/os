import asyncio
import os
import logging
import json
import aiohttp
from openrouter_analyzer import OpenRouterAnalyzer
from dotenv import load_dotenv

# Настройка логов для теста
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("TestOpenRouter")

async def test_direct_api():
    from config import config
    api_key = config.openrouter.api_key.split(',')[0].strip().strip("'").strip('"')
    logger.info(f"🔑 Тестируем первый ключ (длина {len(api_key)}): {api_key[:10]}...{api_key[-5:]}")
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": "Say hello"}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=10) as resp:
                status = resp.status
                text = await resp.text()
                logger.info(f"📡 Статус API: {status}")
                if status == 200:
                    logger.info("✅ Прямое соединение успешно!")
                else:
                    logger.error(f"❌ Ошибка API: {text}")
    except Exception as e:
        logger.error(f"💥 Ошибка сети: {e}")

async def test_analyzer():
    load_dotenv()
    analyzer = OpenRouterAnalyzer()
    
    if not analyzer.enabled:
        logger.error("❌ OpenRouter не включен!")
        return

    logger.info("🧪 Тестируем анализатор через NewsBot logic...")
    
    # Пытаемся проанализировать тестовый заголовок
    result = await analyzer.analyze_news(
        "Binance adds new pair BTC/TRY", 
        "Binance adds BTC/TRY spot trading pair to its platform.",
        ["BTC"],
        high_impact=True # Чтобы использовал TOP MODELS
    )
    
    if result:
        logger.info("✅ Анализатор вернул результат!")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        logger.error("❌ Анализатор вернул None. Проверь логи выше (DEBUG включен).")

if __name__ == "__main__":
    print("\n--- ЭТАП 1: ПРЯМОЙ ЗАПРОС ---")
    asyncio.run(test_direct_api())
    print("\n--- ЭТАП 2: ЧЕРЕЗ АНАЛИЗАТОР ---")
    asyncio.run(test_analyzer())

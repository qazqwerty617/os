import asyncio
import os
import logging
from openrouter_analyzer import OpenRouterAnalyzer
from dotenv import load_dotenv

# Инициализация логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("TestOpenRouter")

async def test_openrouter():
    # Загружаем .env
    load_dotenv()
    
    logger.info("🧪 Запуск теста OpenRouter...")
    
    # Инициализация анализатора
    analyzer = OpenRouterAnalyzer()
    
    if not analyzer.enabled:
        logger.error("❌ OpenRouter не включен! Проверь OPENROUTER_API_KEY в .env")
        return

    # Тестовые данные (имитируем CPI)
    event_data = {
        'title': 'US CPI (YoY)',
        'impact': 'CRITICAL',
        'forecast': '2.9%'
    }
    actual_data = '3.2%'

    logger.info(f"📡 Отправка запроса к OpenRouter (модель: {analyzer.models[0]})...")
    
    start_time = asyncio.get_event_loop().time()
    result = await analyzer.analyze_event_result(event_data, actual_data)
    end_time = asyncio.get_event_loop().time()

    if result:
        logger.info("✅ УСПЕХ! Ответ от OpenRouter получен:")
        print(f"\nВердикт: {result.get('verdict')}")
        print(f"Причина: {result.get('reason')}")
        print(f"Уверенность: {result.get('confidence')}%")
        print(f"Время ответа: {end_time - start_time:.2f} сек")
    else:
        logger.error("❌ Тест провален. Ответ не получен или пришел с ошибкой.")

if __name__ == "__main__":
    asyncio.run(test_openrouter())

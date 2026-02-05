import asyncio
import os
import sys

# Добавляем текущую директорию в путь, чтобы импорты работали
sys.path.append(os.getcwd())

async def run_test():
    print("🚀 МОНИТОР: Запуск теста Gemini 2.0 Flash...")
    print("-" * 40)
    
    from news_bot import NewsBot
    from config import config
    
    bot = NewsBot()
    
    # 1. Проверка конфигурации
    if not config.openrouter.api_key:
        print("❌ ОШИБКА: OPENROUTER_API_KEY не найден в .env!")
        return
    
    print(f"✅ Конфиг загружен. Модель: {config.openrouter.model}")
    print(f"🔑 Ключ (первые 10 символов): {config.openrouter.api_key[:10]}...")
    
    # 2. Тестовые сценарии
    test_cases = [
        {
            "title": "Binance Lists New Meme Coin PEPE 3.0",
            "summary": "The world's largest exchange announced the listing of PEPE 3.0 with zero fees.",
            "tokens": ["PEPE"]
        },
        {
            "title": "Major DeFi Bridge Hacked for $50M",
            "summary": "A critical vulnerability was exploited in the cross-chain protocol.",
            "tokens": ["ETH", "SOL"]
        }
    ]
    
    print("\n🔍 Начинаю анализ через AI...")
    
    for case in test_cases:
        print(f"\n📝 Новость: {case['title']}")
        print("⚡ Отправка запроса в OpenRouter (Gemini 2.0 Flash)...")
        
        try:
            # Вызываем основной метод анализа бота
            result = await bot._analyze_with_openrouter(case['title'], case['summary'], case['tokens'])
            
            if result:
                print("✅ ОТВЕТ ПОЛУЧЕН:")
                print(f"   📊 Важность: {result.get('importance')}/100")
                print(f"   📈 Сентимент: {result.get('sentiment')}")
                print(f"   🇷🇺 Перевод: {result.get('ru_title')}")
            else:
                print("⚠️ AI не вернул результат (проверьте логи).")
                
        except Exception as e:
            print(f"❌ ОШИБКА при запросе: {e}")

    print("\n" + "-" * 40)
    print("🏁 Тест завершен.")

if __name__ == "__main__":
    asyncio.run(run_test())

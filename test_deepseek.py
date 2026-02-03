
import asyncio
import os
from news_bot import NewsBot, NewsSentiment
from config import config

# Mock settings for testing logic flow
config.deepseek.api_key = "sk-test-mock"

# Mock the _analyze_with_deepseek method to avoid real API call failure in test env
# (unless we actually had a key)
async def mock_deepseek(self, title, summary, tokens):
    print(f"🤖 DeepSeek Analysing: {title[:30]}...")
    if "HACK" in title:
        return {
            "importance": 95,
            "sentiment": "very_bearish",
            "score": -0.9,
            "ru_title": "ГЛАВНЫЙ ВЗЛОМ: 100М украдено"
        }
    return None

async def test_logic():
    bot = NewsBot()
    # Monkey patch for testing flow
    bot._analyze_with_deepseek = lambda t, s, k: mock_deepseek(bot, t, s, k)
    
    examples = [
        "MAJOR HACK: 100M stolen from Bridge", 
        "Someone said something about bitcoin price"
    ]
    
    print("🤖 TESTING DEEPSEEK INTEGRATION 🤖")
    print("-" * 50)
    
    for title in examples:
        print(f"\nTitle: {title}")
        
        # Simulate the logic block from _parse_rss
        # 1. Noise check
        if bot._is_noise(title):
            print("❌ Result: FILTERED (Noise Rule)")
            continue
            
        # 2. DeepSeek logic
        print("⚡ Sending to AI...")
        analysis = await bot._analyze_with_deepseek(title, "", [])
        
        if analysis:
            print(f"✅ AI Result: {analysis}")
            print(f"🇷🇺 Translated: {analysis['ru_title']}")
        else:
             print("⚠️ AI Skipped (or Failed)")

if __name__ == "__main__":
    asyncio.run(test_logic())

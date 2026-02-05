"""
Test News Parser
"""
import asyncio
import os
from pathlib import Path

# Load .env
env_path = Path('.env')
if env_path.exists():
    for line in env_path.read_text().split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip()

async def test_news():
    from news_bot import NewsBot
    
    print("🔑 API Keys Status:")
    print(f"  CryptoPanic: {'✅ SET' if os.getenv('CRYPTOPANIC_API_KEY') else '❌ NOT SET'}")
    print(f"  Groq AI: {'✅ SET' if os.getenv('GROQ_API_KEY') else '❌ NOT SET'}")
    print()
    
    print("📰 Starting News Bot...")
    bot = NewsBot()
    
    # Fetch news
    print("🔍 Fetching news from all sources...")
    await bot._fetch_all_sources()
    
    print(f"\n✅ Total news fetched: {len(bot.news)}")
    print(f"📊 Stats: {bot.stats}")
    
    # Show recent news
    if bot.news:
        print("\n📋 Recent News (last 5):")
        for news in bot.news[-5:]:
            tokens = ', '.join(news.mentioned_tokens) if news.mentioned_tokens else 'N/A'
            print(f"  • {news.title}")
            print(f"    Tokens: {tokens} | Importance: {news.importance}/100")
            print()

if __name__ == "__main__":
    asyncio.run(test_news())

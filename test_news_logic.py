
import asyncio
from news_bot import NewsBot, NewsSentiment

async def test_logic():
    bot = NewsBot()
    
    # Test Cases ( Real examples from user complaint )
    examples = [
        "Bitcoin borrowing shifts from short-term liquidity to long-term planning: Xapo",
        "Bitcoin ETFs bounce $562M after $1.5B sell-off, as headwinds linger",
        "Spot crypto volumes plunge to 2024 lows amid investor demand weakens",
        "MAJOR HACK: 100M stolen from Bridge",
        "Binance Listing: New token SUI available now",
        "Price Analysis: Bitcoin could reach 100k soon",
    ]
    
    print("📰 TESTING NEWS LOGIC 📰")
    print("-" * 50)
    
    for title in examples:
        print(f"\nTitle: {title}")
        
        # 1. Noise Check
        is_noise = bot._is_noise(title)
        if is_noise:
            print("❌ Result: NOISE (Filtered)")
            continue
            
        # 2. Extract Token logic check
        tokens = bot._extract_tokens(title)
        
        # 3. Sentiment (Mock)
        sentiment = NewsSentiment.NEUTRAL
        if "hack" in title.lower(): sentiment = NewsSentiment.VERY_BEARISH
        if "listing" in title.lower(): sentiment = NewsSentiment.VERY_BULLISH
        
        # 4. Importance
        score = bot._calculate_importance(title, tokens, sentiment)
        
        if score >= 80:
             print(f"🔄 Translating...")
             try:
                 ru = await bot._translate_text(title)
                 print(f"🇷🇺 RU: {ru}")
             except:
                 print("⚠️ Translation failed")

if __name__ == "__main__":
    asyncio.run(test_logic())

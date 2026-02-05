import asyncio
import logging
from mexc_client import MEXCClient
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Diagnostic")

async def run_diagnostic():
    client = MEXCClient()
    print("🔍 Starting MEXC Client...")
    await client.start()
    
    symbols = client.get_active_symbols()
    print(f"✅ Active symbols loaded: {len(symbols)}")
    
    if len(symbols) == 0:
        print("❌ ERROR: No symbols loaded. Check for 403/Forbidden or API issues.")
        await client.stop()
        return

    print("📡 Fetching tickers...")
    tickers = await client.get_tickers()
    print(f"✅ Tickers fetched: {len(tickers)}")
    
    if len(tickers) == 0:
        print("❌ ERROR: No tickers fetched. Check API connectivity.")
    else:
        # Show top 5 tickers by volume
        top_tickers = sorted(tickers, key=lambda x: x.volume_24h, reverse=True)[:5]
        print("\nTop 5 Tickers by 24h Volume:")
        for t in top_tickers:
            print(f" - {t.symbol}: Price={t.price}, Vol24h={t.volume_24h}")

    print("\n🔬 Testing Kline Fetch for BTC_USDT...")
    klines = await client.get_klines("BTC_USDT", "Min1", 5)
    print(f"✅ Klines fetched for BTC_USDT: {len(klines)}")
    
    await client.stop()
    print("\n🏁 Diagnostic Complete.")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())

import asyncio
import time
import logging
from mexc_client import MEXCClient

async def check_env():
    client = MEXCClient()
    await client.start()
    
    # Check Time
    local_ms = int(time.time() * 1000)
    tickers = await client.get_tickers()
    if tickers:
        mexc_ms = tickers[0].timestamp
        diff = local_ms - mexc_ms
        print(f"⏰ Time Check:")
        print(f"   Local Name: {time.ctime()}")
        print(f"   Local MS: {local_ms}")
        print(f"   MEXC MS:  {mexc_ms}")
        print(f"   Diff:     {diff} ms ({diff/1000:.2f} s)")
        if abs(diff) > 300000: # 5 minutes
            print("❌ WARNING: Time drift is > 5 minutes!")
    
    # Check Top Gainers
    print("\n📈 Top 10 Gainers (24h):")
    gainers = sorted(tickers, key=lambda x: x.change_24h_pct, reverse=True)[:10]
    for g in gainers:
        print(f" - {g.symbol}: {g.change_24h_pct:+.2f}% | Vol: ${g.volume_24h * g.price:,.0f}")
        
    await client.stop()

if __name__ == "__main__":
    asyncio.run(check_env())

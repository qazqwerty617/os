import aiohttp
import asyncio
import ssl
import time

async def test():
    # Trying exact example from docs (modified for current date)
    # GET https://contract.mexc.com/api/v1/contract/kline/BTC_USDT?interval=Min15&start=...&end=...
    
    symbol = "BTC_USDT"
    base_url = f"https://contract.mexc.com/api/v1/contract/kline/{symbol}" # Note: symbol in path!
    
    end = int(time.time())
    start = end - 3600 * 24 # 1 day ago
    
    params = {
        'interval': 'Min60', 
        'start': start,
        'end': end
    }
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
    }

    print(f"Testing URL: {base_url}")
    print(f"Params: {params}")

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_context)) as session:
        async with session.get(base_url, params=params, headers=headers) as resp:
            print(f"Status: {resp.status}")
            text = await resp.text()
            print(f"Body: {text[:200]}")

asyncio.run(test())

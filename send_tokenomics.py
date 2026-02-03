"""Send Tokenomics Signal"""
import asyncio
from telegram_bot import TelegramNotifier

async def send():
    tg = TelegramNotifier()
    
    msg = """📊📊📊 <b>TOKENOMICS ANALYSIS</b> 📊📊📊

🪙 <b>NEWCOIN_USDT</b>

📈 <b>Supply Info:</b>
├ Total Supply: 1,000,000,000
├ Circulating: 250,000,000 (25%)
├ Max Supply: 1,000,000,000
└ Inflation: 2% yearly

🔒 <b>Token Distribution:</b>
├ Team: 15% (locked 2 years)
├ Investors: 20% (vesting 1 year)
├ Community: 40%
├ Treasury: 15%
└ Liquidity: 10%

⏰ <b>Unlock Schedule:</b>
├ Next unlock: 2026-03-01
├ Amount: 50M tokens (5%)
└ ⚠️ POTENTIAL DUMP RISK

💰 <b>Market Cap:</b>
├ Current: $12.5M
├ FDV: $50M
└ MC/FDV Ratio: 0.25

🎯 <b>Risk Assessment:</b>
├ Unlock Risk: 🔴 HIGH
├ Whale Concentration: 🟡 MEDIUM
└ Liquidity: 🟢 GOOD

⚡ Overall: <b>CAUTIOUS</b>"""
    
    result = await tg.send_message(msg)
    print(f"Tokenomics sent: {result}")
    
    if tg._session:
        await tg._session.close()

asyncio.run(send())

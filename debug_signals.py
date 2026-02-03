"""
Debug Signals Script - No external deps
"""
import asyncio
import os
import sys

# Add project to path
sys.path.insert(0, '/Users/qazqwerty617/Downloads/OS')

from telegram_bot import TelegramNotifier

async def send_all_signals():
    print("=== SENDING TEST SIGNALS ===")
    
    tg = TelegramNotifier()
    print(f"Telegram enabled: {tg.enabled}")
    print(f"Chat ID: {tg.chat_id}")
    
    if not tg.enabled:
        print("ERROR: Telegram not enabled!")
        return
    
    signals = [
        "🔥🔥🔥 <b>PUMP DETECTED</b> 🔥🔥🔥\n\n📊 <b>TEST_USDT</b>\n💰 Цена: $0.054 → $0.068\n📈 Изменение: <b>+24.96%</b>\n⚡ Quality: <b>A-TIER</b>",
        
        "🔴🔴🔴 <b>SHORT SIGNAL</b> 🔴🔴🔴\n\n📊 <b>HYPE_USDT</b>\n📉 RSI: 82 (перекуплен!)\n🐋 Whale Pressure: 72%\n⚡ Quality: <b>S-TIER</b>",
        
        "🐋🐋🐋 <b>WHALE ALERT</b> 🐋🐋🐋\n\n📊 <b>BTC_USDT</b>\n📉 Size: <b>$2.5M SELL</b>\n⚠️ Possible dump incoming",
        
        "🆕🆕🆕 <b>NEW LISTING</b> 🆕🆕🆕\n\n📊 <b>NEWCOIN_USDT</b>\n💰 Initial: $0.0012\n📊 Leverage: 50x\n⚡ HIGH VOLATILITY!",
        
        "🔒 <b>BREAKEVEN ACTIVATED</b>\n\n📊 <b>ETH_USDT</b>\n✅ Position now RISK-FREE!",
        
        "💰💰💰 <b>TAKE PROFIT HIT!</b> 💰💰💰\n\n📊 <b>SOL_USDT</b>\n📈 Profit: <b>+9.95%</b>\n🎉 Great trade!",
        
        "🔴 <b>STOP LOSS HIT</b>\n\n📊 <b>DOGE_USDT</b>\n📉 Loss: <b>-5.7%</b>",
        
        "🏥 <b>HEALTH REPORT</b>\n\n🟢 Status: HEALTHY\n📊 Modules: 48 OK\n💻 CPU: 12.5%",
        
        "🎯 <b>SNIPER READY!</b>\n\n📊 <b>PEPE_USDT</b>\n🔫 Target: NEW_LISTING\n⏰ Waiting...",
        
        "📊 <b>DAILY SUMMARY</b>\n\n✅ Signals: 12\n📈 Win Rate: 75%\n💰 P/L: +$156.50"
    ]
    
    for i, sig in enumerate(signals, 1):
        print(f"Sending {i}/10...")
        result = await tg.send_message(sig)
        print(f"  Result: {result}")
        await asyncio.sleep(0.5)
    
    print("\n✅ ALL 10 SIGNALS SENT!")
    
    if tg._session:
        await tg._session.close()

if __name__ == "__main__":
    asyncio.run(send_all_signals())

import asyncio
import logging
import time
from pump_detector import PumpDetector
from mexc_client import Ticker
from config import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("Simulation")

class MockClient:
    def __init__(self):
        self.symbols = ["SIM_USDT"]
        self.tickers = {
            "SIM_USDT": Ticker("SIM_USDT", 1.0, 1000.0, 0.0, 1.0, 1.0, int(time.time() * 1000))
        }
    def get_active_symbols(self): return self.symbols
    async def get_klines(self, symbol, interval, limit): return []
    async def get_tickers(self): return list(self.tickers.values())

async def run_simulation():
    client = MockClient()
    detector = PumpDetector(client)
    
    # 1. VERY LIMITED HISTORY (Only 2 points)
    print("🧪 Populating minimal history for SIM_USDT (2 minutes)...")
    now_ms = int(time.time() * 1000)
    history = detector.history["SIM_USDT"]
    
    # Add only 1 point before now
    history.add(1.0, 10.0, now_ms - 60000)
    
    # 2. Add PUMP at 'now' with NO VOLUME increase
    print("🚀 Simulating 5% price spike with ZERO volume increase...")
    pump_price = 1.05
    pump_vol_rate = 10.0 # Same as before
    history.add(pump_price, pump_vol_rate, now_ms)
    
    # 3. Use standard config (not aggressive) to see if hardcoded filters are gone
    config.pump.min_price_change_pct = 1.0
    config.pump.min_volume_multiplier = 2.0 # This would normally block it
    config.pump.rsi_overbought = 70.0 # RSI won't even be 70 here
    config.scoring.min_score_threshold = 50 # This would also block it
    
    # Register callback
    signal_caught = asyncio.Event()
    async def on_signal(sig):
        print(f"✅ SIGNAL DETECTED: {sig.symbol} @ {sig.price} (Score: {sig.score})")
        signal_caught.set()
    
    detector.on_signal(on_signal)
    
    print(f"🔍 History length: {len(history.prices)}")
    print(f"🔍 Price change: {history.get_price_change(5):.2f}%")
    
    await detector._check_pump("SIM_USDT", current_vol_rate=pump_vol_rate)
    
    try:
        await asyncio.wait_for(signal_caught.wait(), timeout=5)
        print("🎉 SUCCESS: Pure price detection is working regardless of technical filters!")
    except asyncio.TimeoutError:
        print("❌ FAILED: Signal was blocked by a filter.")

if __name__ == "__main__":
    asyncio.run(run_simulation())

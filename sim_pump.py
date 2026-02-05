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
            "SIM_USDT": Ticker("SIM_USDT", 1.0, 100000.0, 0.0, 1.0, 1.0, int(time.time() * 1000))
        }
    def get_active_symbols(self): return self.symbols
    async def get_klines(self, symbol, interval, limit): return []
    async def get_tickers(self): return list(self.tickers.values())

async def run_simulation():
    client = MockClient()
    detector = PumpDetector(client)
    
    # 1. Populate history with realistic timestamps
    print("🧪 Populating fake history for SIM_USDT...")
    now_ms = int(time.time() * 1000)
    history = detector.history["SIM_USDT"]
    base_price = 1.0
    
    # Add 40 minutes of data ending just before 'now'
    for i in range(40):
        # 1 minute apart
        ts = now_ms - (40 - i) * 60000
        history.add(base_price, 10000.0, ts)
    
    # 2. Add a PUMP at 'now'
    print("🚀 Simulating 5% price spike and 5x volume spike...")
    pump_price = base_price * 1.05
    pump_vol_rate = 50000.0 # 5x of 10000
    history.add(pump_price, pump_vol_rate, now_ms)
    
    # 3. Configure aggressive thresholds
    config.pump.min_price_change_pct = 1.0
    config.pump.min_volume_multiplier = 1.1
    config.pump.rsi_overbought = 40.0 
    config.scoring.min_score_threshold = 10
    config.filters.min_daily_volume_usd = 1000 # Make sure we pass volume filter
    
    # Register callback
    signal_caught = asyncio.Event()
    async def on_signal(sig):
        print(f"✅ SIGNAL DETECTED: {sig.symbol} @ {sig.price} (Score: {sig.score})")
        print(f"   Breakdown: {sig.score_breakdown}")
        signal_caught.set()
    
    detector.on_signal(on_signal)
    
    # 4. Trigger check
    print(f"🔍 Current history length: {len(history.prices)}")
    print(f"🔍 Price change (5m): {history.get_price_change(5):.2f}%")
    
    await detector._check_pump("SIM_USDT", current_vol_rate=pump_vol_rate)
    
    try:
        await asyncio.wait_for(signal_caught.wait(), timeout=5)
        print("🎉 Simulation Successful: Signal was generated!")
    except asyncio.TimeoutError:
        print("❌ Simulation Failed: Still no signal generated.")
        # Debugging Indicators
        from indicators import calculate_all_indicators
        ind = calculate_all_indicators(history.prices, history.volumes, pump_vol_rate)
        print(f"📊 Indicators: RSI={ind.rsi}, VolRatio={ind.volume_ratio}, Ext={ind.ema_extension_pct}")

if __name__ == "__main__":
    asyncio.run(run_simulation())

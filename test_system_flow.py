
import asyncio
from risk_manager import RiskManager, RiskLevel
from profit_maximizer import ProfitMaximizer

# Mock Classes
class MockClient:
    async def get_balance(self): return {'equity': 10000}
    
class MockRiskManager(RiskManager):
    pass

async def test_full_system_flow():
    print("🚀 TESTING FULL SYSTEM UPGRADE (AI -> RISK -> EXECUTION)")
    print("-" * 60)
    
    # Init
    risk_manager = RiskManager(capital=10000, risk_level=RiskLevel.AGGRESSIVE)
    client = MockClient()
    optimizer = ProfitMaximizer(client, risk_manager)
    optimizer.is_enabled = True # FORCE ENABLE FOR TEST
    await optimizer.start()
    
    # TEST 1: Standard Trade (Low Confidence)
    print("\n[SCENARIO 1] Standard Signal (Score 60)")
    signal_low = {
        'symbol': 'BTCUSDT',
        'entry_price': 50000,
        'stop_loss': 49000, # 2% risk
        'final_score': 60,
        'news_score': 0
    }
    await optimizer.execute_signal(signal_low)
    trade_low = optimizer.active_trades.get('BTCUSDT')
    print(f"Size: ${trade_low.size_usd:.0f} | Lev: {trade_low.leverage}x")
    
    # TEST 2: AI Hyper-Trade (High Confidence + Strong News)
    print("\n[SCENARIO 2] 🚀 MOONBAG Signal (Score 95 + News 90)")
    signal_high = {
        'symbol': 'PEPEUSDT',
        'entry_price': 0.0001,
        'stop_loss': 0.000095,
        'final_score': 95, # AI LOVES THIS
        'news_score': 90   # BINANCE LISTING
    }
    await optimizer.execute_signal(signal_high)
    trade_high = optimizer.active_trades.get('PEPEUSDT')
    
    print(f"Size: ${trade_high.size_usd:.0f} | Lev: {trade_high.leverage}x")
    print(f"TP1: {trade_high.take_profit_1} (Expect Boosted)")
    print(f"TP2: {trade_high.take_profit_2} (Expect Moonbag)")
    
    # VALIDATION
    if trade_high.size_usd > trade_low.size_usd * 1.5:
        print("✅ PASS: Position Size scaled up for High Confidence")
    else:
        print("❌ FAIL: Size did not scale")
        
    if trade_high.take_profit_2 > trade_high.entry_price * 1.05: # > 5% gain
        print("✅ PASS: Targets boosted for Moonbag Mode")
    else:
        print("❌ FAIL: Targets not boosted")

if __name__ == "__main__":
    asyncio.run(test_full_system_flow())

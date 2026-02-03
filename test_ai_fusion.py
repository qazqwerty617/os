
import asyncio
from ai_predictor import AIPumpPredictor, PumpPrediction

def test_hyper_optimization():
    print("🧠 TESTING HYPER-OPTIMIZED AI")
    print("-" * 50)
    
    ai = AIPumpPredictor()
    
    # 1. Test News Fusion Impact
    # Scenario: Weak Technicals but STRONG News
    print("\n[TEST 1] AI Fusion (News + Technicals)")
    prediction = ai.predict(
        symbol="BTCUSDT",
        current_price=100.0,
        current_volume=1000.0,
        rsi=50, # Neutral
        volume_ratio=1.2, # Weak
        news_score=90, # 🚀 STRONG NEWS
        news_sentiment=0.8
    )
    
    print(f"Scenario: Weak Tech + Strong News (90)")
    print(f"AI Pump Probability: {prediction.pump_probability:.1f}%")
    if prediction.pump_probability > 80:
        print("✅ PASS: Fusion boosted probability correctly")
    else:
        print("❌ FAIL: News did not boost score enough")

    # 2. Test Dynamic Learning
    print("\n[TEST 2] Dynamic Weight Adjustment")
    initial_weight = ai.factor_weights['news_sentiment']
    print(f"Initial News Weight: {initial_weight}")
    
    # Simulate a correct prediction largely driven by news
    # We tell the AI: "You predicted PUMP with Strong News, and it went up +15%"
    ai.record_outcome(
        symbol="BTCUSDT",
        prediction=prediction,
        actual_change_pct=15.0 # Correct!
    )
    
    new_weight = ai.factor_weights['news_sentiment']
    print(f"New News Weight: {new_weight}")
    
    if new_weight > initial_weight:
        print("✅ PASS: AI learned and increased weight")
    else:
        print("❌ FAIL: Weight did not increase")

if __name__ == "__main__":
    test_hyper_optimization()

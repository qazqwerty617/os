
from local_model import local_brain

def test_signals():
    print("🎯 TESTING LOCAL SIGNALS (Direction + Coin)")
    print("-" * 50)
    
    test_cases = [
        # Bullish
        ("Binance Listing: New token SUI available", "LONG"),
        ("Coinbase roadmap adds PEPE support", "LONG"),
        ("Blackrock Spot ETF Approved", "LONG"),
        ("Mainnet Upgrade Successful v2", "LONG"),
        
        # Bearish
        ("MAJOR HACK: 100M stolen from Bridge", "SHORT"),
        ("SEC sues Binance for fraud", "SHORT"),
        ("Rug pull detected: Developer removed liquidity", "SHORT"),
        ("Delisting: TOKEN removed from exchange", "SHORT"),
        
        # Neutral/Noise
        ("Bitcoin price analysis for today", "NEUTRAL"),
    ]
    
    score = 0
    for text, expected in test_cases:
        direction, conf = local_brain.predict_direction(text)
        
        # Mock token extraction for display
        tokens = [w for w in text.split() if w.isupper() and len(w) > 2]
        token = tokens[0] if tokens else "MARKET"
        
        result = "✅" if direction == expected else "❌"
        if direction == expected: score += 1
        
        print(f"Text: {text[:40]}...")
        print(f"Expect: {expected} | Got: {direction} ({conf:.1f}%) -> {result}")
        if direction != "NEUTRAL":
            print(f"🚀 SIGNAL: {direction} {token}")
        print("-" * 20)
        
    print(f"Accuracy: {score}/{len(test_cases)}")

if __name__ == "__main__":
    test_signals()

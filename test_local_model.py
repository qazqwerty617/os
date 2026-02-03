
from local_model import local_brain

def test_local_brain():
    print("🧠 TESTING LOCAL BRAIN (Naive Bayes V2 - Bigrams)")
    print("-" * 50)
    
    test_cases = [
        # Noise
        ("Price Analysis: Bitcoin could hit 100k", "noise"),
        ("Top 5 cryptos to watch for 2025", "noise"),
        ("Analyst predicts massive surge for SHIB", "noise"),
        ("Ethereum borrowing rates shift slightly", "noise"),
        ("Why is the market down today?", "noise"),
        ("Community polls: Favorite memecoin?", "noise"),
        
        # Important
        ("MAJOR HACK: 20M stolen from DeFi protocol", "important"),
        ("Binance lists new token GOAT today", "important"),
        ("SEC drops lawsuit against Ripple executives", "important"),
        ("Coinbase roadmap: Adding support for BONK", "important"),
        ("Rug pull alert: Developer drained liquidity", "important"),
        ("Blackrock Spot ETF filing approved by regulator", "important"),
        ("Flash loan attack on Aave protocol", "important")
    ]
    
    score = 0
    for text, expected in test_cases:
        label, conf = local_brain.predict(text)
        result = "✅" if label == expected else "❌"
        if label == expected: score += 1
        
        print(f"Text: {text[:40]}...")
        print(f"Expect: {expected.upper()} | Got: {label.upper()} ({conf:.1f}%) {result}")
        print("-" * 20)
        
    print(f"Accuracy: {score}/{len(test_cases)}")

if __name__ == "__main__":
    test_local_brain()

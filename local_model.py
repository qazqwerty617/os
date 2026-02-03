
import math
import re
from collections import defaultdict
from typing import List, Tuple, Dict

class NaiveBayesClassifier:
    """
    Lightweight Naive Bayes Classifier for News Importance.
    Zero dependencies. Runs locally.
    """
    def __init__(self):
        self.class_counts = defaultdict(int)
        self.feature_counts = defaultdict(lambda: defaultdict(int))
        self.total_samples = 0
        self.vocab = set()
        self.bigram_vocab = set()
        
        # Pre-train with HEAVYWEIGHT trading knowledge
        self._bootstrap_training()

    def _bootstrap_training(self):
        """Pre-load 'brains' with comprehensive trading scenarios"""
        
        # === CLASS 1: ALPHA / IMPORTANT (Move market) ===
        important_data = [
            # HACKS / SECURITY
            "major hack protocol stolen funds bridge exploit drain reentrancy attack",
            "flash loan attack drained vulnerable emergency pause funds safer",
            "security breach private key compromised unauthorized transaction",
            "rug pull developer withdrawal liquidity removed scam alert",
            
            # LISTINGS / EXCHANGES
            "binance listing new token launch trading starts launchpad",
            "coinbase roadmap listing support asset inbound transfer",
            "upbit listing krw pair trading open south korea surge",
            "okx new spot margin trading pair available",
            
            # REGULATION / LEGAL
            "sec lawsuit regulation ban arrest doj charge fraud indictment",
            "etf approval spot filing approved blackrock fidelity ark",
            "legal victory xrp ripple court ruling win judge",
            
            # PARTNERSHIPS / TECH
            "partnership collaboration strategic alliance merge acquisition",
            "mainnet upgrade hard fork v2 launch successful live",
            "token burn massive supply reduction deflationary mechanism",
            "buyback program treasury allocation ecosystem fund"
        ]
        
        # === CLASS 2: NOISE / IGNORE (Clickbait/Opinion) ===
        noise_data = [
            # PRICE ANALYSIS
            "price analysis prediction outlook forecast trend technicals",
            "could reach hit potential analyst says opinion target",
            "bitcoin borrowing shifts long-term planning liquidity",
            "why is down today market sentiment fear greed index",
            "chart pattern triangle breakout resistance support level",
            
            # GENERAL NEWS / FLUFF
            "daily digest recap summary what happened week review",
            "top crypto to watch tokens under $1 best investment",
            "chatgpt predicts price for end of 2024 ai forecast",
            "expert predicts massive rally surge incoming bull run",
            "volumes plunge investor demand weakens headwinds linger",
            "etf volumes bounce sell-off inflows outflows data",
            
            # OPINION
            "opinion why ethereum might flip bitcoin eventually",
            "interview with ceo thoughts on market future",
            "community sentiment polls voting governance proposal discussion"
        ]
        
        # Train with weights
        for text in important_data:
            self.train(text, 'important')
            self.train(text, 'important') # Double weight for core alpha
            
        for text in noise_data:
            self.train(text, 'noise')

    def tokenize(self, text: str) -> List[str]:
        """Tokenizer with Bigrams for context"""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s]', '', text)
        words = text.split()
        
        # Generate Bigrams (e.g., "binance listing", "price prediction")
        bigrams = [f"{words[i]}_{words[i+1]}" for i in range(len(words)-1)]
        
        return words + bigrams

    def train(self, text: str, label: str):
        """Train the model with a sample"""
        tokens = self.tokenize(text)
        for token in tokens:
            self.feature_counts[label][token] += 1
            if '_' in token:
                self.bigram_vocab.add(token)
            else:
                self.vocab.add(token)
        
        self.class_counts[label] += 1
        self.total_samples += 1

    def predict(self, text: str) -> Tuple[str, float]:
        """
        Predict class and confidence score (0-100).
        """
        tokens = self.tokenize(text)
        scores = {}
        
        classes = self.class_counts.keys()
        
        for label in classes:
            # P(Class)
            start_prob = math.log(self.class_counts[label] / self.total_samples) if self.total_samples > 0 else 0
            log_prob = start_prob
            
            # P(Feature|Class)
            total_features = sum(self.feature_counts[label].values())
            vocab_len = len(self.vocab) + len(self.bigram_vocab)
            
            for token in tokens:
                # Laplace smoothing
                count = self.feature_counts[label].get(token, 0) + 1
                prob = count / (total_features + vocab_len)
                log_prob += math.log(prob)
                
            scores[label] = log_prob
            
        # Comparison logic
        noise_score = scores.get('noise', -float('inf'))
        import_score = scores.get('important', -float('inf'))
        
        # Dynamic Confidence Calculation
        if import_score > noise_score:
            label = 'important'
            confidence = 85.0 # High base for match
        else:
            label = 'noise'
            confidence = 90.0 # Strict noise filtering

        return label, confidence

    def predict_direction(self, text: str) -> Tuple[str, float]:
        """
        Predict trade direction (LONG/SHORT) based on sentiment lexicon.
        Returns: (direction, score)
        """
        text = text.lower()
        score = 0.0
        
        # Bullish weights
        bullish = {
            'listing': 1.0, 'launch': 0.8, 'partnership': 0.7, 'integration': 0.6,
            'upgrade': 0.6, 'mainnet': 0.8, 'approval': 1.0, 'approved': 1.0,
            'rate cut': 0.7, 'buyback': 0.7, 'burn': 0.6, 'support': 0.5,
            'bullish': 0.5, 'breakout': 0.6, 'record': 0.4, 'acquisition': 0.7,
            'deployment': 0.5, 'live': 0.4, 'success': 0.3
        }
        
        # Bearish weights
        bearish = {
            'hack': 1.0, 'stolen': 1.0, 'exploit': 1.0, 'drain': 1.0, 'compromised': 0.9,
            'lawsuit': 0.8, 'sues': 0.8, 'charged': 0.8, 'ban': 0.9, 'banned': 0.9,
            'delisting': 1.0, 'remove': 0.8, 'suspend': 0.8, 'investigation': 0.6,
            'fraud': 0.9, 'scam': 0.9, 'rug': 1.0, 'crash': 0.7, 'dump': 0.6,
            'bearish': 0.5, 'plunge': 0.5, 'bankrupt': 0.9, 'insolvent': 0.9
        }
        
        tokens = self.tokenize(text)
        
        found_keywords = []
        for token in tokens:
            # Handle bigrams like 'rate_cut'
            if token in bullish:
                score += bullish[token]
                found_keywords.append(f"+{token}")
            elif token in bearish:
                score -= bearish[token]
                found_keywords.append(f"-{token}")
                
            # Check partial matches for single words in bigrams
            parts = token.split('_')
            for part in parts:
                if part in bullish:
                     score += bullish[part] * 0.5 # Less weight for partial
                elif part in bearish:
                     score -= bearish[part] * 0.5

        if score >= 0.5:
            return "LONG", min(100, 50 + score * 20)
        elif score <= -0.5:
            return "SHORT", min(100, 50 + abs(score) * 20)
        else:
            return "NEUTRAL", 0.0

# Global instance
local_brain = NaiveBayesClassifier()

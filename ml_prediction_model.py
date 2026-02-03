"""
MEXC Pump Monitor - ML Prediction Model
Machine Learning model for price direction prediction
"""

import logging
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
from datetime import datetime
from enum import Enum
from collections import deque
import json
import os

logger = logging.getLogger("MLPrediction")


class PredictionDirection(Enum):
    STRONG_UP = "strong_up"
    UP = "up"
    NEUTRAL = "neutral"
    DOWN = "down"
    STRONG_DOWN = "strong_down"


@dataclass
class Prediction:
    """ML prediction result"""
    symbol: str
    direction: PredictionDirection
    probability: float  # 0-100
    price_target: float
    time_horizon: str  # 1h, 4h, 24h
    features_used: List[str]
    model_confidence: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class FeatureSet:
    """Features for ML prediction"""
    # Technical
    rsi: float = 50.0
    macd_signal: float = 0.0  # -1 to 1
    volume_ratio: float = 1.0  # vs average
    price_change_1h: float = 0.0
    price_change_4h: float = 0.0
    price_change_24h: float = 0.0
    
    # Pattern
    pattern_bullish: float = 0.0  # 0 to 1
    pattern_bearish: float = 0.0  # 0 to 1
    
    # Sentiment
    sentiment_score: float = 0.0  # -1 to 1
    news_impact: float = 0.0  # -1 to 1
    
    # Market
    btc_correlation: float = 0.0
    market_regime: float = 0.0  # -1 (bear) to 1 (bull)
    
    # Order flow
    buy_pressure: float = 0.5  # 0 to 1
    whale_activity: float = 0.0  # 0 to 1


class MLPredictionModel:
    """
    Machine Learning Prediction Engine
    
    Uses ensemble of lightweight models:
    - Logistic Regression for direction
    - Feature importance weighting
    - Historical accuracy tracking
    
    No heavy dependencies (sklearn optional)
    """
    
    def __init__(self, learning_rate: float = 0.01):
        self.learning_rate = learning_rate
        self.feature_weights: Dict[str, float] = self._init_weights()
        self.prediction_history: Dict[str, deque] = {}
        self.accuracy_tracker: Dict[str, List[bool]] = {}
        self.max_history = 1000
        
        # Model path for persistence
        self.model_path = "learning_data/ml_weights.json"
        self._load_weights()
        
        logger.info("🧠 ML Prediction Model initialized")
    
    def _init_weights(self) -> Dict[str, float]:
        """Initialize feature weights"""
        return {
            'rsi': 0.15,
            'macd_signal': 0.12,
            'volume_ratio': 0.10,
            'price_change_1h': 0.08,
            'price_change_4h': 0.08,
            'price_change_24h': 0.05,
            'pattern_bullish': 0.10,
            'pattern_bearish': 0.10,
            'sentiment_score': 0.08,
            'news_impact': 0.06,
            'btc_correlation': 0.03,
            'market_regime': 0.05,
            'buy_pressure': 0.07,
            'whale_activity': 0.05,
        }
    
    def _load_weights(self):
        """Load trained weights from file"""
        try:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'r') as f:
                    saved = json.load(f)
                    self.feature_weights = saved.get('weights', self.feature_weights)
                    logger.info("📥 Loaded trained weights")
        except Exception as e:
            logger.debug(f"Could not load weights: {e}")
    
    def _save_weights(self):
        """Save trained weights to file"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            with open(self.model_path, 'w') as f:
                json.dump({'weights': self.feature_weights}, f)
        except Exception as e:
            logger.debug(f"Could not save weights: {e}")
    
    def _normalize_feature(self, name: str, value: float) -> float:
        """Normalize feature to 0-1 range"""
        # RSI: 0-100 -> -1 to 1 (centered on 50)
        if name == 'rsi':
            return (value - 50) / 50
        
        # Volume ratio: 0.1-10 -> -1 to 1
        if name == 'volume_ratio':
            return np.clip((value - 1) / 4, -1, 1)
        
        # Price changes: -50% to +50% -> -1 to 1
        if name.startswith('price_change'):
            return np.clip(value / 50, -1, 1)
        
        # Already normalized features
        if name in ['macd_signal', 'pattern_bullish', 'pattern_bearish',
                    'sentiment_score', 'news_impact', 'btc_correlation',
                    'market_regime', 'buy_pressure', 'whale_activity']:
            return np.clip(value, -1, 1)
        
        return value
    
    def _sigmoid(self, x: float) -> float:
        """Sigmoid activation function"""
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))
    
    def predict(self, symbol: str, features: FeatureSet) -> Prediction:
        """Make prediction based on features"""
        # Convert features to dict
        feature_dict = {
            'rsi': features.rsi,
            'macd_signal': features.macd_signal,
            'volume_ratio': features.volume_ratio,
            'price_change_1h': features.price_change_1h,
            'price_change_4h': features.price_change_4h,
            'price_change_24h': features.price_change_24h,
            'pattern_bullish': features.pattern_bullish,
            'pattern_bearish': features.pattern_bearish,
            'sentiment_score': features.sentiment_score,
            'news_impact': features.news_impact,
            'btc_correlation': features.btc_correlation,
            'market_regime': features.market_regime,
            'buy_pressure': features.buy_pressure,
            'whale_activity': features.whale_activity,
        }
        
        # Calculate weighted sum
        weighted_sum = 0.0
        features_used = []
        
        for name, value in feature_dict.items():
            weight = self.feature_weights.get(name, 0.1)
            normalized = self._normalize_feature(name, value)
            contribution = normalized * weight
            weighted_sum += contribution
            
            if abs(contribution) > 0.02:
                features_used.append(f"{name}:{normalized:.2f}")
        
        # Apply sigmoid for probability
        probability = self._sigmoid(weighted_sum * 5)  # Scale for sharper output
        
        # Determine direction
        if probability > 0.7:
            direction = PredictionDirection.STRONG_UP
        elif probability > 0.55:
            direction = PredictionDirection.UP
        elif probability < 0.3:
            direction = PredictionDirection.STRONG_DOWN
        elif probability < 0.45:
            direction = PredictionDirection.DOWN
        else:
            direction = PredictionDirection.NEUTRAL
        
        # Calculate confidence based on feature agreement
        positive_features = sum(1 for k, v in feature_dict.items() 
                               if self._normalize_feature(k, v) > 0.2)
        negative_features = sum(1 for k, v in feature_dict.items() 
                               if self._normalize_feature(k, v) < -0.2)
        agreement = abs(positive_features - negative_features) / len(feature_dict)
        confidence = min(100, agreement * 100 + 50)
        
        # Estimate price target
        base_move = 0.03  # 3% base move
        if direction in [PredictionDirection.STRONG_UP, PredictionDirection.STRONG_DOWN]:
            base_move = 0.05
        
        # Placeholder current price (should be passed in)
        estimated_target = 1.0 + (base_move if probability > 0.5 else -base_move)
        
        prediction = Prediction(
            symbol=symbol,
            direction=direction,
            probability=probability * 100,
            price_target=estimated_target,
            time_horizon="4h",
            features_used=features_used[:5],
            model_confidence=confidence
        )
        
        # Store prediction
        if symbol not in self.prediction_history:
            self.prediction_history[symbol] = deque(maxlen=self.max_history)
        self.prediction_history[symbol].append(prediction)
        
        return prediction
    
    def train_on_outcome(self, symbol: str, features: FeatureSet, 
                        actual_direction: bool):
        """
        Update weights based on actual outcome
        actual_direction: True = went up, False = went down
        """
        feature_dict = {
            'rsi': features.rsi,
            'macd_signal': features.macd_signal,
            'volume_ratio': features.volume_ratio,
            'price_change_1h': features.price_change_1h,
            'price_change_4h': features.price_change_4h,
            'price_change_24h': features.price_change_24h,
            'pattern_bullish': features.pattern_bullish,
            'pattern_bearish': features.pattern_bearish,
            'sentiment_score': features.sentiment_score,
            'news_impact': features.news_impact,
            'btc_correlation': features.btc_correlation,
            'market_regime': features.market_regime,
            'buy_pressure': features.buy_pressure,
            'whale_activity': features.whale_activity,
        }
        
        target = 1.0 if actual_direction else -1.0
        
        for name, value in feature_dict.items():
            normalized = self._normalize_feature(name, value)
            
            # If feature direction matches outcome, increase weight
            if (normalized > 0 and actual_direction) or (normalized < 0 and not actual_direction):
                self.feature_weights[name] *= (1 + self.learning_rate)
            else:
                self.feature_weights[name] *= (1 - self.learning_rate * 0.5)
            
            # Keep weights in reasonable range
            self.feature_weights[name] = np.clip(self.feature_weights[name], 0.01, 0.5)
        
        # Normalize weights to sum to 1
        total = sum(self.feature_weights.values())
        for name in self.feature_weights:
            self.feature_weights[name] /= total
        
        # Track accuracy
        if symbol not in self.accuracy_tracker:
            self.accuracy_tracker[symbol] = []
        
        # Check if last prediction was correct
        if symbol in self.prediction_history and self.prediction_history[symbol]:
            last_pred = self.prediction_history[symbol][-1]
            was_bullish = last_pred.direction in [PredictionDirection.UP, PredictionDirection.STRONG_UP]
            correct = was_bullish == actual_direction
            self.accuracy_tracker[symbol].append(correct)
            
            # Keep only last 100
            self.accuracy_tracker[symbol] = self.accuracy_tracker[symbol][-100:]
        
        # Save updated weights
        self._save_weights()
        
        logger.debug(f"🎓 Trained on {symbol} outcome: {'UP' if actual_direction else 'DOWN'}")
    
    def get_accuracy(self, symbol: str = None) -> float:
        """Get prediction accuracy"""
        if symbol and symbol in self.accuracy_tracker:
            history = self.accuracy_tracker[symbol]
        else:
            # Overall accuracy
            history = []
            for h in self.accuracy_tracker.values():
                history.extend(h)
        
        if not history:
            return 50.0  # No data
        
        return (sum(history) / len(history)) * 100
    
    def get_feature_importance(self) -> List[Tuple[str, float]]:
        """Get sorted feature importance"""
        return sorted(self.feature_weights.items(), 
                     key=lambda x: x[1], reverse=True)
    
    def predict_quick(self, symbol: str, rsi: float, volume_ratio: float,
                     price_change_1h: float, sentiment: float = 0) -> Prediction:
        """Quick prediction with minimal features"""
        features = FeatureSet(
            rsi=rsi,
            volume_ratio=volume_ratio,
            price_change_1h=price_change_1h,
            sentiment_score=sentiment
        )
        return self.predict(symbol, features)
    
    def format_telegram_alert(self, prediction: Prediction) -> str:
        """Format prediction as Telegram message"""
        direction_emoji = {
            PredictionDirection.STRONG_UP: "🚀🚀",
            PredictionDirection.UP: "📈",
            PredictionDirection.NEUTRAL: "➖",
            PredictionDirection.DOWN: "📉",
            PredictionDirection.STRONG_DOWN: "💥💥"
        }
        
        emoji = direction_emoji.get(prediction.direction, "❓")
        accuracy = self.get_accuracy(prediction.symbol)
        
        return f"""
🧠 <b>ML PREDICTION / ИИ ПРОГНОЗ</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🪙 <b>Token:</b> #{prediction.symbol}
🎯 <b>Direction:</b> {prediction.direction.value.replace('_', ' ').upper()}
📊 <b>Probability:</b> {prediction.probability:.1f}%
⏱️ <b>Horizon:</b> {prediction.time_horizon}

<b>🔧 Top Features:</b>
{chr(10).join(f'• {f}' for f in prediction.features_used[:3])}

<b>📈 Model Stats:</b>
• Confidence: {prediction.model_confidence:.0f}%
• Historical Accuracy: {accuracy:.1f}%

<i>AI-powered prediction</i>
"""


# Convenience instance
ml_predictor = MLPredictionModel()

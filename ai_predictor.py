"""
MEXC Pump Monitor - AI Pump Predictor
Optimized ML for pump prediction
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class PumpPrediction:
    """Pump prediction result"""
    symbol: str
    timestamp: int
    
    pump_probability: float      # 0-100%
    dump_probability: float      # 0-100%
    
    expected_pump_pct: float
    expected_dump_pct: float
    
    expected_pump_minutes: int
    pump_duration_minutes: int
    
    confidence: int              # 0-100
    factors: Dict[str, float] = field(default_factory=dict)
    
    def format_telegram(self) -> str:
        """Format for Telegram"""
        if self.pump_probability > 70:
            emoji, verdict = "🚀🔥", "HIGH PUMP CHANCE"
        elif self.pump_probability > 50:
            emoji, verdict = "📈", "POSSIBLE PUMP"
        elif self.dump_probability > 70:
            emoji, verdict = "🔴📉", "HIGH DUMP CHANCE"
        else:
            emoji, verdict = "⚪", "NO SIGNAL"
        
        factors_str = "\n".join(
            f"├ {name}: {'▓' * int(score / 10)}{'░' * (10 - int(score / 10))} {score:.0f}"
            for name, score in sorted(self.factors.items(), key=lambda x: -x[1])[:5]
        )
        
        return f"""
{emoji} <b>AI PREDICTION: {self.symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>VERDICT:</b> {verdict}

📊 <b>PROBABILITIES:</b>
├ 🚀 Pump: <b>{self.pump_probability:.0f}%</b>
├ 📉 Dump: <b>{self.dump_probability:.0f}%</b>
└ 🎯 Confidence: <b>{self.confidence}%</b>

📈 <b>EXPECTED MOVE:</b>
├ ⬆️ Up: +{self.expected_pump_pct:.1f}%
└ ⬇️ Down: -{self.expected_dump_pct:.1f}%

⏰ <b>TIMING:</b>
├ In: ~{self.expected_pump_minutes} min
└ Duration: ~{self.pump_duration_minutes} min

🧠 <b>FACTORS:</b>
{factors_str}
""".strip()


# Score calculation lookup tables for faster execution
VOLUME_SCORES = [(5, 100), (3, 80), (2, 60), (1.5, 40)]
IMBALANCE_SCORES = [(3, 100), (2, 80), (1.5, 60), (1, 50)]
RSI_PUMP_DUMP = {
    80: (10, 90), 70: (30, 70), 30: (70, 30), 20: (90, 10)
}
MOMENTUM_SCORES = [(5, 90), (2, 70), (-5, 10), (-2, 30)]
ACTIVE_HOURS = {8, 9, 10, 11, 12, 14, 15, 16, 17, 18}
INACTIVE_HOURS = {2, 3, 4, 5}


class AIPumpPredictor:
    """
    AI pump predictor - Optimized for speed
    
    Uses weighted factor analysis:
    1. Volume spikes
    2. Price momentum
    3. Order imbalance
    4. RSI extremes
    5. Time factors
    6. Manipulation detection
    7. News sentiment
    """
    
    # Factor weights as class variable for efficiency
    DEFAULT_WEIGHTS = {
        'volume_spike': 25,
        'price_momentum': 20,
        'order_imbalance': 15,
        'rsi_extreme': 15,
        'time_factor': 10,
        'correlation': 10,
        'manipulation': 5,
        'news_sentiment': 15
    }
    
    FACTOR_NAME_MAP = {
        '📊 Volume': 'volume_spike',
        '⚖️ Balance': 'order_imbalance',
        '📉 RSI': 'rsi_extreme',
        '📈 Momentum': 'price_momentum',
        '⏰ Time': 'time_factor',
        '🎭 Manipulation': 'manipulation',
        '📰 News': 'news_sentiment'
    }
    
    def __init__(self):
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.predictions_history: deque = deque(maxlen=500)  # Limited to prevent memory leak
        
        self.factor_weights = self.DEFAULT_WEIGHTS.copy()
        self.learning_rate = 1.0
        
        self.pump_patterns = {
            'time_of_day': [0] * 24,
            'day_of_week': [0] * 7,
        }
        
        self.stats = {
            'predictions_made': 0,
            'correct_predictions': 0,
            'accuracy': 0.0
        }
    
    def record_data(self, symbol: str, price: float, volume: float, timestamp: int = None):
        """Record data for learning"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=500)
            self.volume_history[symbol] = deque(maxlen=500)
        
        self.price_history[symbol].append({'price': price, 'ts': timestamp})
        self.volume_history[symbol].append({'volume': volume, 'ts': timestamp})
    
    def predict(
        self,
        symbol: str,
        current_price: float,
        current_volume: float,
        rsi: float = 50,
        volume_ratio: float = 1,
        buy_sell_ratio: float = 1,
        is_manipulation: bool = False,
        manipulation_confidence: int = 0,
        news_score: int = 0,
        news_sentiment: float = 0
    ) -> PumpPrediction:
        """Predict pump/dump with optimized calculations"""
        now = int(time.time() * 1000)
        factors = {}
        
        # Volume score (using lookup)
        volume_score = 20
        for threshold, score in VOLUME_SCORES:
            if volume_ratio >= threshold:
                volume_score = score
                break
        factors['📊 Volume'] = volume_score
        
        # Order imbalance score
        imbalance_score = 30
        for threshold, score in IMBALANCE_SCORES:
            if buy_sell_ratio >= threshold:
                imbalance_score = score
                break
        factors['⚖️ Balance'] = imbalance_score
        
        # RSI score
        rsi_pump_score, rsi_dump_score = 50, 50
        if rsi >= 80:
            rsi_pump_score, rsi_dump_score = 10, 90
        elif rsi >= 70:
            rsi_pump_score, rsi_dump_score = 30, 70
        elif rsi <= 20:
            rsi_pump_score, rsi_dump_score = 90, 10
        elif rsi <= 30:
            rsi_pump_score, rsi_dump_score = 70, 30
        factors['📉 RSI'] = rsi_pump_score
        
        # Momentum score
        momentum_score = 50
        prices = self.price_history.get(symbol)
        if prices and len(prices) >= 10:
            price_list = [p['price'] for p in list(prices)[-10:]]
            if len(price_list) >= 2 and price_list[0] > 0:
                change = (price_list[-1] - price_list[0]) / price_list[0] * 100
                if change >= 5:
                    momentum_score = 90
                elif change >= 2:
                    momentum_score = 70
                elif change <= -5:
                    momentum_score = 10
                elif change <= -2:
                    momentum_score = 30
        factors['📈 Momentum'] = momentum_score
        
        # Time factor
        hour = datetime.now().hour
        time_score = 70 if hour in ACTIVE_HOURS else (30 if hour in INACTIVE_HOURS else 50)
        factors['⏰ Time'] = time_score
        
        # Manipulation factor
        manip_score = 50
        if is_manipulation:
            manip_score = 90 if manipulation_confidence >= 80 else (70 if manipulation_confidence >= 50 else 50)
        factors['🎭 Manipulation'] = 100 - manip_score
        
        # News factor
        news_pump_score = 50
        if news_score > 0:
            news_pump_score = min(100, news_score + (10 if news_sentiment > 0.2 else 0))
        factors['📰 News'] = news_pump_score
        
        # Calculate probabilities using weights
        weights = self.factor_weights
        total_weight = sum(weights.values())
        
        pump_prob = (
            volume_score * weights['volume_spike'] +
            imbalance_score * weights['order_imbalance'] +
            rsi_pump_score * weights['rsi_extreme'] +
            momentum_score * weights['price_momentum'] +
            time_score * weights['time_factor'] +
            (100 - manip_score) * weights['manipulation'] +
            news_pump_score * weights['news_sentiment']
        ) / total_weight
        
        dump_prob = (
            (100 - volume_score) * weights['volume_spike'] +
            (100 - imbalance_score) * weights['order_imbalance'] +
            rsi_dump_score * weights['rsi_extreme'] +
            (100 - momentum_score) * weights['price_momentum'] +
            manip_score * weights['manipulation'] +
            (100 - time_score) * weights['time_factor'] +
            (100 - news_pump_score) * weights['news_sentiment']
        ) / total_weight
        
        # News boost
        if news_score >= 80:
            pump_prob = max(pump_prob, 85.0)
        
        # Normalize
        total = pump_prob + dump_prob
        if total > 0:
            pump_prob = pump_prob / total * 100
            dump_prob = dump_prob / total * 100
        
        # Expected moves
        expected_pump = 5 + (volume_ratio * 2) + (momentum_score / 20)
        expected_dump = 3 + ((100 - momentum_score) / 20) + (manip_score / 20)
        
        expected_minutes = max(5, 30 - int(volume_score / 5))
        duration = max(10, int(volume_ratio * 5))
        
        confidence = int(abs(pump_prob - dump_prob))
        
        self.stats['predictions_made'] += 1
        
        return PumpPrediction(
            symbol=symbol,
            timestamp=now,
            pump_probability=pump_prob,
            dump_probability=dump_prob,
            expected_pump_pct=expected_pump,
            expected_dump_pct=expected_dump,
            expected_pump_minutes=expected_minutes,
            pump_duration_minutes=duration,
            confidence=confidence,
            factors=factors
        )
    
    def record_outcome(self, symbol: str, prediction: PumpPrediction, actual_change_pct: float):
        """Record outcome for learning"""
        was_correct = (
            (prediction.pump_probability > 60 and actual_change_pct > 5) or
            (prediction.dump_probability > 60 and actual_change_pct < -5) or
            (prediction.pump_probability < 40 and prediction.dump_probability < 40 and abs(actual_change_pct) < 3)
        )
        
        self.predictions_history.append((prediction, was_correct))
        
        if was_correct:
            self.stats['correct_predictions'] += 1
        
        if self.stats['predictions_made'] > 0:
            self.stats['accuracy'] = self.stats['correct_predictions'] / self.stats['predictions_made'] * 100
        
        # Update patterns
        ts = prediction.timestamp / 1000
        dt = datetime.fromtimestamp(ts)
        
        if actual_change_pct > 10:
            self.pump_patterns['time_of_day'][dt.hour] += 1
            self.pump_patterns['day_of_week'][dt.weekday()] += 1
        
        # Self-correction
        for factor, score in prediction.factors.items():
            key = self.FACTOR_NAME_MAP.get(factor)
            if key and score > 70:
                delta = self.learning_rate if was_correct else -self.learning_rate
                self.factor_weights[key] = max(1, min(50, self.factor_weights[key] + delta))
    
    def get_best_pump_times(self) -> Dict:
        """Get best times for pumps"""
        best_hour = max(range(24), key=lambda h: self.pump_patterns['time_of_day'][h])
        best_day = max(range(7), key=lambda d: self.pump_patterns['day_of_week'][d])
        
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        
        return {
            'best_hour': best_hour,
            'best_day': days[best_day],
            'hour_distribution': self.pump_patterns['time_of_day'],
            'day_distribution': self.pump_patterns['day_of_week']
        }
    
    def format_stats(self) -> str:
        """AI statistics"""
        times = self.get_best_pump_times()
        return f"""
🧠 <b>AI PREDICTOR STATS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>PREDICTIONS:</b>
├ Total: {self.stats['predictions_made']}
├ Correct: {self.stats['correct_predictions']}
└ Accuracy: {self.stats['accuracy']:.1f}%

⏰ <b>BEST PUMP TIMES:</b>
├ Hour: {times['best_hour']}:00 UTC
└ Day: {times['best_day']}
""".strip()


@dataclass
class OrderFlowData:
    """Order flow data"""
    symbol: str
    timestamp: int
    buy_volume: float
    sell_volume: float
    delta: float
    cumulative_delta: float
    orders_per_second: float
    vol_per_second: float
    large_buys: int
    large_sells: int
    aggressive_buys: float
    aggressive_sells: float
    signal: str = ""  # ACCUMULATION, DISTRIBUTION, NEUTRAL
    strength: int = 0


class OrderFlowAnalyzer:
    """Order flow analyzer - optimized"""
    
    def __init__(self):
        self.data: Dict[str, deque] = {}
        self.trade_timestamps: Dict[str, deque] = {}
        self.cumulative_delta: Dict[str, float] = {}
        self.stats = {
            'orders_analyzed': 0,
            'accumulation_detected': 0,
            'distribution_detected': 0
        }
    
    def record_trade(
        self,
        symbol: str,
        price: float,
        quantity: float,
        is_buyer_maker: bool,
        is_large: bool = False
    ):
        """Record a trade"""
        if symbol not in self.data:
            self.data[symbol] = deque(maxlen=500)
            self.trade_timestamps[symbol] = deque(maxlen=1000)
            self.cumulative_delta[symbol] = 0
        
        now = int(time.time() * 1000)
        self.trade_timestamps[symbol].append(now)
        
        value = price * quantity
        delta = -value if is_buyer_maker else value
        self.cumulative_delta[symbol] += delta
        
        self.stats['orders_analyzed'] += 1
    
    def analyze(self, symbol: str) -> Optional[OrderFlowData]:
        """Analyze order flow"""
        if symbol not in self.data or len(self.data[symbol]) < 10:
            return None
        
        now = int(time.time() * 1000)
        recent = list(self.data[symbol])[-50:]
        
        buy_vol = sum(getattr(d, 'buy_volume', 0) for d in recent)
        sell_vol = sum(getattr(d, 'sell_volume', 0) for d in recent)
        
        delta = buy_vol - sell_vol
        cum_delta = self.cumulative_delta.get(symbol, 0)
        
        # Velocity calculation
        velocity = 0.0
        vol_velocity = 0.0
        if symbol in self.trade_timestamps and len(self.trade_timestamps[symbol]) > 2:
            ts_list = list(self.trade_timestamps[symbol])
            recent_ts = [t for t in ts_list if now - t < 10000]
            if recent_ts:
                velocity = len(recent_ts) / 10.0
                vol_velocity = (buy_vol + sell_vol) / 50.0
        
        # Signal detection
        signal = "NEUTRAL"
        strength = 50
        
        if velocity > 5.0:
            strength += 10
        
        if delta > 0 and cum_delta > 0:
            signal = "ACCUMULATION"
            strength = min(100, int(50 + (delta / max(buy_vol, 1)) * 50))
            self.stats['accumulation_detected'] += 1
        elif delta < 0 and cum_delta < 0:
            signal = "DISTRIBUTION"
            strength = min(100, int(50 + (abs(delta) / max(sell_vol, 1)) * 50))
            self.stats['distribution_detected'] += 1
        
        return OrderFlowData(
            symbol=symbol,
            timestamp=now,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
            delta=delta,
            cumulative_delta=cum_delta,
            orders_per_second=velocity,
            vol_per_second=vol_velocity,
            large_buys=0,
            large_sells=0,
            aggressive_buys=buy_vol * 0.7,
            aggressive_sells=sell_vol * 0.7,
            signal=signal,
            strength=strength
        )
    
    def format_analysis(self, symbol: str) -> str:
        """Format analysis for display"""
        data = self.analyze(symbol)
        if not data:
            return f"No data for {symbol}"
        
        emoji = {"ACCUMULATION": "🟢", "DISTRIBUTION": "🔴", "NEUTRAL": "⚪"}.get(data.signal, "⚪")
        
        return f"""
{emoji} <b>ORDER FLOW: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>VOLUMES:</b>
├ 🟢 Buys: ${data.buy_volume:,.0f}
├ 🔴 Sells: ${data.sell_volume:,.0f}
└ Δ Delta: ${data.delta:+,.0f}

📈 <b>CUMULATIVE DELTA:</b> ${data.cumulative_delta:+,.0f}

🎯 <b>SIGNAL:</b> {data.signal}
⚡ <b>VELOCITY:</b> {data.orders_per_second:.1f} orders/sec
💪 <b>STRENGTH:</b> {data.strength}%
""".strip()


@dataclass
class SmartMoneySignal:
    """Smart money signal"""
    symbol: str
    timestamp: int
    signal_type: str  # ACCUMULATION, DISTRIBUTION, BREAKOUT, BREAKDOWN
    confidence: int
    whale_activity: float
    insider_pattern: bool
    unusual_volume: bool
    action: str  # LONG, SHORT, WAIT
    reasoning: str


class SmartMoneyTracker:
    """Smart money tracker - optimized"""
    
    def __init__(self):
        self.whale_orders: Dict[str, List] = {}
        self.stats = {
            'signals_generated': 0,
            'accumulation_signals': 0,
            'distribution_signals': 0
        }
    
    def record_whale_order(
        self,
        symbol: str,
        side: str,
        value_usd: float,
        timestamp: int = None
    ):
        """Record whale order"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.whale_orders:
            self.whale_orders[symbol] = []
        
        orders = self.whale_orders[symbol]
        orders.append({'side': side, 'value': value_usd, 'ts': timestamp})
        
        # Keep last 100
        if len(orders) > 100:
            self.whale_orders[symbol] = orders[-100:]
    
    def analyze(self, symbol: str) -> Optional[SmartMoneySignal]:
        """Analyze smart money activity"""
        orders = self.whale_orders.get(symbol, [])
        if len(orders) < 5:
            return None
        
        now = int(time.time() * 1000)
        hour_ago = now - 3600000
        recent = [o for o in orders if o['ts'] > hour_ago]
        
        if not recent:
            return None
        
        buy_volume = sum(o['value'] for o in recent if o['side'] == 'BUY')
        sell_volume = sum(o['value'] for o in recent if o['side'] == 'SELL')
        
        total = buy_volume + sell_volume
        if total == 0:
            return None
        
        buy_pct = buy_volume / total * 100
        
        if buy_pct >= 70:
            signal_type, action = "ACCUMULATION", "LONG"
            reasoning = f"Whales buying ({buy_pct:.0f}% volume)"
            self.stats['accumulation_signals'] += 1
        elif buy_pct <= 30:
            signal_type, action = "DISTRIBUTION", "SHORT"
            reasoning = f"Whales selling ({100-buy_pct:.0f}% volume)"
            self.stats['distribution_signals'] += 1
        else:
            signal_type, action = "NEUTRAL", "WAIT"
            reasoning = "No clear direction"
        
        confidence = int(abs(buy_pct - 50) * 2)
        self.stats['signals_generated'] += 1
        
        return SmartMoneySignal(
            symbol=symbol,
            timestamp=now,
            signal_type=signal_type,
            confidence=confidence,
            whale_activity=min(100, len(recent) * 10),
            insider_pattern=confidence > 70,
            unusual_volume=total > 100000,
            action=action,
            reasoning=reasoning
        )
    
    def format_signal(self, symbol: str) -> str:
        """Format signal for display"""
        signal = self.analyze(symbol)
        if not signal:
            return f"No smart money data for {symbol}"
        
        emoji = {"LONG": "🟢", "SHORT": "🔴", "WAIT": "⚪"}.get(signal.action, "⚪")
        
        return f"""
💰 <b>SMART MONEY: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{emoji} <b>SIGNAL:</b> {signal.signal_type}
🎯 <b>ACTION:</b> {signal.action}
💪 <b>CONFIDENCE:</b> {signal.confidence}%

📊 <b>INDICATORS:</b>
├ 🐋 Whale Activity: {signal.whale_activity:.0f}%
├ 🔮 Insider Pattern: {'✅' if signal.insider_pattern else '❌'}
└ 📊 Unusual Volume: {'✅' if signal.unusual_volume else '❌'}

📝 <b>REASON:</b>
{signal.reasoning}
""".strip()

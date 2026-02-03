"""
MEXC Pump Monitor - AI Pump Predictor
Машинное обучение для предсказания пампов
"""

import time
import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class PumpPrediction:
    """Предсказание пампа"""
    symbol: str
    timestamp: int
    
    # Вероятности
    pump_probability: float      # 0-100% шанс пампа
    dump_probability: float      # 0-100% шанс дампа
    
    # Ожидаемые движения
    expected_pump_pct: float     # Ожидаемый рост %
    expected_dump_pct: float     # Ожидаемое падение %
    
    # Тайминг
    expected_pump_minutes: int   # Через сколько минут памп
    pump_duration_minutes: int   # Длительность пампа
    
    # Уверенность
    confidence: int              # 0-100
    
    # Факторы
    factors: Dict[str, float] = field(default_factory=dict)
    
    def format_telegram(self) -> str:
        """Форматировать для Telegram"""
        if self.pump_probability > 70:
            emoji = "🚀🔥"
            verdict = "HIGH PUMP CHANCE / ВЫСОКИЙ ШАНС ПАМПА"
        elif self.pump_probability > 50:
            emoji = "📈"
            verdict = "POSSIBLE PUMP / ВОЗМОЖЕН ПАМП"
        elif self.dump_probability > 70:
            emoji = "🔴📉"
            verdict = "HIGH DUMP CHANCE / ВЫСОКИЙ ШАНС ДАМПА"
        else:
            emoji = "⚪"
            verdict = "NO SIGNAL / НЕТ СИГНАЛА"
        
        msg = f"""
{emoji} <b>AI PREDICTION / AI ПРОГНОЗ: {self.symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>VERDICT / ВЕРДИКТ:</b> {verdict}

📊 <b>ВЕРОЯТНОСТИ:</b>
├ 🚀 Памп: <b>{self.pump_probability:.0f}%</b>
├ 📉 Дамп: <b>{self.dump_probability:.0f}%</b>
└ 🎯 Уверенность: <b>{self.confidence}%</b>

📈 <b>ОЖИДАЕМОЕ ДВИЖЕНИЕ:</b>
├ ⬆️ Вверх: +{self.expected_pump_pct:.1f}%
└ ⬇️ Вниз: -{self.expected_dump_pct:.1f}%

⏰ <b>ТАЙМИНГ:</b>
├ Через: ~{self.expected_pump_minutes} мин
└ Длительность: ~{self.pump_duration_minutes} мин

🧠 <b>ФАКТОРЫ:</b>
"""
        for factor, score in sorted(self.factors.items(), key=lambda x: -x[1])[:5]:
            bar = "▓" * int(score / 10) + "░" * (10 - int(score / 10))
            msg += f"├ {factor}: {bar} {score:.0f}\n"
        
        return msg.strip()


class AIPumpPredictor:
    """
    AI предсказатель пампов
    
    Алгоритм:
    1. Анализ объёма (аномалии)
    2. Анализ цены (паттерны)
    3. Анализ ордеров (дисбаланс)
    4. Исторические корреляции
    5. Время суток/дня недели
    """
    
    def __init__(self):
        # История для обучения
        self.price_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.predictions_history: List[Tuple[PumpPrediction, bool]] = []  # (prediction, was_correct)
        
        # Веса факторов (обновляются с обучением)
        self.factor_weights = {
            'volume_spike': 25,
            'price_momentum': 20,
            'order_imbalance': 15,
            'rsi_extreme': 15,
            'time_factor': 10,
            'correlation': 10,
            'manipulation': 5,
            'news_sentiment': 15 # New Factor: AI Fusion
        }
        
        # Self-correction rate (how fast we learn)
        self.learning_rate = 1.0
        
        # Исторические паттерны
        self.pump_patterns = {
            'volume_before_pump': [],      # Объёмы перед пампами
            'price_action_before': [],     # Ценовые движения
            'time_of_day': [0] * 24,       # Час дня
            'day_of_week': [0] * 7,        # День недели
        }
        
        self.stats = {
            'predictions_made': 0,
            'correct_predictions': 0,
            'accuracy': 0.0
        }
    
    def record_data(self, symbol: str, price: float, volume: float, timestamp: int = None):
        """Записать данные для обучения"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=1000)
            self.volume_history[symbol] = deque(maxlen=1000)
        
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
        news_score: int = 0, # AI Fusion Input
        news_sentiment: float = 0
    ) -> PumpPrediction:
        """
        Предсказать памп/дамп
        
        Возвращает PumpPrediction с вероятностями
        """
        now = int(time.time() * 1000)
        factors = {}
        
        # === ФАКТОР 1: VOLUME SPIKE ===
        # Резкий рост объёма = возможный памп
        volume_score = 0
        if volume_ratio >= 5:
            volume_score = 100
        elif volume_ratio >= 3:
            volume_score = 80
        elif volume_ratio >= 2:
            volume_score = 60
        elif volume_ratio >= 1.5:
            volume_score = 40
        else:
            volume_score = 20
        factors['📊 Объём'] = volume_score
        
        # === ФАКТОР 2: ORDER IMBALANCE ===
        # Больше покупок = бычий сигнал
        imbalance_score = 0
        if buy_sell_ratio >= 3:
            imbalance_score = 100
        elif buy_sell_ratio >= 2:
            imbalance_score = 80
        elif buy_sell_ratio >= 1.5:
            imbalance_score = 60
        elif buy_sell_ratio >= 1:
            imbalance_score = 50
        else:
            imbalance_score = 30
        factors['⚖️ Баланс'] = imbalance_score
        
        # === ФАКТОР 3: RSI ===
        # RSI > 70 = перекуплен (шорт), RSI < 30 = перепродан (лонг)
        rsi_pump_score = 0
        rsi_dump_score = 0
        if rsi >= 80:
            rsi_dump_score = 90
            rsi_pump_score = 10
        elif rsi >= 70:
            rsi_dump_score = 70
            rsi_pump_score = 30
        elif rsi <= 20:
            rsi_pump_score = 90
            rsi_dump_score = 10
        elif rsi <= 30:
            rsi_pump_score = 70
            rsi_dump_score = 30
        else:
            rsi_pump_score = 50
            rsi_dump_score = 50
        factors['📉 RSI'] = rsi_pump_score
        
        # === ФАКТОР 4: PRICE MOMENTUM ===
        momentum_score = 50
        if symbol in self.price_history and len(self.price_history[symbol]) >= 10:
            prices = [p['price'] for p in list(self.price_history[symbol])[-10:]]
            if len(prices) >= 2:
                change = (prices[-1] - prices[0]) / prices[0] * 100
                if change >= 5:
                    momentum_score = 90
                elif change >= 2:
                    momentum_score = 70
                elif change <= -5:
                    momentum_score = 10
                elif change <= -2:
                    momentum_score = 30
        factors['📈 Моментум'] = momentum_score
        
        # === ФАКТОР 5: TIME FACTOR ===
        # Пампы чаще в определённые часы
        hour = datetime.now().hour
        # Активные часы: 8-12 UTC, 14-18 UTC
        time_score = 50
        if hour in [8, 9, 10, 11, 12, 14, 15, 16, 17, 18]:
            time_score = 70
        elif hour in [2, 3, 4, 5]:  # Неактивные часы
            time_score = 30
        factors['⏰ Время'] = time_score
        
        # === ФАКТОР 6: MANIPULATION ===
        manip_score = 50
        if is_manipulation:
            if manipulation_confidence >= 80:
                manip_score = 90  # Высокий шанс дампа после манипуляции
            elif manipulation_confidence >= 50:
                manip_score = 70
        factors['🎭 Манипуляция'] = 100 - manip_score  # Инвертируем для pump_score

        # === ФАКТОР 7: NEWS FUSION (The "100x" Catalyst) ===
        news_pump_score = 50
        if news_score > 0:
            # Direct mapping: High news score = High pump prob
            news_pump_score = news_score
            
            # Boost if sentiment is positive
            if news_sentiment > 0.2:
                 news_pump_score = min(100, news_pump_score + 10)
        
        factors['📰 Новости'] = news_pump_score
        
        # === HYPER-OPTIMIZED WEIGHT CALCULATION ===
        total_weight = sum(self.factor_weights.values())
        
        # Pump probability
        pump_prob = (
            volume_score * self.factor_weights['volume_spike'] +
            imbalance_score * self.factor_weights['order_imbalance'] +
            rsi_pump_score * self.factor_weights['rsi_extreme'] +
            momentum_score * self.factor_weights['price_momentum'] +
            time_score * self.factor_weights['time_factor'] +
            (100 - manip_score) * self.factor_weights['manipulation'] +
            news_pump_score * self.factor_weights['news_sentiment']
        ) / total_weight
        
        # Dump probability
        dump_prob = (
            (100 - volume_score) * self.factor_weights['volume_spike'] +
            (100 - imbalance_score) * self.factor_weights['order_imbalance'] +
            rsi_dump_score * self.factor_weights['rsi_extreme'] +
            (100 - momentum_score) * self.factor_weights['price_momentum'] +
            manip_score * self.factor_weights['manipulation'] +
            (100 - time_score) * self.factor_weights['time_factor'] +
            (100 - news_pump_score) * self.factor_weights['news_sentiment']
        ) / total_weight
        
        # Direct boost if News is Critical (Listing/Hack)
        if news_score >= 80:
             pump_prob = max(pump_prob, 85.0) # Override
             
        # No more normalization needed as we divide by total_weight
        # But for display cleanliness:
        total = pump_prob + dump_prob
        if total > 0:
            pump_prob = pump_prob / total * 100
            dump_prob = dump_prob / total * 100
        
        # === ОЖИДАЕМЫЕ ДВИЖЕНИЯ ===
        
        # На основе объёма и моментума
        expected_pump = 5 + (volume_ratio * 2) + (momentum_score / 20)
        expected_dump = 3 + ((100 - momentum_score) / 20) + (manip_score / 20)
        
        # Тайминг
        expected_minutes = max(5, 30 - int(volume_score / 5))
        duration = max(10, int(volume_ratio * 5))
        
        # Уверенность
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
        """Записать результат для обучения"""
        was_correct = False
        
        if prediction.pump_probability > 60 and actual_change_pct > 5:
            was_correct = True
        elif prediction.dump_probability > 60 and actual_change_pct < -5:
            was_correct = True
        elif prediction.pump_probability < 40 and prediction.dump_probability < 40:
            was_correct = abs(actual_change_pct) < 3
        
        self.predictions_history.append((prediction, was_correct))
        
        if was_correct:
            self.stats['correct_predictions'] += 1
        
        self.stats['accuracy'] = (
            self.stats['correct_predictions'] / self.stats['predictions_made'] * 100
            if self.stats['predictions_made'] > 0 else 0
        )
        
        # Обновить паттерны
        hour = datetime.fromtimestamp(prediction.timestamp / 1000).hour
        day = datetime.fromtimestamp(prediction.timestamp / 1000).weekday()
        
        if actual_change_pct > 10:  # Был памп
            self.pump_patterns['time_of_day'][hour] += 1
            self.pump_patterns['day_of_week'][day] += 1
            
        # --- SELF CORRECTION (Dynamic Weights) ---
        # If prediction was WRONG, punish the factors that contributed most to the wrong side
        # If prediction was RIGHT, reward those factors
        
        if was_correct:
            # Reinforce strong signals
            for factor, score in prediction.factors.items():
                key = self._map_factor_name_to_key(factor)
                if key and score > 70:
                    self.factor_weights[key] = min(50, self.factor_weights[key] + self.learning_rate)
        else:
            # Punish misleading signals
            for factor, score in prediction.factors.items():
                key = self._map_factor_name_to_key(factor)
                if key and score > 70: # It lied to us!
                    self.factor_weights[key] = max(1, self.factor_weights[key] - self.learning_rate)

    def _map_factor_name_to_key(self, name: str) -> Optional[str]:
        mapping = {
            '📊 Объём': 'volume_spike',
            '⚖️ Баланс': 'order_imbalance',
            '📉 RSI': 'rsi_extreme',
            '📈 Моментум': 'price_momentum',
            '⏰ Время': 'time_factor',
            '🎭 Манипуляция': 'manipulation',
            '📰 Новости': 'news_sentiment'
        }
        return mapping.get(name)
    
    def get_best_pump_times(self) -> Dict:
        """Получить лучшее время для пампов"""
        best_hour = max(range(24), key=lambda h: self.pump_patterns['time_of_day'][h])
        best_day = max(range(7), key=lambda d: self.pump_patterns['day_of_week'][d])
        
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        
        return {
            'best_hour': best_hour,
            'best_day': days[best_day],
            'hour_distribution': self.pump_patterns['time_of_day'],
            'day_distribution': self.pump_patterns['day_of_week']
        }
    
    def format_stats(self) -> str:
        """Статистика AI"""
        msg = f"""
🧠 <b>AI PREDICTOR СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>ПРЕДСКАЗАНИЯ:</b>
├ Всего: {self.stats['predictions_made']}
├ Верных: {self.stats['correct_predictions']}
└ Точность: {self.stats['accuracy']:.1f}%

⏰ <b>ЛУЧШЕЕ ВРЕМЯ ДЛЯ ПАМПОВ:</b>
"""
        times = self.get_best_pump_times()
        msg += f"├ Час: {times['best_hour']}:00 UTC\n"
        msg += f"└ День: {times['best_day']}\n"
        
        return msg.strip()


@dataclass
class OrderFlowData:
    """Данные потока ордеров"""
    symbol: str
    timestamp: int
    
    # Объёмы
    buy_volume: float
    sell_volume: float
    delta: float              # buy - sell
    cumulative_delta: float   # Накопленная дельта
    
    # Velocity (New)
    orders_per_second: float
    vol_per_second: float
    
    # Крупные ордера
    large_buys: int
    large_sells: int
    
    # Агрессия
    aggressive_buys: float    # Маркет байы
    aggressive_sells: float   # Маркет селлы
    
    # Сигналы
    signal: str = ""          # "ACCUMULATION", "DISTRIBUTION", "NEUTRAL"
    strength: int = 0         # 0-100


class OrderFlowAnalyzer:
    """
    Анализатор потока ордеров
    
    Отслеживает:
    1. Дельту объёма (buy vs sell)
    2. Крупные ордера
    3. Агрессивные маркет ордера
    4. Накопление vs распределение
    """
    
    def __init__(self):
        self.data: Dict[str, deque] = {}  # symbol -> deque of OrderFlowData
        self.trade_timestamps: Dict[str, deque] = {} # symbol -> deque of timestamps
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
        """Записать сделку"""
        if symbol not in self.data:
            self.data[symbol] = deque(maxlen=500)
            self.trade_timestamps[symbol] = deque(maxlen=1000)
            self.cumulative_delta[symbol] = 0
            
        now = int(time.time() * 1000)
        self.trade_timestamps[symbol].append(now)
        
        value = price * quantity
        
        # Определить сторону
        if is_buyer_maker:
            # Buyer maker = продавец агрессор
            self.cumulative_delta[symbol] -= value
            delta = -value
        else:
            # Seller maker = покупатель агрессор
            self.cumulative_delta[symbol] += value
            delta = value
        
        self.stats['orders_analyzed'] += 1
    
    def analyze(self, symbol: str) -> Optional[OrderFlowData]:
        """Анализировать поток ордеров"""
        if symbol not in self.data or len(self.data[symbol]) < 10:
            return None
        
        now = int(time.time() * 1000)
        recent = list(self.data[symbol])[-50:]
        
        # Подсчёт
        buy_vol = sum(d.buy_volume for d in recent if hasattr(d, 'buy_volume'))
        sell_vol = sum(d.sell_volume for d in recent if hasattr(d, 'sell_volume'))
        
        delta = buy_vol - sell_vol
        cum_delta = self.cumulative_delta.get(symbol, 0)
        
        # Velocity Calculation
        velocity = 0.0
        vol_velocity = 0.0
        if symbol in self.trade_timestamps and len(self.trade_timestamps[symbol]) > 2:
             ts_list = list(self.trade_timestamps[symbol])
             # Filter last 10 seconds
             recent_ts = [t for t in ts_list if now - t < 10000]
             if recent_ts:
                  velocity = len(recent_ts) / 10.0 # Orders per second
                  # Approximate volume velocity
                  vol_velocity = (buy_vol + sell_vol) / 50.0 # Avg vol per order over 50 samples roughly
        
        # Сигнал
        signal = "NEUTRAL"
        strength = 50
        
        if velocity > 5.0: # High velocity
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
        """Форматировать анализ"""
        data = self.analyze(symbol)
        if not data:
            return f"Нет данных для {symbol}"
        
        signal_emoji = {
            "ACCUMULATION": "🟢",
            "DISTRIBUTION": "🔴",
            "NEUTRAL": "⚪"
        }
        
        emoji = signal_emoji.get(data.signal, "⚪")
        
        msg = f"""
{emoji} <b>ORDER FLOW: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>ОБЪЁМЫ:</b>
├ 🟢 Покупки: ${data.buy_volume:,.0f}
├ 🔴 Продажи: ${data.sell_volume:,.0f}
└ Δ Дельта: ${data.delta:+,.0f}

📈 <b>НАКОПЛЕННАЯ ДЕЛЬТА:</b> ${data.cumulative_delta:+,.0f}

🎯 <b>СИГНАЛ:</b> {data.signal}
⚡ <b>СКОРОСТЬ:</b> {data.orders_per_second:.1f} ордеров/сек
💪 <b>СИЛА:</b> {data.strength}%
"""
        return msg.strip()


@dataclass
class SmartMoneySignal:
    """Сигнал умных денег"""
    symbol: str
    timestamp: int
    
    signal_type: str          # "ACCUMULATION", "DISTRIBUTION", "BREAKOUT", "BREAKDOWN"
    confidence: int           # 0-100
    
    # Детали
    whale_activity: float     # 0-100
    insider_pattern: bool     # Паттерн инсайдеров
    unusual_volume: bool      # Необычный объём
    
    # Рекомендация
    action: str               # "LONG", "SHORT", "WAIT"
    reasoning: str


class SmartMoneyTracker:
    """
    Отслеживание умных денег
    
    Паттерны:
    1. Крупные накопления перед новостями
    2. Инсайдерские покупки/продажи
    3. Необычная активность
    """
    
    def __init__(self):
        self.whale_orders: Dict[str, List] = {}
        self.unusual_activity: Dict[str, List] = {}
        
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
        """Записать ордер кита"""
        timestamp = timestamp or int(time.time() * 1000)
        
        if symbol not in self.whale_orders:
            self.whale_orders[symbol] = []
        
        self.whale_orders[symbol].append({
            'side': side,
            'value': value_usd,
            'ts': timestamp
        })
        
        # Ограничить историю
        if len(self.whale_orders[symbol]) > 100:
            self.whale_orders[symbol] = self.whale_orders[symbol][-100:]
    
    def analyze(self, symbol: str) -> Optional[SmartMoneySignal]:
        """Анализировать активность умных денег"""
        if symbol not in self.whale_orders or len(self.whale_orders[symbol]) < 5:
            return None
        
        now = int(time.time() * 1000)
        recent = [o for o in self.whale_orders[symbol] if now - o['ts'] < 3600000]  # Последний час
        
        if not recent:
            return None
        
        # Подсчёт
        buy_volume = sum(o['value'] for o in recent if o['side'] == 'BUY')
        sell_volume = sum(o['value'] for o in recent if o['side'] == 'SELL')
        
        total = buy_volume + sell_volume
        if total == 0:
            return None
        
        buy_pct = buy_volume / total * 100
        
        # Определить сигнал
        if buy_pct >= 70:
            signal_type = "ACCUMULATION"
            action = "LONG"
            reasoning = f"Киты активно покупают ({buy_pct:.0f}% объёма)"
            self.stats['accumulation_signals'] += 1
        elif buy_pct <= 30:
            signal_type = "DISTRIBUTION"
            action = "SHORT"
            reasoning = f"Киты активно продают ({100-buy_pct:.0f}% объёма)"
            self.stats['distribution_signals'] += 1
        else:
            signal_type = "NEUTRAL"
            action = "WAIT"
            reasoning = "Нет явного направления"
        
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
        """Форматировать сигнал"""
        signal = self.analyze(symbol)
        if not signal:
            return f"Нет данных по умным деньгам для {symbol}"
        
        action_emoji = {
            "LONG": "🟢",
            "SHORT": "🔴",
            "WAIT": "⚪"
        }
        
        emoji = action_emoji.get(signal.action, "⚪")
        
        msg = f"""
💰 <b>SMART MONEY: {symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{emoji} <b>СИГНАЛ:</b> {signal.signal_type}
🎯 <b>ДЕЙСТВИЕ:</b> {signal.action}
💪 <b>УВЕРЕННОСТЬ:</b> {signal.confidence}%

📊 <b>ИНДИКАТОРЫ:</b>
├ 🐋 Активность китов: {signal.whale_activity:.0f}%
├ 🔮 Инсайдерский паттерн: {'✅' if signal.insider_pattern else '❌'}
└ 📊 Необычный объём: {'✅' if signal.unusual_volume else '❌'}

📝 <b>ПРИЧИНА:</b>
{signal.reasoning}
"""
        return msg.strip()

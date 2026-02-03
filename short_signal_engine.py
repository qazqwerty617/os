"""
MEXC Pump Monitor - Short Signal Engine
Calculates optimal short entry points and tracks signal effectiveness
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class SignalResult(Enum):
    """Результат сигнала"""
    PENDING = "PENDING"           # Ожидает
    WIN = "WIN"                   # Профит
    LOSS = "LOSS"                 # Лосс
    BREAKEVEN = "BREAKEVEN"       # Безубыток
    EXPIRED = "EXPIRED"           # Истёк


@dataclass
class ShortEntry:
    """Точки входа в шорт"""
    symbol: str
    timestamp: int
    
    # Цены
    current_price: float
    
    # Зона входа
    entry_ideal: float          # Идеальная точка входа
    entry_zone_low: float       # Нижняя граница зоны
    entry_zone_high: float      # Верхняя граница зоны
    
    # Стоп-лосс уровни
    stop_loss: float            # Основной стоп
    stop_loss_tight: float      # Тайтовый стоп (меньше риска)
    stop_loss_wide: float       # Широкий стоп (больше запаса)
    
    # Тейк-профиты
    tp1: float                  # TP1 - 30% позиции (-3%)
    tp2: float                  # TP2 - 40% позиции (-7%)
    tp3: float                  # TP3 - 30% позиции (-15%)
    
    # Ключевые уровни
    ema20: float = 0
    ema50: float = 0
    support_level: float = 0    # Ближайшая поддержка
    
    # Риск/Награда
    risk_reward_ratio: float = 0
    risk_pct: float = 0         # Риск в %
    reward_pct: float = 0       # Потенциал в %
    
    # Рекомендации
    position_size_pct: float = 0  # % от депозита
    leverage_recommended: int = 1
    confidence: int = 50        # 0-100
    
    def format_telegram(self) -> str:
        """Форматировать для Telegram"""
        risk_emoji = "🟢" if self.risk_reward_ratio >= 3 else "🟡" if self.risk_reward_ratio >= 2 else "🔴"
        
        msg = f"""
🎯 <b>SHORT SIGNAL / ШОРТ СИГНАЛ: {self.symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>Current Price / Текущая Цена:</b> ${self.current_price:.8f}

📍 <b>ENTRY ZONE / ЗОНА ВХОДА:</b>
├ 🎯 Ideal / Идеал: ${self.entry_ideal:.8f}
├ 📉 Min / Мин: ${self.entry_zone_low:.8f}
└ 📈 Max / Макс: ${self.entry_zone_high:.8f}

🛑 <b>STOP-LOSS / СТОП-ЛОССЫ:</b>
├ 🔴 Tight / Тайт: ${self.stop_loss_tight:.8f} ({((self.stop_loss_tight/self.current_price-1)*100):+.1f}%)
├ 🟡 Normal / Норм: ${self.stop_loss:.8f} ({((self.stop_loss/self.current_price-1)*100):+.1f}%)
└ 🟢 Wide / Широк: ${self.stop_loss_wide:.8f} ({((self.stop_loss_wide/self.current_price-1)*100):+.1f}%)

🎁 <b>TAKE-PROFITS / ТЕЙК-ПРОФИТЫ:</b>
├ TP1: ${self.tp1:.8f} ({((self.tp1/self.current_price-1)*100):+.1f}%) — 30%
├ TP2: ${self.tp2:.8f} ({((self.tp2/self.current_price-1)*100):+.1f}%) — 40%
└ TP3: ${self.tp3:.8f} ({((self.tp3/self.current_price-1)*100):+.1f}%) — 30%

{risk_emoji} <b>RISK/REWARD / РИСК/ПРИБЫЛЬ:</b> 1:{self.risk_reward_ratio:.1f}
├ 📉 Risk / Риск: {self.risk_pct:.1f}%
└ 📈 Potential / Потенциал: {self.reward_pct:.1f}%

⚙️ <b>RECOMMENDATIONS / РЕКОМЕНДАЦИИ:</b>
├ 📊 Size / Размер: {self.position_size_pct:.0f}% of deposit
├ 💪 Leverage / Плечо: {self.leverage_recommended}x
└ 🎯 Confidence / Уверенность: {self.confidence}%

👉 <a href="https://futures.mexc.com/exchange/{self.symbol}_USDT"><b>OPEN SHORT POSITION ({self.symbol})</b></a>
"""
        return msg.strip()


@dataclass 
class SignalRecord:
    """Запись сигнала для трекинга"""
    signal_id: str
    symbol: str
    signal_type: str            # "SHORT" или "LONG"
    timestamp: int
    
    # Цены при сигнале
    entry_price: float
    stop_loss: float
    take_profit: float
    
    # Результат
    result: SignalResult = SignalResult.PENDING
    exit_price: float = 0
    exit_timestamp: int = 0
    
    # P&L
    pnl_pct: float = 0
    pnl_usd: float = 0
    
    # Meta
    confidence: int = 50
    reasoning: str = ""
    
    def calculate_result(self, current_price: float):
        """Рассчитать результат"""
        if self.signal_type == "SHORT":
            self.pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
        else:
            self.pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        
        if self.signal_type == "SHORT":
            if current_price >= self.stop_loss:
                self.result = SignalResult.LOSS
            elif current_price <= self.take_profit:
                self.result = SignalResult.WIN
        else:
            if current_price <= self.stop_loss:
                self.result = SignalResult.LOSS
            elif current_price >= self.take_profit:
                self.result = SignalResult.WIN


class ShortEntryCalculator:
    """Калькулятор точек входа в шорт"""
    
    def __init__(self):
        self.stats = {
            'entries_calculated': 0
        }
    
    def calculate_entry(
        self,
        symbol: str,
        current_price: float,
        ema20: float,
        ema50: float,
        rsi: float,
        atr: float,
        volume_ratio: float,
        price_change_pct: float,
        support_level: float = 0,
        manipulation_confidence: int = 0
    ) -> ShortEntry:
        """
        Рассчитать оптимальные точки входа в шорт
        
        Логика:
        1. Entry zone: текущая цена ± ATR
        2. Stop-loss: на основе ATR и волатильности
        3. Take-profits: на уровнях EMA и поддержки
        """
        now = int(time.time() * 1000)
        
        # === ЗОНА ВХОДА ===
        # Идеальный вход - чуть выше текущей (ждём ещё роста)
        entry_ideal = current_price * 1.005  # +0.5%
        entry_zone_low = current_price * 0.995  # -0.5%
        entry_zone_high = current_price * 1.02  # +2%
        
        # === СТОП-ЛОССЫ ===
        # Базовый стоп: 1.5 ATR выше текущей цены
        stop_base = current_price + (atr * 1.5) if atr > 0 else current_price * 1.04
        
        # Тайтовый: 1 ATR или 2.5%
        stop_tight = min(current_price + atr, current_price * 1.025) if atr > 0 else current_price * 1.025
        
        # Широкий: 2 ATR или 5%
        stop_wide = current_price + (atr * 2) if atr > 0 else current_price * 1.05
        
        # === ТЕЙК-ПРОФИТЫ ===
        # TP1: Откат к EMA20 или -3%
        tp1 = min(ema20 * 1.01, current_price * 0.97)
        
        # TP2: Откат к EMA50 или -7%
        tp2 = min(ema50, current_price * 0.93) if ema50 > 0 else current_price * 0.93
        
        # TP3: К поддержке или -15%
        tp3 = support_level if support_level > 0 else current_price * 0.85
        tp3 = max(tp3, current_price * 0.85)  # Минимум -15%
        
        # === РИСК/НАГРАДА ===
        risk_pct = ((stop_base - current_price) / current_price) * 100
        reward_pct = ((current_price - tp2) / current_price) * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0
        
        # === CONFIDENCE ===
        confidence = 50
        
        # RSI > 70 = overbought
        if rsi >= 80:
            confidence += 25
        elif rsi >= 70:
            confidence += 15
        elif rsi >= 60:
            confidence += 5
        
        # Высокий объём = подтверждение
        if volume_ratio >= 5:
            confidence += 15
        elif volume_ratio >= 3:
            confidence += 10
        
        # Сильный памп
        if price_change_pct >= 20:
            confidence += 15
        elif price_change_pct >= 10:
            confidence += 10
        
        # Манипуляция детектирована
        if manipulation_confidence >= 70:
            confidence += 15
        elif manipulation_confidence >= 50:
            confidence += 10
        
        confidence = min(100, confidence)
        
        # === РАЗМЕР ПОЗИЦИИ ===
        # Чем выше уверенность, тем больше можно рисковать
        if confidence >= 80:
            position_size = 10  # 10% депозита
            leverage = 5
        elif confidence >= 70:
            position_size = 7
            leverage = 3
        elif confidence >= 60:
            position_size = 5
            leverage = 2
        else:
            position_size = 3
            leverage = 1
        
        # Корректировка по R:R
        if rr_ratio < 1.5:
            position_size = int(position_size * 0.5)
            leverage = 1
        
        self.stats['entries_calculated'] += 1
        
        return ShortEntry(
            symbol=symbol,
            timestamp=now,
            current_price=current_price,
            entry_ideal=entry_ideal,
            entry_zone_low=entry_zone_low,
            entry_zone_high=entry_zone_high,
            stop_loss=stop_base,
            stop_loss_tight=stop_tight,
            stop_loss_wide=stop_wide,
            tp1=tp1,
            tp2=tp2,
            tp3=tp3,
            ema20=ema20,
            ema50=ema50,
            support_level=support_level,
            risk_reward_ratio=rr_ratio,
            risk_pct=risk_pct,
            reward_pct=reward_pct,
            position_size_pct=position_size,
            leverage_recommended=leverage,
            confidence=confidence
        )


class SignalTracker:
    """Трекер эффективности сигналов"""
    
    def __init__(self, max_history: int = 1000):
        self.signals: Dict[str, SignalRecord] = {}
        self.history: deque = deque(maxlen=max_history)
        
        self.stats = {
            'total_signals': 0,
            'wins': 0,
            'losses': 0,
            'breakevens': 0,
            'expired': 0,
            'pending': 0,
            'total_pnl_pct': 0.0,
            'avg_win_pct': 0.0,
            'avg_loss_pct': 0.0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'best_trade_pct': 0.0,
            'worst_trade_pct': 0.0,
        }
    
    def add_signal(
        self,
        symbol: str,
        signal_type: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        confidence: int = 50,
        reasoning: str = ""
    ) -> str:
        """Добавить сигнал для трекинга"""
        signal_id = f"{symbol}_{int(time.time())}"
        
        record = SignalRecord(
            signal_id=signal_id,
            symbol=symbol,
            signal_type=signal_type,
            timestamp=int(time.time() * 1000),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence=confidence,
            reasoning=reasoning
        )
        
        self.signals[signal_id] = record
        self.stats['total_signals'] += 1
        self.stats['pending'] += 1
        
        return signal_id
    
    def update_signal(self, signal_id: str, current_price: float) -> Optional[SignalRecord]:
        """Обновить сигнал с текущей ценой"""
        if signal_id not in self.signals:
            return None
        
        record = self.signals[signal_id]
        old_result = record.result
        
        record.calculate_result(current_price)
        
        # Если результат изменился с PENDING
        if old_result == SignalResult.PENDING and record.result != SignalResult.PENDING:
            record.exit_price = current_price
            record.exit_timestamp = int(time.time() * 1000)
            
            self.stats['pending'] -= 1
            self._update_stats(record)
            
            # Переместить в историю
            self.history.append(record)
            del self.signals[signal_id]
        
        return record
    
    def close_signal(
        self,
        signal_id: str,
        exit_price: float,
        result: SignalResult = None
    ) -> Optional[SignalRecord]:
        """Закрыть сигнал вручную"""
        if signal_id not in self.signals:
            return None
        
        record = self.signals[signal_id]
        record.exit_price = exit_price
        record.exit_timestamp = int(time.time() * 1000)
        record.calculate_result(exit_price)
        
        if result:
            record.result = result
        
        self.stats['pending'] -= 1
        self._update_stats(record)
        
        self.history.append(record)
        del self.signals[signal_id]
        
        return record
    
    def _update_stats(self, record: SignalRecord):
        """Обновить статистику"""
        if record.result == SignalResult.WIN:
            self.stats['wins'] += 1
            self.stats['total_pnl_pct'] += record.pnl_pct
            if record.pnl_pct > self.stats['best_trade_pct']:
                self.stats['best_trade_pct'] = record.pnl_pct
                
        elif record.result == SignalResult.LOSS:
            self.stats['losses'] += 1
            self.stats['total_pnl_pct'] += record.pnl_pct
            if record.pnl_pct < self.stats['worst_trade_pct']:
                self.stats['worst_trade_pct'] = record.pnl_pct
                
        elif record.result == SignalResult.BREAKEVEN:
            self.stats['breakevens'] += 1
            
        elif record.result == SignalResult.EXPIRED:
            self.stats['expired'] += 1
        
        # Пересчитать метрики
        total_closed = self.stats['wins'] + self.stats['losses']
        if total_closed > 0:
            self.stats['win_rate'] = (self.stats['wins'] / total_closed) * 100
            
            # Средние
            wins = [r for r in self.history if r.result == SignalResult.WIN]
            losses = [r for r in self.history if r.result == SignalResult.LOSS]
            
            if wins:
                self.stats['avg_win_pct'] = sum(r.pnl_pct for r in wins) / len(wins)
            if losses:
                self.stats['avg_loss_pct'] = sum(r.pnl_pct for r in losses) / len(losses)
            
            # Profit Factor
            gross_profit = sum(r.pnl_pct for r in wins) if wins else 0
            gross_loss = abs(sum(r.pnl_pct for r in losses)) if losses else 0
            self.stats['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else 0
    
    def get_active_signals(self) -> List[SignalRecord]:
        """Получить активные сигналы"""
        return list(self.signals.values())
    
    def format_stats(self) -> str:
        """Форматировать статистику"""
        s = self.stats
        
        # Emoji для винрейта
        wr = s['win_rate']
        if wr >= 60:
            wr_emoji = "🟢"
        elif wr >= 50:
            wr_emoji = "🟡"
        else:
            wr_emoji = "🔴"
        
        # Emoji для PnL
        pnl = s['total_pnl_pct']
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        
        msg = f"""
📊 <b>СТАТИСТИКА СИГНАЛОВ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 <b>ОБЩАЯ СТАТИСТИКА:</b>
├ Всего сигналов: {s['total_signals']}
├ ✅ Винов: {s['wins']}
├ ❌ Лоссов: {s['losses']}
├ ⏳ В ожидании: {s['pending']}
└ ⌛ Истекло: {s['expired']}

{wr_emoji} <b>ВИНРЕЙТ:</b> {s['win_rate']:.1f}%

{pnl_emoji} <b>ОБЩИЙ P&L:</b> {s['total_pnl_pct']:+.2f}%

💰 <b>СРЕДНИЕ:</b>
├ Ср. вин: {s['avg_win_pct']:+.2f}%
├ Ср. лосс: {s['avg_loss_pct']:+.2f}%
└ Profit Factor: {s['profit_factor']:.2f}

🏆 <b>ЛУЧШАЯ СДЕЛКА:</b> {s['best_trade_pct']:+.2f}%
💀 <b>ХУДШАЯ СДЕЛКА:</b> {s['worst_trade_pct']:+.2f}%
"""
        return msg.strip()


class TelegramAlertFormatter:
    """Форматтер красивых Telegram алертов"""
    
    @staticmethod
    def format_pump_detected(
        symbol: str,
        price: float,
        price_change_pct: float,
        volume_ratio: float,
        score: int,
        rsi: float
    ) -> str:
        """Алерт о детекте пампа"""
        
        # Emoji по силе пампа
        if price_change_pct >= 20:
            pump_emoji = "🚀🚀🚀"
            strength = "МЕГА"
        elif price_change_pct >= 10:
            pump_emoji = "🚀🚀"
            strength = "СИЛЬНЫЙ"
        elif price_change_pct >= 5:
            pump_emoji = "🚀"
            strength = "СРЕДНИЙ"
        else:
            pump_emoji = "📈"
            strength = "СЛАБЫЙ"
        
        msg = f"""
{pump_emoji} <b>ПАМП ОБНАРУЖЕН!</b> {pump_emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Токен:</b> {symbol}
💰 <b>Цена:</b> ${price:.8f}

📊 <b>МЕТРИКИ:</b>
├ 📈 Рост: <b>{price_change_pct:+.1f}%</b>
├ 📊 Объём: <b>×{volume_ratio:.1f}</b> от среднего
├ 📉 RSI: <b>{rsi:.0f}</b>
└ 🎯 Скор: <b>{score}/100</b>

⚡ <b>СИЛА:</b> {strength}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return msg.strip()
    
    @staticmethod
    def format_distribution_detected(
        symbol: str,
        price: float,
        buy_sell_ratio: float,
        confidence: int,
        phase: str
    ) -> str:
        """Алерт о детекте распределения (сигнал на ШОРТ)"""
        
        if phase == "DUMPING":
            alert_emoji = "🚨🚨🚨"
            urgency = "КРИТИЧЕСКАЯ"
            action = "ШОРТ СЕЙЧАС!"
        else:
            alert_emoji = "⚠️⚠️"
            urgency = "ВЫСОКАЯ"
            action = "ГОТОВЬ ШОРТ"
        
        msg = f"""
{alert_emoji} <b>РАСПРЕДЕЛЕНИЕ ОБНАРУЖЕНО!</b> {alert_emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Токен:</b> {symbol}
💰 <b>Цена:</b> ${price:.8f}

🔴 <b>СИГНАЛ: SHORT</b>

📊 <b>ИНДИКАТОРЫ:</b>
├ 📉 Buy/Sell Ratio: <b>{buy_sell_ratio:.2f}</b>
├ 🎯 Уверенность: <b>{confidence}%</b>
└ 📍 Фаза: <b>{phase}</b>

🎬 <b>ДЕЙСТВИЕ:</b> {action}
⚡ <b>СРОЧНОСТЬ:</b> {urgency}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return msg.strip()
    
    @staticmethod
    def format_exit_signal(
        symbol: str,
        price: float,
        action: str,
        urgency: str,
        reason: str,
        pnl_pct: float = 0
    ) -> str:
        """Алерт на выход из позиции"""
        
        if urgency == "CRITICAL":
            emoji = "🚨🚨🚨"
            urgency_ru = "КРИТИЧЕСКАЯ"
        elif urgency == "HIGH":
            emoji = "⚠️⚠️"
            urgency_ru = "ВЫСОКАЯ"
        else:
            emoji = "ℹ️"
            urgency_ru = "СРЕДНЯЯ"
        
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        
        msg = f"""
{emoji} <b>СИГНАЛ НА ВЫХОД!</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Токен:</b> {symbol}
💰 <b>Цена:</b> ${price:.8f}

🎬 <b>ДЕЙСТВИЕ:</b> {action}
⚡ <b>СРОЧНОСТЬ:</b> {urgency_ru}

📝 <b>ПРИЧИНА:</b>
{reason}

{pnl_emoji} <b>P&L:</b> {pnl_pct:+.2f}%

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return msg.strip()
    
    @staticmethod
    def format_signal_result(
        symbol: str,
        result: SignalResult,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        duration_minutes: int
    ) -> str:
        """Алерт о результате сигнала"""
        
        if result == SignalResult.WIN:
            emoji = "✅🎉"
            result_text = "ПРОФИТ"
        elif result == SignalResult.LOSS:
            emoji = "❌😢"
            result_text = "ЛОСС"
        else:
            emoji = "➖"
            result_text = "БЕЗУБЫТОК"
        
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        
        msg = f"""
{emoji} <b>СДЕЛКА ЗАКРЫТА: {result_text}</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Токен:</b> {symbol}

📊 <b>РЕЗУЛЬТАТ:</b>
├ Вход: ${entry_price:.8f}
├ Выход: ${exit_price:.8f}
├ {pnl_emoji} P&L: <b>{pnl_pct:+.2f}%</b>
└ ⏱ Время: {duration_minutes} мин

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return msg.strip()

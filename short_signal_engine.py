"""
MEXC Pump Monitor - Short Signal Engine
Optimized short entry calculation and signal tracking
"""

import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class SignalResult(Enum):
    """Signal result"""
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    EXPIRED = "EXPIRED"


@dataclass
class ShortEntry:
    """Short entry points"""
    symbol: str
    timestamp: int
    current_price: float
    
    # Entry zone
    entry_ideal: float
    entry_zone_low: float
    entry_zone_high: float
    
    # Stop-loss levels
    stop_loss: float
    stop_loss_tight: float
    stop_loss_wide: float
    
    # Take-profit levels
    tp1: float
    tp2: float
    tp3: float
    
    # Key levels
    ema20: float = 0
    ema50: float = 0
    support_level: float = 0
    
    # Risk/Reward
    risk_reward_ratio: float = 0
    risk_pct: float = 0
    reward_pct: float = 0
    
    # Recommendations
    position_size_pct: float = 0
    leverage_recommended: int = 1
    confidence: int = 50
    
    # Additional fields for Telegram formatting
    rsi: float = 0
    oi: float = 0
    reason: str = ""
    
    def format_telegram(self) -> str:
        """Format for Telegram"""
        price = self.current_price
        
        return f"""
📉 <b>SHORT SETUP: {self.symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>EXITS:</b>
├ 📈 Entry: <b>{self.entry_ideal:.6f}</b>
├ 🛑 Stop: <b>{self.stop_loss:.6f}</b>
├ 💹 TP1 (EMA20): <b>{self.tp1:.6f}</b>
└ 💹 TP2 (EMA50): <b>{self.tp2:.6f}</b>

📊 <b>TECHNICALS:</b>
├ 📉 RSI: <b>{self.rsi:.1f}</b>
├ 📈 OI: <b>{self.oi:,.0f}</b>
└ 📝 REASON: <b>{self.reason}</b>

⚙️ <b>EXECUTION:</b>
├ ⚖️ Risk/Reward: 1:{self.risk_reward_ratio:.1f}
├ 📊 Size: {self.position_size_pct:.0f}% of deposit
├ 💪 Leverage: {self.leverage_recommended}x
└ 🎯 Confidence: {self.confidence}%
""".strip()


@dataclass 
class SignalRecord:
    """Signal record for tracking"""
    signal_id: str
    symbol: str
    signal_type: str
    timestamp: int
    entry_price: float
    stop_loss: float
    take_profit: float
    
    result: SignalResult = SignalResult.PENDING
    exit_price: float = 0
    exit_timestamp: int = 0
    pnl_pct: float = 0
    pnl_usd: float = 0
    confidence: int = 50
    reasoning: str = ""
    
    def calculate_result(self, current_price: float):
        """Calculate result based on current price"""
        if self.signal_type == "SHORT":
            self.pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
            if current_price >= self.stop_loss:
                self.result = SignalResult.LOSS
            elif current_price <= self.take_profit:
                self.result = SignalResult.WIN
        else:
            self.pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
            if current_price <= self.stop_loss:
                self.result = SignalResult.LOSS
            elif current_price >= self.take_profit:
                self.result = SignalResult.WIN


class ShortEntryCalculator:
    """Short entry calculator - optimized"""
    
    # Confidence boost thresholds
    RSI_BOOSTS = [(80, 25), (70, 15), (60, 5)]
    VOLUME_BOOSTS = [(5, 15), (3, 10)]
    CHANGE_BOOSTS = [(20, 15), (10, 10)]
    MANIP_BOOSTS = [(70, 15), (50, 10)]
    
    # Position sizing by confidence
    SIZING = [
        (80, 10, 5),  # confidence >= 80: 10% size, 5x leverage
        (70, 7, 3),
        (60, 5, 2),
        (0, 3, 1)
    ]
    
    def __init__(self):
        self.stats = {'entries_calculated': 0}
    
    async def analyze_orderbook(self, client, symbol: str, current_price: float) -> tuple[bool, float]:
        """
        Analyze orderbook for resistance above current price.
        
        Returns:
            (has_resistance, density_boost) - density_boost is 0-15 confidence
        """
        try:
            # Fetch orderbook from client
            orderbook = await client.get_order_book(symbol, depth=20)
            if not orderbook or 'asks' not in orderbook:
                return False, 0
            
            asks = orderbook.get('asks', [])
            if not asks:
                return False, 0
            
            # Calculate density above current price (resistance)
            # asks format: [[price, quantity], ...]
            resistance_zone = current_price * 1.02  # 2% above
            total_qty = 0
            resistance_qty = 0
            
            for price_str, qty_str in asks[:20]:
                price = float(price_str)
                qty = float(qty_str)
                total_qty += qty
                
                if price <= resistance_zone:
                    resistance_qty += qty
            
            if total_qty == 0:
                return False, 0
            
            # Calculate density ratio
            density_pct = (resistance_qty / total_qty) * 100
            
            # Boost confidence if high resistance
            if density_pct >= 60:  # 60%+ of asks in resistance zone
                return True, 15  # Strong resistance → +15 confidence
            elif density_pct >= 40:
                return True, 10  # Medium resistance → +10 confidence
            elif density_pct >= 25:
                return True, 5   # Weak resistance → +5 confidence
            
            return False, 0
            
        except Exception as e:
            logger.debug(f"Orderbook analysis error for {symbol}: {e}")
            return False, 0
    
    def analyze_pump(
        self,
        symbol: str,
        current_price: float,
        rsi: float = 50,
        volume_spike: float = 0,
        price_change: float = 0,
        oi: float = 0,
        reason: str = ""
    ) -> Dict:
        """Compatibility method for SystemOrchestrator"""
        # HARD FILTER: RSI minimum 65
        if rsi < 65:
            logger.debug(f"Blocked SHORT {symbol}: RSI {rsi:.1f} < 65 (not overbought)")
            return {
                'recommendation': 'SKIP',
                'confidence': 0,
                'reason': f'RSI too low ({rsi:.1f} < 65)'
            }
        
        # Determine internal reasoning if not provided
        if not reason:
            if rsi > 75:
                reason = "Overbought (RSI > 75)"
            elif oi > 1000000:
                reason = "High Open Interest Spike"
            else:
                reason = "Technical Fade (No News)"

        # Call modern calculation
        entry_data = self.calculate_entry(
            symbol=symbol,
            current_price=current_price,
            ema20=current_price * 0.98,
            ema50=current_price * 0.95,
            rsi=rsi,
            atr=current_price * 0.02,
            volume_ratio=2.0 if volume_spike > 0 else 1.0,
            price_change_pct=price_change or 5.0,
            oi=oi,
            reason=reason
        )
        
        # HARD FILTER: Minimum confidence 60%
        if entry_data.confidence < 60:
            logger.debug(f"Blocked SHORT {symbol}: confidence {entry_data.confidence}% < 60%")
            return {
                'recommendation': 'SKIP',
                'confidence': entry_data.confidence,
                'reason': f'Low confidence ({entry_data.confidence}%)'
            }
        
        return {
            'recommendation': 'SHORT',
            'entry_price': entry_data.entry_ideal,
            'stop_loss': entry_data.stop_loss,
            'confidence': entry_data.confidence,
            'raw': entry_data
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
        manipulation_confidence: int = 0,
        oi: float = 0,
        reason: str = ""
    ) -> ShortEntry:
        """Calculate optimal short entry points"""
        now = int(time.time() * 1000)
        price = current_price
        
        # Entry zone
        entry_ideal = price * 1.005
        entry_zone_low = price * 0.995
        entry_zone_high = price * 1.02
        
        # Stop-loss calculations
        atr_based = atr > 0
        stop_base = price + (atr * 1.5) if atr_based else price * 1.04
        stop_tight = min(price + atr, price * 1.025) if atr_based else price * 1.025
        stop_wide = price + (atr * 2) if atr_based else price * 1.05
        
        # Take-profit levels
        tp1 = min(ema20 * 1.01, price * 0.97)
        tp2 = min(ema50, price * 0.93) if ema50 > 0 else price * 0.93
        tp3 = max(support_level if support_level > 0 else price * 0.85, price * 0.85)
        
        # Risk/Reward
        risk_pct = ((stop_base - price) / price) * 100
        reward_pct = ((price - tp2) / price) * 100
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0
        
        # Confidence calculation
        confidence = 50
        
        # RSI boost (stricter thresholds)
        for threshold, boost in self.RSI_BOOSTS:
            if rsi >= threshold:
                confidence += boost
                break
        
        # Volume boost
        for threshold, boost in self.VOLUME_BOOSTS:
            if volume_ratio >= threshold:
                confidence += boost
                break
        
        # Price change boost
        for threshold, boost in self.CHANGE_BOOSTS:
            if price_change_pct >= threshold:
                confidence += boost
                break
        
        # Manipulation boost
        for threshold, boost in self.MANIP_BOOSTS:
            if manipulation_confidence >= threshold:
                confidence += boost
                break
        
        # OI penalty if no data
        if oi == 0 and rsi < 75:
            confidence -= 15  # Uncertainty penalty
        
        confidence = min(100, max(0, confidence))
        
        # Position sizing
        position_size, leverage = 3, 1
        for threshold, size, lev in self.SIZING:
            if confidence >= threshold:
                position_size, leverage = size, lev
                break
        
        # R:R adjustment
        if rr_ratio < 1.5:
            position_size = int(position_size * 0.5)
            leverage = 1
        
        self.stats['entries_calculated'] += 1
        
        return ShortEntry(
            symbol=symbol,
            timestamp=now,
            current_price=price,
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
            confidence=confidence,
            oi=oi,
            reason=reason,
            rsi=rsi
        )


class SignalTracker:
    """Signal effectiveness tracker - optimized"""
    
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
        """Add signal for tracking"""
        signal_id = f"{symbol}_{int(time.time())}"
        
        self.signals[signal_id] = SignalRecord(
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
        
        self.stats['total_signals'] += 1
        self.stats['pending'] += 1
        
        return signal_id
    
    def update_signal(self, signal_id: str, current_price: float) -> Optional[SignalRecord]:
        """Update signal with current price"""
        record = self.signals.get(signal_id)
        if not record:
            return None
        
        old_result = record.result
        record.calculate_result(current_price)
        
        if old_result == SignalResult.PENDING and record.result != SignalResult.PENDING:
            record.exit_price = current_price
            record.exit_timestamp = int(time.time() * 1000)
            
            self.stats['pending'] -= 1
            self._update_stats(record)
            
            self.history.append(record)
            del self.signals[signal_id]
        
        return record
    
    def close_signal(
        self,
        signal_id: str,
        exit_price: float,
        result: SignalResult = None
    ) -> Optional[SignalRecord]:
        """Close signal manually"""
        record = self.signals.get(signal_id)
        if not record:
            return None
        
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
        """Update statistics"""
        s = self.stats
        
        if record.result == SignalResult.WIN:
            s['wins'] += 1
            s['total_pnl_pct'] += record.pnl_pct
            s['best_trade_pct'] = max(s['best_trade_pct'], record.pnl_pct)
        elif record.result == SignalResult.LOSS:
            s['losses'] += 1
            s['total_pnl_pct'] += record.pnl_pct
            s['worst_trade_pct'] = min(s['worst_trade_pct'], record.pnl_pct)
        elif record.result == SignalResult.BREAKEVEN:
            s['breakevens'] += 1
        elif record.result == SignalResult.EXPIRED:
            s['expired'] += 1
        
        # Recalculate metrics
        total_closed = s['wins'] + s['losses']
        if total_closed > 0:
            s['win_rate'] = (s['wins'] / total_closed) * 100
            
            wins = [r for r in self.history if r.result == SignalResult.WIN]
            losses = [r for r in self.history if r.result == SignalResult.LOSS]
            
            s['avg_win_pct'] = sum(r.pnl_pct for r in wins) / len(wins) if wins else 0
            s['avg_loss_pct'] = sum(r.pnl_pct for r in losses) / len(losses) if losses else 0
            
            gross_profit = sum(r.pnl_pct for r in wins) if wins else 0
            gross_loss = abs(sum(r.pnl_pct for r in losses)) if losses else 0
            s['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else 0
    
    def get_active_signals(self) -> List[SignalRecord]:
        """Get active signals"""
        return list(self.signals.values())
    
    def format_stats(self) -> str:
        """Format statistics"""
        s = self.stats
        wr_emoji = "🟢" if s['win_rate'] >= 60 else "🟡" if s['win_rate'] >= 50 else "🔴"
        pnl_emoji = "🟢" if s['total_pnl_pct'] >= 0 else "🔴"
        
        return f"""
📊 <b>SIGNAL STATISTICS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 <b>OVERVIEW:</b>
├ Total: {s['total_signals']}
├ ✅ Wins: {s['wins']}
├ ❌ Losses: {s['losses']}
├ ⏳ Pending: {s['pending']}
└ ⌛ Expired: {s['expired']}

{wr_emoji} <b>WIN RATE:</b> {s['win_rate']:.1f}%

{pnl_emoji} <b>TOTAL P&L:</b> {s['total_pnl_pct']:+.2f}%

💰 <b>AVERAGES:</b>
├ Avg Win: {s['avg_win_pct']:+.2f}%
├ Avg Loss: {s['avg_loss_pct']:+.2f}%
└ Profit Factor: {s['profit_factor']:.2f}

🏆 <b>BEST:</b> {s['best_trade_pct']:+.2f}%
💀 <b>WORST:</b> {s['worst_trade_pct']:+.2f}%
""".strip()


class TelegramAlertFormatter:
    """Telegram alert formatter - optimized as static methods"""
    
    @staticmethod
    def format_pump_detected(
        symbol: str,
        price: float,
        price_change_pct: float,
        volume_ratio: float,
        score: int,
        rsi: float,
        market_cap: str = "N/A"
    ) -> str:
        """Pump detected alert"""
        if price_change_pct >= 20:
            emoji, strength = "🚀🚀🚀", "MEGA"
        elif price_change_pct >= 10:
            emoji, strength = "🚀🚀", "STRONG"
        elif price_change_pct >= 5:
            emoji, strength = "🚀", "MEDIUM"
        else:
            emoji, strength = "📈", "WEAK"
        
        return f"""
{emoji} <b>PUMP DETECTED!</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Token:</b> {symbol}
💰 <b>Price:</b> ${price:.8f}

📊 <b>METRICS:</b>
├ 📈 Change: <b>{price_change_pct:+.1f}%</b>
├ 📊 Volume: <b>×{volume_ratio:.1f}</b>
├ 💎 Cap: <b>{market_cap}</b>
├ 📉 RSI: <b>{rsi:.0f}</b>
└ 🎯 Score: <b>{score}/100</b>

⚡ <b>STRENGTH:</b> {strength}
⏰ {datetime.now().strftime('%H:%M:%S')}
""".strip()
    
    @staticmethod
    def format_distribution_detected(
        symbol: str,
        price: float,
        buy_sell_ratio: float,
        confidence: int,
        phase: str,
        oi: float = 0,
        reason: str = "Technical overextension"
    ) -> str:
        """Distribution detected alert (SHORT signal)"""
        if phase == "DUMPING":
            emoji, urgency, action = "🚨🚨🚨", "CRITICAL", "SHORT NOW!"
        else:
            emoji, urgency, action = "⚠️⚠️", "HIGH", "PREPARE SHORT"
        
        return f"""
{emoji} <b>DISTRIBUTION DETECTED!</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Token:</b> {symbol}
💰 <b>Price:</b> ${price:.8f}

🔴 <b>SIGNAL: SHORT</b>

📊 <b>INDICATORS:</b>
├ 📉 Buy/Sell: <b>{buy_sell_ratio:.2f}</b>
├ 🎯 Confidence: <b>{confidence}%</b>
└ 📍 Phase: <b>{phase}</b>

🎬 <b>ACTION:</b> {action}
⚡ <b>URGENCY:</b> {urgency}
⏰ {datetime.now().strftime('%H:%M:%S')}
""".strip()
    
    @staticmethod
    def format_exit_signal(
        symbol: str,
        price: float,
        action: str,
        urgency: str,
        reason: str,
        pnl_pct: float = 0
    ) -> str:
        """Exit signal alert"""
        if urgency == "CRITICAL":
            emoji, urgency_str = "🚨🚨🚨", "CRITICAL"
        elif urgency == "HIGH":
            emoji, urgency_str = "⚠️⚠️", "HIGH"
        else:
            emoji, urgency_str = "ℹ️", "MEDIUM"
        
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        
        return f"""
{emoji} <b>EXIT SIGNAL!</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Token:</b> {symbol}
💰 <b>Price:</b> ${price:.8f}

🎬 <b>ACTION:</b> {action}
⚡ <b>URGENCY:</b> {urgency_str}

📝 <b>REASON:</b>
{reason}

{pnl_emoji} <b>P&L:</b> {pnl_pct:+.2f}%
⏰ {datetime.now().strftime('%H:%M:%S')}
""".strip()
    
    @staticmethod
    def format_signal_result(
        symbol: str,
        result: SignalResult,
        entry_price: float,
        exit_price: float,
        pnl_pct: float,
        duration_minutes: int
    ) -> str:
        """Signal result alert"""
        if result == SignalResult.WIN:
            emoji, result_text = "✅🎉", "PROFIT"
        elif result == SignalResult.LOSS:
            emoji, result_text = "❌😢", "LOSS"
        else:
            emoji, result_text = "➖", "BREAKEVEN"
        
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        
        return f"""
{emoji} <b>TRADE CLOSED: {result_text}</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>Token:</b> {symbol}

📊 <b>RESULT:</b>
├ Entry: ${entry_price:.8f}
├ Exit: ${exit_price:.8f}
├ {pnl_emoji} P&L: <b>{pnl_pct:+.2f}%</b>
└ ⏱ Duration: {duration_minutes} min

⏰ {datetime.now().strftime('%H:%M:%S')}
""".strip()

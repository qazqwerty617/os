"""
MEXC Pump Monitor - Position Sizing Calculator
Расчёт оптимального размера позиции на основе риска
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Уровни риска"""
    CONSERVATIVE = "conservative"  # 0.5% per trade
    MODERATE = "moderate"          # 1% per trade
    AGGRESSIVE = "aggressive"      # 2% per trade
    YOLO = "yolo"                  # 5% per trade


@dataclass
class PositionSize:
    """Результат расчёта позиции"""
    # Размеры
    position_usd: float
    position_qty: float
    leverage: int
    margin_required: float
    
    # Риск
    risk_usd: float
    risk_pct: float
    
    # Уровни
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    
    # R:R
    risk_reward_1: float
    risk_reward_2: float
    
    # Ликвидация
    liquidation_price: float
    distance_to_liq_pct: float
    
    # Warnings
    warnings: list = None
    
    def __post_init__(self):
        self.warnings = self.warnings or []


class PositionSizingCalculator:
    """
    📊 Position Sizing Calculator
    
    Расчёт размера позиции на основе:
    - Размера депозита
    - Допустимого риска
    - Stop-loss уровня
    - Плеча
    
    Поддерживает:
    - Kelly Criterion
    - Fixed Fractional
    - ATR-based sizing
    """
    
    # Risk percentages per level
    RISK_PERCENTAGES = {
        RiskLevel.CONSERVATIVE: 0.5,
        RiskLevel.MODERATE: 1.0,
        RiskLevel.AGGRESSIVE: 2.0,
        RiskLevel.YOLO: 5.0
    }
    
    # Max leverage recommendations
    MAX_LEVERAGE = {
        RiskLevel.CONSERVATIVE: 5,
        RiskLevel.MODERATE: 10,
        RiskLevel.AGGRESSIVE: 20,
        RiskLevel.YOLO: 50
    }
    
    def __init__(
        self,
        account_balance: float = 1000,
        risk_level: RiskLevel = RiskLevel.MODERATE,
        max_leverage: int = 20,
        max_position_pct: float = 25.0  # Max 25% of account per trade
    ):
        self.account_balance = account_balance
        self.risk_level = risk_level
        self.max_leverage = max_leverage
        self.max_position_pct = max_position_pct
        
        # Win rate for Kelly Criterion (can be updated based on history)
        self.win_rate = 0.55
        self.avg_win = 1.5  # Average R:R on wins
        self.avg_loss = 1.0  # Average R:R on losses
    
    def set_account_balance(self, balance: float):
        """Установить баланс аккаунта"""
        self.account_balance = balance
        logger.info(f"Account balance set to ${balance:,.2f}")
    
    def set_risk_level(self, level: RiskLevel):
        """Установить уровень риска"""
        self.risk_level = level
        logger.info(f"Risk level set to {level.value}")
    
    def update_win_rate(self, win_rate: float, avg_win: float = None, avg_loss: float = None):
        """Обновить win rate для Kelly"""
        self.win_rate = win_rate
        if avg_win:
            self.avg_win = avg_win
        if avg_loss:
            self.avg_loss = avg_loss
    
    def calculate_fixed_fractional(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float = None,
        leverage: int = None,
        is_short: bool = True
    ) -> PositionSize:
        """
        Fixed Fractional Position Sizing
        
        Рискуем фиксированным % от депозита на каждую сделку
        
        Args:
            entry_price: Цена входа
            stop_loss: Уровень стоп-лосса
            take_profit_1: Первая цель
            take_profit_2: Вторая цель (опционально)
            leverage: Плечо (если None - будет рассчитано)
            is_short: True для шортов
        
        Returns:
            PositionSize с полным расчётом
        """
        warnings = []
        
        # Get risk percentage
        risk_pct = self.RISK_PERCENTAGES[self.risk_level]
        risk_usd = self.account_balance * (risk_pct / 100)
        
        # Calculate SL distance
        if is_short:
            sl_distance_pct = ((stop_loss - entry_price) / entry_price) * 100
        else:
            sl_distance_pct = ((entry_price - stop_loss) / entry_price) * 100
        
        if sl_distance_pct <= 0:
            warnings.append("⚠️ Invalid stop loss level")
            sl_distance_pct = 3.0  # Default 3%
        
        # Calculate position size: Risk = Position * SL%
        # Position = Risk / SL%
        position_usd = risk_usd / (sl_distance_pct / 100)
        
        # Apply max position limit
        max_position = self.account_balance * (self.max_position_pct / 100)
        if position_usd > max_position:
            position_usd = max_position
            warnings.append(f"⚠️ Position capped at {self.max_position_pct}% of account")
        
        # Calculate or validate leverage
        if leverage is None:
            # Calculate required leverage
            leverage = max(1, int(position_usd / (self.account_balance * 0.1)))
            leverage = min(leverage, self.max_leverage)
        else:
            leverage = min(leverage, self.max_leverage)
        
        # Calculate margin required
        margin_required = position_usd / leverage
        
        # Check if we have enough margin
        if margin_required > self.account_balance:
            # Reduce position
            margin_required = self.account_balance * 0.9  # Use 90% max
            position_usd = margin_required * leverage
            warnings.append("⚠️ Position reduced due to margin requirements")
        
        # Calculate quantity
        position_qty = position_usd / entry_price
        
        # Calculate R:R ratios
        if is_short:
            tp1_distance = entry_price - take_profit_1
            tp2_distance = entry_price - take_profit_2 if take_profit_2 else tp1_distance * 2
            sl_distance = stop_loss - entry_price
        else:
            tp1_distance = take_profit_1 - entry_price
            tp2_distance = take_profit_2 - entry_price if take_profit_2 else tp1_distance * 2
            sl_distance = entry_price - stop_loss
        
        rr_1 = abs(tp1_distance / sl_distance) if sl_distance > 0 else 0
        rr_2 = abs(tp2_distance / sl_distance) if sl_distance > 0 else 0
        
        if rr_1 < 1.0:
            warnings.append(f"⚠️ Low R:R ratio ({rr_1:.2f})")
        
        # Calculate liquidation price
        # For shorts: Liq = Entry * (1 + 1/leverage - maintenance margin)
        # Simplified: Liq ≈ Entry * (1 + 0.9/leverage)
        maint_margin = 0.005  # 0.5% maintenance
        if is_short:
            liq_price = entry_price * (1 + (1 - maint_margin) / leverage)
        else:
            liq_price = entry_price * (1 - (1 - maint_margin) / leverage)
        
        distance_to_liq = abs((liq_price - entry_price) / entry_price) * 100
        
        if distance_to_liq < sl_distance_pct * 1.5:
            warnings.append("⚠️ Stop loss close to liquidation!")
        
        # Take profit 2 if not provided
        if take_profit_2 is None:
            if is_short:
                take_profit_2 = entry_price - (sl_distance * 3)
            else:
                take_profit_2 = entry_price + (sl_distance * 3)
        
        return PositionSize(
            position_usd=round(position_usd, 2),
            position_qty=round(position_qty, 6),
            leverage=leverage,
            margin_required=round(margin_required, 2),
            risk_usd=round(risk_usd, 2),
            risk_pct=risk_pct,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            risk_reward_1=round(rr_1, 2),
            risk_reward_2=round(rr_2, 2),
            liquidation_price=round(liq_price, 6),
            distance_to_liq_pct=round(distance_to_liq, 2),
            warnings=warnings
        )
    
    def calculate_kelly(
        self,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        win_rate: float = None,
        is_short: bool = True
    ) -> float:
        """
        Kelly Criterion Position Sizing
        
        Формула: f* = (p * b - q) / b
        где:
        - p = вероятность выигрыша
        - q = 1 - p (вероятность проигрыша)
        - b = отношение выигрыша к проигрышу (R:R)
        
        Returns:
            Optimal fraction of bankroll to bet (0-1)
        """
        win_rate = win_rate or self.win_rate
        
        # Calculate R:R
        if is_short:
            win_amount = entry_price - take_profit
            loss_amount = stop_loss - entry_price
        else:
            win_amount = take_profit - entry_price
            loss_amount = entry_price - stop_loss
        
        if loss_amount <= 0:
            return 0
        
        b = abs(win_amount / loss_amount)  # R:R ratio
        p = win_rate
        q = 1 - p
        
        # Kelly formula
        kelly = (p * b - q) / b
        
        # Half Kelly for safety
        half_kelly = kelly / 2
        
        # Clamp to reasonable range
        return max(0, min(0.25, half_kelly))  # Max 25%
    
    def calculate_atr_based(
        self,
        entry_price: float,
        atr: float,
        atr_multiplier: float = 2.0,
        is_short: bool = True
    ) -> Tuple[float, float, float]:
        """
        ATR-based Stop Loss and Position Sizing
        
        Args:
            entry_price: Цена входа
            atr: Average True Range
            atr_multiplier: Множитель ATR для SL
            is_short: True для шортов
        
        Returns:
            (stop_loss, take_profit_1, take_profit_2)
        """
        sl_distance = atr * atr_multiplier
        
        if is_short:
            stop_loss = entry_price + sl_distance
            take_profit_1 = entry_price - (sl_distance * 1.5)
            take_profit_2 = entry_price - (sl_distance * 3.0)
        else:
            stop_loss = entry_price - sl_distance
            take_profit_1 = entry_price + (sl_distance * 1.5)
            take_profit_2 = entry_price + (sl_distance * 3.0)
        
        return stop_loss, take_profit_1, take_profit_2
    
    def calculate_from_signal(self, signal: dict) -> PositionSize:
        """
        Рассчитать позицию из сигнала
        
        Args:
            signal: Сигнал с полями entry_price, stop_loss, take_profit_1, etc.
        
        Returns:
            PositionSize
        """
        return self.calculate_fixed_fractional(
            entry_price=signal.get('entry_price', signal.get('price')),
            stop_loss=signal.get('stop_loss'),
            take_profit_1=signal.get('take_profit_1'),
            take_profit_2=signal.get('take_profit_2'),
            leverage=signal.get('leverage'),
            is_short=signal.get('is_short', True)
        )
    
    def format_position(self, pos: PositionSize) -> str:
        """
        Форматировать позицию для отображения
        """
        warnings_text = "\n".join(pos.warnings) if pos.warnings else ""
        
        return f"""
📊 <b>POSITION SIZING</b>

💰 <b>Position:</b> ${pos.position_usd:,.2f}
📦 <b>Quantity:</b> {pos.position_qty:,.6f}
⚡ <b>Leverage:</b> {pos.leverage}x
🔒 <b>Margin:</b> ${pos.margin_required:,.2f}

⚠️ <b>Risk:</b> ${pos.risk_usd:,.2f} ({pos.risk_pct}%)

📍 <b>Entry:</b> ${pos.entry_price:.6f}
🛑 <b>Stop Loss:</b> ${pos.stop_loss:.6f}
🎯 <b>TP1:</b> ${pos.take_profit_1:.6f} (R:R {pos.risk_reward_1})
🎯 <b>TP2:</b> ${pos.take_profit_2:.6f} (R:R {pos.risk_reward_2})

💀 <b>Liquidation:</b> ${pos.liquidation_price:.6f} ({pos.distance_to_liq_pct}% away)

{warnings_text}
"""
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            'account_balance': self.account_balance,
            'risk_level': self.risk_level.value,
            'risk_pct': self.RISK_PERCENTAGES[self.risk_level],
            'max_leverage': self.max_leverage,
            'max_position_pct': self.max_position_pct,
            'win_rate': self.win_rate,
            'kelly_fraction': self.calculate_kelly(100, 104, 94)  # Example
        }

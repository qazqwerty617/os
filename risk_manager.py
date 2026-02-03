"""
MEXC Pump Monitor - Risk Manager
Position sizing, risk calculation, and portfolio management
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk levels"""
    CONSERVATIVE = "CONSERVATIVE"  # 0.5% per trade
    MODERATE = "MODERATE"          # 1% per trade
    AGGRESSIVE = "AGGRESSIVE"      # 2% per trade
    DEGEN = "DEGEN"               # 5% per trade (not recommended)


@dataclass
class TradeSetup:
    """Complete trade setup with risk calculations"""
    symbol: str
    
    # Entry
    entry_price: float
    entry_type: str  # "MARKET", "LIMIT"
    
    # Exits
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: Optional[float] = None
    
    # Risk metrics
    risk_pct: float = 0  # Risk as % of entry
    reward_1_pct: float = 0
    reward_2_pct: float = 0
    risk_reward_1: float = 0
    risk_reward_2: float = 0
    
    # Position sizing
    position_size_usd: float = 0
    position_size_contracts: float = 0
    leverage: int = 1
    
    # Extra info
    signal_score: int = 0
    signal_quality: str = ""
    notes: List[str] = field(default_factory=list)
    
    def calculate_metrics(self):
        """Calculate risk/reward metrics"""
        # Risk
        self.risk_pct = abs((self.stop_loss - self.entry_price) / self.entry_price) * 100
        
        # Rewards
        self.reward_1_pct = abs((self.take_profit_1 - self.entry_price) / self.entry_price) * 100
        self.reward_2_pct = abs((self.take_profit_2 - self.entry_price) / self.entry_price) * 100
        
        # R:R ratios
        if self.risk_pct > 0:
            self.risk_reward_1 = self.reward_1_pct / self.risk_pct
            self.risk_reward_2 = self.reward_2_pct / self.risk_pct
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'risk_pct': self.risk_pct,
            'risk_reward_1': self.risk_reward_1,
            'risk_reward_2': self.risk_reward_2,
            'position_size_usd': self.position_size_usd,
            'leverage': self.leverage,
            'signal_score': self.signal_score,
            'notes': self.notes
        }


@dataclass
class ActivePosition:
    """Active position tracking"""
    symbol: str
    side: str  # "LONG" or "SHORT"
    entry_price: float
    entry_time: int
    size_contracts: float
    size_usd: float
    leverage: int
    
    # Targets
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    
    # Current state
    current_price: float = 0
    unrealized_pnl: float = 0
    unrealized_pnl_pct: float = 0
    
    # Partial closes
    tp1_hit: bool = False
    partial_closed_pct: float = 0
    
    def update(self, current_price: float):
        """Update position state"""
        self.current_price = current_price
        
        if self.side == "SHORT":
            self.unrealized_pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100
        else:
            self.unrealized_pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100
        
        self.unrealized_pnl = self.size_usd * (self.unrealized_pnl_pct / 100)
    
    def check_exits(self, current_price: float) -> Optional[str]:
        """Check if any exit conditions are met"""
        self.update(current_price)
        
        if self.side == "SHORT":
            if current_price >= self.stop_loss:
                return "STOP_LOSS"
            if current_price <= self.take_profit_1 and not self.tp1_hit:
                return "TAKE_PROFIT_1"
            if current_price <= self.take_profit_2:
                return "TAKE_PROFIT_2"
        else:
            if current_price <= self.stop_loss:
                return "STOP_LOSS"
            if current_price >= self.take_profit_1 and not self.tp1_hit:
                return "TAKE_PROFIT_1"
            if current_price >= self.take_profit_2:
                return "TAKE_PROFIT_2"
        
        return None


class RiskManager:
    """
    Risk management and position sizing
    """
    
    # Default risk per trade by level
    RISK_PER_TRADE = {
        RiskLevel.CONSERVATIVE: 0.005,  # 0.5%
        RiskLevel.MODERATE: 0.01,       # 1%
        RiskLevel.AGGRESSIVE: 0.02,     # 2%
        RiskLevel.DEGEN: 0.05           # 5%
    }
    
    # Max positions
    MAX_POSITIONS = {
        RiskLevel.CONSERVATIVE: 3,
        RiskLevel.MODERATE: 5,
        RiskLevel.AGGRESSIVE: 8,
        RiskLevel.DEGEN: 15
    }
    
    def __init__(
        self,
        capital: float = 10000,
        risk_level: RiskLevel = RiskLevel.MODERATE,
        max_leverage: int = 20
    ):
        self.capital = capital
        self.risk_level = risk_level
        self.max_leverage = max_leverage
        
        # Active positions
        self.positions: Dict[str, ActivePosition] = {}
        
        # Trade history
        self.trade_history: List[Dict] = []
        
        # Daily/weekly limits
        self.daily_loss_limit = capital * 0.05  # 5% daily max loss
        self.daily_loss = 0
        self.last_reset = time.time()
        
        # Stats
        self.stats = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0,
            'max_drawdown': 0
        }
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        signal_score: int = 70,
        leverage: int = None
    ) -> TradeSetup:
        """
        Calculate position size based on risk parameters
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            signal_score: Signal quality score (affects position size)
            leverage: Leverage to use (or auto-calculate)
        
        Returns:
            TradeSetup with position sizing
        """
        # Base risk per trade
        risk_pct = self.RISK_PER_TRADE[self.risk_level]
        
        # Adjust based on signal score (AI Confidence)
        # Dynamic Scaling: Linear interpolation from baseline
        # Baseline = 70 score. Every 1 point above = +2% risk size.
        if signal_score > 70:
            boost_factor = 1.0 + ((signal_score - 70) * 0.02) # e.g., 90 score = 1.4x risk
            risk_pct *= boost_factor
        elif signal_score < 60:
            risk_pct *= 0.5 # Penalty for low confidence
        
        # Max cap for safety (never risk more than 3x baseline)
        risk_pct = min(risk_pct, self.RISK_PER_TRADE[self.risk_level] * 3)
        
        # Calculate risk amount in USD
        risk_usd = self.capital * risk_pct
        
        # Calculate price risk
        price_risk_pct = abs((stop_loss - entry_price) / entry_price)
        
        if price_risk_pct == 0:
            return None
        
        # Calculate position size (without leverage)
        base_position_usd = risk_usd / price_risk_pct
        
        # Auto-calculate leverage if not provided
        if leverage is None:
            # Dynamic Leverage based on AI Confidence
            # 90+ Score = High Conviction = Higher Leverage
            if signal_score >= 90:
                leverage = min(self.max_leverage, 15)
            elif signal_score >= 80:
                leverage = min(self.max_leverage, 10)
            elif signal_score >= 70:
                leverage = min(self.max_leverage, 5)
            else:
                leverage = min(self.max_leverage, 2) # Safety first
        
        # Position size with leverage
        position_usd = base_position_usd * leverage
        
        # Cap at available capital
        max_position = self.capital * 0.5  # Max 50% of capital per position
        position_usd = min(position_usd, max_position)
        
        # Calculate contracts
        contracts = position_usd / entry_price
        
        # Calculate take profits
        risk_amount = abs(stop_loss - entry_price)
        
        # For shorts
        if stop_loss > entry_price:
            tp1 = entry_price - (risk_amount * 1.5)  # 1.5R
            tp2 = entry_price - (risk_amount * 2.5)  # 2.5R
            tp3 = entry_price - (risk_amount * 4)    # 4R
        else:
            tp1 = entry_price + (risk_amount * 1.5)
            tp2 = entry_price + (risk_amount * 2.5)
            tp3 = entry_price + (risk_amount * 4)
        
        setup = TradeSetup(
            symbol="",
            entry_price=entry_price,
            entry_type="LIMIT",
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            position_size_usd=position_usd,
            position_size_contracts=contracts,
            leverage=leverage,
            signal_score=signal_score
        )
        
        setup.calculate_metrics()
        
        # Add notes
        setup.notes.append(f"Risk: ${risk_usd:.2f} ({risk_pct*100:.2f}% of capital)")
        setup.notes.append(f"R:R = 1:{setup.risk_reward_1:.1f} / 1:{setup.risk_reward_2:.1f}")
        
        return setup
    
    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """Check if new position can be opened"""
        # Check max positions
        max_pos = self.MAX_POSITIONS[self.risk_level]
        if len(self.positions) >= max_pos:
            return False, f"max_positions_reached ({max_pos})"
        
        # Check if already in position
        if symbol in self.positions:
            return False, "already_in_position"
        
        # Check daily loss limit
        if self.daily_loss >= self.daily_loss_limit:
            return False, "daily_loss_limit_reached"
        
        return True, "ok"
    
    def open_position(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        size_usd: float,
        leverage: int,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float
    ) -> Optional[ActivePosition]:
        """Record opening a position"""
        can_open, reason = self.can_open_position(symbol)
        if not can_open:
            logger.warning(f"Cannot open position: {reason}")
            return None
        
        position = ActivePosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            entry_time=int(time.time() * 1000),
            size_contracts=size_usd / entry_price,
            size_usd=size_usd,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2
        )
        
        self.positions[symbol] = position
        self.stats['total_trades'] += 1
        
        logger.info(f"Opened {side} position: {symbol} @ {entry_price}, size=${size_usd:.0f}")
        
        return position
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: str = "manual"
    ) -> Optional[Dict]:
        """Record closing a position"""
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        position.update(exit_price)
        
        # Calculate PnL
        pnl = position.unrealized_pnl
        pnl_pct = position.unrealized_pnl_pct
        
        # Update stats
        self.stats['total_pnl'] += pnl
        
        if pnl > 0:
            self.stats['winning_trades'] += 1
        else:
            self.stats['losing_trades'] += 1
            self.daily_loss += abs(pnl)
        
        # Record trade
        trade = {
            'symbol': symbol,
            'side': position.side,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'size_usd': position.size_usd,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'duration_seconds': (int(time.time() * 1000) - position.entry_time) // 1000
        }
        
        self.trade_history.append(trade)
        del self.positions[symbol]
        
        logger.info(f"Closed {symbol}: PnL=${pnl:.2f} ({pnl_pct:+.2f}%) - {reason}")
        
        return trade
    
    def update_positions(self, prices: Dict[str, float]):
        """Update all positions with current prices"""
        for symbol, position in self.positions.items():
            if symbol in prices:
                exit_signal = position.check_exits(prices[symbol])
                
                if exit_signal:
                    self.close_position(symbol, prices[symbol], exit_signal)
    
    def get_portfolio_exposure(self) -> Dict:
        """Get current portfolio exposure"""
        total_exposure = sum(p.size_usd for p in self.positions.values())
        total_unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        
        return {
            'positions': len(self.positions),
            'total_exposure_usd': total_exposure,
            'total_unrealized_pnl': total_unrealized,
            'capital': self.capital,
            'exposure_pct': (total_exposure / self.capital) * 100 if self.capital > 0 else 0,
            'daily_loss': self.daily_loss,
            'daily_loss_remaining': self.daily_loss_limit - self.daily_loss
        }
    
    def get_stats(self) -> Dict:
        """Get trading statistics"""
        total = self.stats['winning_trades'] + self.stats['losing_trades']
        win_rate = (self.stats['winning_trades'] / total * 100) if total > 0 else 0
        
        return {
            **self.stats,
            'win_rate': win_rate,
            'avg_pnl': self.stats['total_pnl'] / total if total > 0 else 0,
            'positions_open': len(self.positions)
        }
    
    def reset_daily_limits(self):
        """Reset daily limits (call at midnight)"""
        self.daily_loss = 0
        self.last_reset = time.time()
        logger.info("Daily limits reset")



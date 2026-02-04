"""
MEXC Pump Monitor - Auto Trading Engine
Optimized signal execution engine
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionSide(Enum):
    """Position side"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class AutoOrder:
    """Auto order"""
    order_id: str
    symbol: str
    side: PositionSide
    entry_price: float
    quantity: float
    stop_loss: float
    take_profit1: float
    take_profit2: float = 0
    take_profit3: float = 0
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float = 0
    filled_quantity: float = 0
    created_at: datetime = None
    filled_at: datetime = None
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    signal_source: str = ""
    confidence: int = 50


@dataclass
class Position:
    """Open position"""
    symbol: str
    side: PositionSide
    entry_price: float
    quantity: float
    leverage: int = 1
    stop_loss_order_id: str = ""
    tp1_order_id: str = ""
    tp2_order_id: str = ""
    tp3_order_id: str = ""
    current_price: float = 0
    unrealized_pnl_pct: float = 0
    unrealized_pnl_usd: float = 0
    tp1_filled: bool = False
    tp2_filled: bool = False
    opened_at: datetime = None
    
    def update_pnl(self, current_price: float):
        """Update P&L"""
        self.current_price = current_price
        if self.side == PositionSide.SHORT:
            self.unrealized_pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
        else:
            self.unrealized_pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        self.unrealized_pnl_usd = self.quantity * self.entry_price * (self.unrealized_pnl_pct / 100)


class AutoTrader:
    """
    Optimized Auto Trader
    
    WARNING: Demo/testing only!
    Real trading requires API keys
    """
    
    INITIAL_BALANCE = 10000
    
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        demo_mode: bool = True,
        max_positions: int = 8,  # Увеличено для мемкоинов (было 5)
        max_position_size_pct: float = 15  # Увеличено для мемкоинов (было 10)
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.demo_mode = demo_mode
        self.max_positions = max_positions
        self.max_position_size_pct = max_position_size_pct
        
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, AutoOrder] = {}
        self.order_history: List[AutoOrder] = []
        
        self.demo_balance = self.INITIAL_BALANCE
        self.demo_pnl = 0
        
        self.on_order_filled: Optional[Callable] = None
        self.on_position_closed: Optional[Callable] = None
        
        self.stats = {
            'orders_placed': 0,
            'orders_filled': 0,
            'positions_opened': 0,
            'positions_closed': 0,
            'total_pnl_usd': 0,
            'total_pnl_pct': 0,
            'wins': 0,
            'losses': 0
        }
        
        mode = "DEMO" if demo_mode else "REAL"
        log_func = logger.info if demo_mode else logger.warning
        log_func(f"{'🎮' if demo_mode else '⚠️'} AutoTrader in {mode} mode")
    
    async def place_short_order(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit1: float,
        take_profit2: float = 0,
        take_profit3: float = 0,
        position_size_usd: float = 0,
        leverage: int = 1,
        confidence: int = 50,
        signal_source: str = ""
    ) -> Optional[AutoOrder]:
        """Place SHORT order"""
        if len(self.positions) >= self.max_positions:
            logger.warning(f"Position limit reached ({self.max_positions})")
            return None
        
        if symbol in self.positions:
            logger.warning(f"Position {symbol} already open")
            return None
        
        if position_size_usd <= 0:
            position_size_usd = self.demo_balance * (self.max_position_size_pct / 100)
        
        order = AutoOrder(
            order_id=f"ORD_{symbol}_{int(time.time())}",
            symbol=symbol,
            side=PositionSide.SHORT,
            entry_price=entry_price,
            quantity=position_size_usd / entry_price,
            stop_loss=stop_loss,
            take_profit1=take_profit1,
            take_profit2=take_profit2 or take_profit1 * 0.95,
            take_profit3=take_profit3 or take_profit1 * 0.90,
            created_at=datetime.now(),
            signal_source=signal_source,
            confidence=confidence
        )
        
        self.orders[order.order_id] = order
        self.stats['orders_placed'] += 1
        
        if self.demo_mode:
            await self._demo_fill_order(order)
        else:
            await self._place_real_order(order, leverage)
        
        logger.info(
            f"📝 SHORT: {symbol} @ ${entry_price:.8f} | "
            f"SL: ${stop_loss:.8f} | TP1: ${take_profit1:.8f}"
        )
        
        return order
    
    async def _demo_fill_order(self, order: AutoOrder):
        """Fill order in demo mode"""
        order.status = OrderStatus.FILLED
        order.filled_price = order.entry_price
        order.filled_quantity = order.quantity
        order.filled_at = datetime.now()
        
        self.stats['orders_filled'] += 1
        
        position = Position(
            symbol=order.symbol,
            side=order.side,
            entry_price=order.filled_price,
            quantity=order.filled_quantity,
            opened_at=datetime.now()
        )
        
        self.positions[order.symbol] = position
        self.stats['positions_opened'] += 1
        self.demo_balance -= order.filled_price * order.filled_quantity
        
        if self.on_order_filled:
            await self.on_order_filled(order)
    
    async def _place_real_order(self, order: AutoOrder, leverage: int):
        """Place real order via MEXC API"""
        logger.warning("Real trading not implemented yet")
    
    async def update_positions(self, prices: Dict[str, float]):
        """Update positions with current prices"""
        for symbol, position in list(self.positions.items()):
            if symbol in prices:
                position.update_pnl(prices[symbol])
                await self._check_exits(position, prices[symbol])
    
    async def _check_exits(self, position: Position, current_price: float):
        """Check SL/TP exits"""
        order = next((o for o in self.orders.values() if o.symbol == position.symbol), None)
        if not order:
            return
        
        close_reason, close_pct = None, 100
        
        if position.side == PositionSide.SHORT:
            if current_price >= order.stop_loss:
                close_reason = "STOP_LOSS"
            elif current_price <= order.take_profit1 and not position.tp1_filled:
                close_reason, close_pct = "TAKE_PROFIT_1", 30
                position.tp1_filled = True
            elif current_price <= order.take_profit2 and not position.tp2_filled:
                close_reason, close_pct = "TAKE_PROFIT_2", 40
                position.tp2_filled = True
            elif current_price <= order.take_profit3:
                close_reason = "TAKE_PROFIT_3"
        
        if close_reason:
            await self._close_position(position, current_price, close_reason, close_pct)
    
    async def _close_position(
        self,
        position: Position,
        exit_price: float,
        reason: str,
        close_pct: float = 100
    ):
        """Close position"""
        if position.side == PositionSide.SHORT:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
        else:
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        
        close_quantity = position.quantity * (close_pct / 100)
        pnl_usd = close_quantity * position.entry_price * (pnl_pct / 100)
        
        self.stats['total_pnl_usd'] += pnl_usd
        self.stats['wins' if pnl_pct > 0 else 'losses'] += 1
        
        self.demo_balance += close_quantity * exit_price + pnl_usd
        self.demo_pnl += pnl_usd
        
        emoji = '✅' if pnl_pct > 0 else '❌'
        logger.info(f"{emoji} Closed: {position.symbol} | P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) | {reason}")
        
        if close_pct >= 100 or reason == "STOP_LOSS":
            del self.positions[position.symbol]
            self.stats['positions_closed'] += 1
            
            if self.on_position_closed:
                await self.on_position_closed(position, pnl_pct, pnl_usd, reason)
        else:
            position.quantity -= close_quantity
    
    async def close_all_positions(self, prices: Dict[str, float]):
        """Close all positions"""
        for symbol, position in list(self.positions.items()):
            if symbol in prices:
                await self._close_position(position, prices[symbol], "MANUAL_CLOSE", 100)
    
    def get_open_positions(self) -> List[Position]:
        return list(self.positions.values())
    
    def format_status(self) -> str:
        """Format status message"""
        pnl_emoji = "🟢" if self.demo_pnl >= 0 else "🔴"
        wr = self.stats['wins'] / max(1, self.stats['wins'] + self.stats['losses']) * 100
        
        msg = f"""
🤖 <b>AUTO TRADER STATUS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>BALANCE:</b>
├ Initial: $10,000
├ Current: ${self.demo_balance:,.2f}
└ {pnl_emoji} P&L: ${self.demo_pnl:+,.2f}

📊 <b>POSITIONS:</b>
├ Open: {len(self.positions)}/{self.max_positions}
├ Total opened: {self.stats['positions_opened']}
└ Total closed: {self.stats['positions_closed']}

📈 <b>RESULTS:</b>
├ ✅ Wins: {self.stats['wins']}
├ ❌ Losses: {self.stats['losses']}
└ Win rate: {wr:.1f}%
"""
        
        if self.positions:
            msg += "\n<b>OPEN POSITIONS:</b>\n"
            for symbol, pos in self.positions.items():
                emoji = "🟢" if pos.unrealized_pnl_pct >= 0 else "🔴"
                msg += f"├ {symbol}: {emoji} {pos.unrealized_pnl_pct:+.2f}%\n"
        
        return msg.strip()
    
    def format_positions(self) -> str:
        """Format open positions"""
        if not self.positions:
            return "📭 No open positions"
        
        msg = "📊 <b>OPEN POSITIONS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for symbol, pos in self.positions.items():
            pnl_emoji = "🟢" if pos.unrealized_pnl_pct >= 0 else "🔴"
            side_emoji = "🔴" if pos.side == PositionSide.SHORT else "🟢"
            
            msg += f"""
{side_emoji} <b>{symbol}</b>
├ Side: {pos.side.value}
├ Entry: ${pos.entry_price:.8f}
├ Current: ${pos.current_price:.8f}
├ {pnl_emoji} P&L: {pos.unrealized_pnl_pct:+.2f}% (${pos.unrealized_pnl_usd:+.2f})
├ TP1: {'✅' if pos.tp1_filled else '⏳'}
└ TP2: {'✅' if pos.tp2_filled else '⏳'}
"""
        
        return msg.strip()

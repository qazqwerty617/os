"""
MEXC Pump Monitor - Auto Trading Engine
Optimized signal execution engine with Adaptive Exit Management
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from adaptive_exit_manager import exit_manager, AdaptiveExitPlan, ExitPhase

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
    leverage: int = 1
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
    """Open position with adaptive exit plan"""
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
    
    # Adaptive exit plan
    exit_plan: Optional[AdaptiveExitPlan] = None
    closed_portions: float = 0  # Сколько % позиции уже закрыто
    
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
    
    INITIAL_BALANCE = 100  # Demo balance
    
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        demo_mode: bool = True,
        initial_balance: float = 100.0,
        max_positions: int = 8,
        max_position_size_pct: float = 15,
        dashboard = None
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.demo_mode = demo_mode
        self.max_positions = max_positions
        self.max_position_size_pct = max_position_size_pct
        self.dashboard = dashboard
        
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, AutoOrder] = {}
        self.order_history: List[AutoOrder] = []
        
        self.demo_balance = initial_balance
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
            confidence=confidence,
            leverage=leverage
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
    
    async def _demo_fill_order(self, order: AutoOrder, price_history: List[float] = None, 
                               orderbook: dict = None, recent_trades: List[dict] = None):
        """Fill order in demo mode with adaptive exit plan"""
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
            opened_at=datetime.now(),
            leverage=order.leverage
        )
        
        # Create adaptive exit plan
        try:
            if price_history:
                exit_plan = await exit_manager.create_exit_plan(
                    symbol=order.symbol,
                    side=order.side.value,
                    entry_price=order.filled_price,
                    price_history=price_history,
                    orderbook=orderbook,
                    recent_trades=recent_trades
                )
                position.exit_plan = exit_plan
                
                # Update order with smart levels
                order.stop_loss = exit_plan.stop_loss.price
                if exit_plan.take_profits:
                    order.take_profit1 = exit_plan.take_profits[0].price
                    order.take_profit2 = exit_plan.take_profits[1].price if len(exit_plan.take_profits) > 1 else 0
                    order.take_profit3 = exit_plan.take_profits[2].price if len(exit_plan.take_profits) > 2 else 0
                
                logger.info(f"🎯 Adaptive exit plan created for {order.symbol}")
                logger.info(f"   Class: {exit_plan.asset_class.value}")
                logger.info(f"   SL: ${exit_plan.stop_loss.price:.6f} ({exit_plan.stop_loss.trigger_reason})")
                for i, tp in enumerate(exit_plan.take_profits):
                    logger.info(f"   TP{i+1}: ${tp.price:.6f} ({tp.size_pct}%)")
        except Exception as e:
            logger.warning(f"Could not create adaptive plan: {e}")
        
        self.positions[order.symbol] = position
        self.stats['positions_opened'] += 1
        self.demo_balance -= order.filled_price * order.filled_quantity * (1/order.leverage if hasattr(order, 'leverage') else 1)
        
        # Update Dashboard
        if self.dashboard:
            self.dashboard.update_stats(
                balance=self.demo_balance,
                total_trades=self.stats['orders_filled']
            )
        
        if self.on_order_filled:
            await self.on_order_filled(order)
    
    async def _place_real_order(self, order: AutoOrder, leverage: int):
        """Place real order via MEXC API"""
        logger.warning("Real trading not implemented yet")
    
    async def update_positions(self, prices: Dict[str, float], orderbook_data: Dict[str, dict] = None, 
                               recent_trades: Dict[str, List[dict]] = None):
        """Update positions with current prices and adaptive plans"""
        for symbol, position in list(self.positions.items()):
            if symbol in prices:
                position.update_pnl(prices[symbol])
                
                # Update adaptive exit plan if exists
                if position.exit_plan:
                    try:
                        await exit_manager.update_plan(
                            symbol=symbol,
                            current_price=prices[symbol],
                            orderbook=orderbook_data.get(symbol) if orderbook_data else None,
                            recent_trades=recent_trades.get(symbol) if recent_trades else None
                        )
                    except Exception as e:
                        logger.debug(f"Could not update exit plan for {symbol}: {e}")
                
                await self._check_exits(position, prices[symbol])
    
    async def _check_exits(self, position: Position, current_price: float):
        """Check SL/TP exits using adaptive exit plan"""
        
        # Use adaptive exit plan if available
        if position.exit_plan:
            exit_signal = exit_manager.check_exits(position.symbol, current_price)
            if exit_signal:
                exit_type, price, level = exit_signal
                close_pct = level.size_pct if level.size_pct > 0 else 100
                await self._close_position(position, current_price, exit_type, close_pct)
                return
            
            # Check for position adjustment (add/reduce)
            adjustment = exit_manager.get_position_adjustment(position.symbol, current_price)
            if adjustment:
                action, size = adjustment
                if action == 'ADD_POSITION':
                    logger.info(f"➕ {position.symbol}: Adding {size*100:.0f}% to position")
                    # Logic to add to position
                elif action == 'REDUCE_POSITION':
                    logger.info(f"➖ {position.symbol}: Reducing position by {size*100:.0f}%")
                    await self._close_position(position, current_price, 'EARLY_REDUCE', size * 100)
        
        # Fallback to basic order levels
        order = next((o for o in self.orders.values() if o.symbol == position.symbol), None)
        if not order:
            return
        
        close_reason, close_pct = None, 100
        
        if position.side == PositionSide.SHORT:
            if current_price >= order.stop_loss:
                close_reason = "STOP_LOSS"
            elif current_price <= order.take_profit1 and not position.tp1_filled:
                close_reason, close_pct = "TAKE_PROFIT_1", 40
                position.tp1_filled = True
                # Move stop loss to entry (breakeven) via exit_manager
                if position.exit_plan:
                    position.exit_plan.stop_loss.price = position.entry_price
                    position.exit_plan.stop_loss.trigger_reason = "Breakeven after TP1"
                order.stop_loss = position.entry_price
                logger.info(f"🔒 {position.symbol}: TP1 hit! 40% closed, stop moved to breakeven ({position.entry_price:.6f})")
            elif current_price <= order.take_profit2 and not position.tp2_filled:
                close_reason, close_pct = "TAKE_PROFIT_2", 35
                position.tp2_filled = True
                logger.info(f"🔒 {position.symbol}: TP2 hit! 35% closed")
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
        """Close position with adaptive tracking"""
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
        
        # Track closed portions
        position.closed_portions += close_pct
        
        # Update Dashboard
        if self.dashboard:
            self.dashboard.update_pnl(
                today=self.demo_pnl,
                all_time=self.stats['total_pnl_usd'],
                trades=self.stats['orders_filled']
            )
            self.dashboard.update_stats(
                balance=self.demo_balance,
                wins=self.stats['wins'],
                losses=self.stats['losses'],
                total_trades=self.stats['orders_filled']
            )
        
        emoji = '✅' if pnl_pct > 0 else '❌'
        logger.info(f"{emoji} Closed: {position.symbol} | {reason} | {close_pct:.0f}% | P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")
        
        if close_pct >= 100 or reason == "STOP_LOSS" or position.closed_portions >= 99:
            # Remove exit plan and position
            if position.exit_plan:
                exit_manager.remove_plan(position.symbol)
            del self.positions[position.symbol]
            self.stats['positions_closed'] += 1
            
            if self.on_position_closed:
                await self.on_position_closed(position, pnl_pct, pnl_usd, reason)
        else:
            position.quantity -= close_quantity
            logger.info(f"📊 {position.symbol}: Position reduced to {position.quantity:.4f} ({100-position.closed_portions:.0f}% remaining)")
    
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
├ Initial: ${self.INITIAL_BALANCE:,.0f}
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

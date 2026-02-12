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
from demo_persistence import load_demo_state, save_demo_state

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
    DEFAULT_LEVERAGE = 20  # Fixed leverage for all demo trades
    POSITION_SIZE_PCT = 5  # 5% of deposit per trade
    
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        demo_mode: bool = True,
        initial_balance: float = 100.0,
        max_positions: int = 8,
        max_position_size_pct: float = 5,
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
        
        if demo_mode:
            saved = load_demo_state()
            if saved:
                self.demo_balance = saved.get("demo_balance", initial_balance)
                self.demo_pnl = saved.get("demo_pnl", 0)
                for k, v in saved.get("stats", {}).items():
                    if k in self.stats:
                        self.stats[k] = v
                for o in saved.get("order_history", []):
                    ord = AutoOrder(
                        order_id=o.get("order_id", ""),
                        symbol=o.get("symbol", ""),
                        side=PositionSide.SHORT if o.get("side") == "SHORT" else PositionSide.LONG,
                        entry_price=o.get("entry_price", 0),
                        quantity=o.get("quantity", 0),
                        stop_loss=0, take_profit1=0,
                        filled_price=o.get("filled_price", 0),
                        filled_quantity=o.get("filled_quantity", 0),
                        realized_pnl=o.get("realized_pnl", 0),
                        status=OrderStatus.FILLED,
                        signal_source=o.get("signal_source", ""),
                    )
                    self.order_history.append(ord)
                logger.info(f"📂 Demo state restored: ${self.demo_balance:.2f}, {len(self.order_history)} trades")
        
        self.on_order_filled: Optional[Callable] = None
        self.on_position_closed: Optional[Callable] = None
        
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
        leverage: int = 20,
        confidence: int = 50,
        signal_source: str = ""
    ) -> Optional[AutoOrder]:
        """Place SHORT order — 5% deposit, 20x leverage"""
        if len(self.positions) >= self.max_positions:
            logger.debug(f"Position limit reached ({self.max_positions})")
            return None
        
        if symbol in self.positions:
            logger.debug(f"Position {symbol} already open")
            return None
        
        # Force 20x leverage
        leverage = self.DEFAULT_LEVERAGE
        
        # Margin = 5% of balance, Notional = margin * leverage
        margin = self.demo_balance * (self.POSITION_SIZE_PCT / 100)
        if margin <= 0:
            logger.debug(f"Insufficient balance for trade")
            return None
        notional = margin * leverage  # e.g. $5 margin * 20x = $100 notional
        quantity = notional / entry_price
        
        order = AutoOrder(
            order_id=f"ORD_{symbol}_{int(time.time())}",
            symbol=symbol,
            side=PositionSide.SHORT,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit1=take_profit1,
            take_profit2=take_profit2 or take_profit1 * 0.95,
            take_profit3=take_profit3,
            created_at=datetime.now(),
            signal_source=signal_source,
            confidence=confidence,
            leverage=leverage
        )
        
        self.orders[order.order_id] = order
        self.stats['orders_placed'] += 1
        
        if self.demo_mode:
            await self._demo_fill_order(order, margin=margin)
        else:
            await self._place_real_order(order, leverage)
        
        logger.info(
            f"📝 SHORT {symbol} @ ${entry_price:.6f} | "
            f"Margin ${margin:.2f} x{leverage} = ${notional:.2f} | "
            f"SL: ${stop_loss:.6f} | TP1: ${take_profit1:.6f}"
        )
        
        return order
    
    async def place_long_order(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit1: float,
        take_profit2: float = 0,
        position_size_usd: float = 0,
        leverage: int = 20,
        confidence: int = 50,
        signal_source: str = ""
    ) -> Optional[AutoOrder]:
        """Place LONG order — 5% deposit, 20x leverage"""
        if len(self.positions) >= self.max_positions:
            logger.debug(f"Position limit reached ({self.max_positions})")
            return None
        
        if symbol in self.positions:
            logger.debug(f"Position {symbol} already open")
            return None
        
        leverage = self.DEFAULT_LEVERAGE
        
        margin = self.demo_balance * (self.POSITION_SIZE_PCT / 100)
        if margin <= 0:
            logger.debug(f"Insufficient balance for trade")
            return None
        notional = margin * leverage
        quantity = notional / entry_price
        
        order = AutoOrder(
            order_id=f"ORD_{symbol}_{int(time.time())}",
            symbol=symbol,
            side=PositionSide.LONG,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit1=take_profit1,
            take_profit2=take_profit2 or take_profit1 * 1.05,
            take_profit3=0,
            created_at=datetime.now(),
            signal_source=signal_source,
            confidence=confidence,
            leverage=leverage
        )
        
        self.orders[order.order_id] = order
        self.stats['orders_placed'] += 1
        
        if self.demo_mode:
            await self._demo_fill_order(order, margin=margin)
        else:
            await self._place_real_order(order, leverage)
        
        logger.info(
            f"📝 LONG {symbol} @ ${entry_price:.6f} | "
            f"Margin ${margin:.2f} x{leverage} = ${notional:.2f} | "
            f"SL: ${stop_loss:.6f} | TP1: ${take_profit1:.6f}"
        )
        
        return order
    
    async def _demo_fill_order(self, order: AutoOrder, price_history: List[float] = None, 
                               orderbook: dict = None, recent_trades: List[dict] = None,
                               margin: float = 0):
        """Fill order in demo mode — deduct margin (5% of balance)"""
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
        
        # Create adaptive exit plan (silent)
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
                order.stop_loss = exit_plan.stop_loss.price
                if exit_plan.take_profits:
                    order.take_profit1 = exit_plan.take_profits[0].price
                    order.take_profit2 = exit_plan.take_profits[1].price if len(exit_plan.take_profits) > 1 else 0
                logger.debug(f"Adaptive exit plan for {order.symbol}")
        except Exception as e:
            logger.debug(f"No adaptive plan: {e}")
        
        self.positions[order.symbol] = position
        self.stats['positions_opened'] += 1
        
        # Deduct margin (5% of balance), NOT full notional
        if margin <= 0:
            margin = order.filled_price * order.filled_quantity / order.leverage
        self.demo_balance -= margin
        
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
        """Check SL/TP exits — TP1: 50% + SL→breakeven, TP2: close all"""
        
        order = next((o for o in self.orders.values() if o.symbol == position.symbol), None)
        if not order:
            return
        
        close_reason, close_pct = None, 100
        
        if position.side == PositionSide.SHORT:
            # STOP LOSS — close everything
            if current_price >= order.stop_loss:
                close_reason = "STOP_LOSS"
                close_pct = 100
            
            # TP1 — close 50%, move SL to breakeven
            elif current_price <= order.take_profit1 and not position.tp1_filled:
                close_reason = "TAKE_PROFIT_1"
                close_pct = 50
                position.tp1_filled = True
                # Move SL to entry (breakeven)
                order.stop_loss = position.entry_price
                if position.exit_plan:
                    position.exit_plan.stop_loss.price = position.entry_price
                    position.exit_plan.stop_loss.trigger_reason = "Breakeven after TP1"
                logger.info(f"🎯 {position.symbol}: TP1! 50% closed, SL → breakeven ${position.entry_price:.6f}")
            
            # TP2 — close remaining 100%
            elif current_price <= order.take_profit2 and not position.tp2_filled and position.tp1_filled:
                close_reason = "TAKE_PROFIT_2"
                close_pct = 100  # Close ALL remaining
                position.tp2_filled = True
                logger.info(f"🎯 {position.symbol}: TP2! Closing remaining position")
        
        elif position.side == PositionSide.LONG:
            # STOP LOSS — price dropped below SL
            if current_price <= order.stop_loss:
                close_reason = "STOP_LOSS"
                close_pct = 100
            
            # TP1 — price rose above TP1, close 50%, move SL to breakeven
            elif current_price >= order.take_profit1 and not position.tp1_filled:
                close_reason = "TAKE_PROFIT_1"
                close_pct = 50
                position.tp1_filled = True
                order.stop_loss = position.entry_price
                if position.exit_plan:
                    position.exit_plan.stop_loss.price = position.entry_price
                    position.exit_plan.stop_loss.trigger_reason = "Breakeven after TP1"
                logger.info(f"🎯 {position.symbol}: TP1! 50% closed, SL → breakeven ${position.entry_price:.6f}")
            
            # TP2 — close remaining 100%
            elif current_price >= order.take_profit2 and not position.tp2_filled and position.tp1_filled:
                close_reason = "TAKE_PROFIT_2"
                close_pct = 100
                position.tp2_filled = True
                logger.info(f"🎯 {position.symbol}: TP2! Closing remaining position")
        
        if close_reason:
            await self._close_position(position, current_price, close_reason, close_pct)
    
    async def _close_position(
        self,
        position: Position,
        exit_price: float,
        reason: str,
        close_pct: float = 100
    ):
        """Close position with leverage-adjusted P&L
        
        P&L formula (SHORT with leverage):
          pnl_pct = (entry - exit) / entry * 100
          notional = quantity * entry_price
          margin   = notional / leverage
          pnl_usd  = margin * leverage * (pnl_pct / 100) * (close_pct / 100)
                   = notional * (pnl_pct / 100) * (close_pct / 100)
        
        Balance update:
          return margin for the closed portion + pnl_usd
        """
        leverage = position.leverage or self.DEFAULT_LEVERAGE
        
        if position.side == PositionSide.SHORT:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
        else:
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        
        # Leveraged P&L
        close_quantity = position.quantity * (close_pct / 100)
        notional_closed = close_quantity * position.entry_price
        margin_closed = notional_closed / leverage
        # P&L USD = (Entry - Exit) * Quantity for SHORT
        if position.side == PositionSide.SHORT:
            pnl_usd = (position.entry_price - exit_price) * close_quantity
        else:
            pnl_usd = (exit_price - position.entry_price) * close_quantity
        
        leveraged_pnl_pct = pnl_pct * leverage  # For display: e.g. 2% * 20x = 40%
        
        if close_pct >= 100 or reason == "STOP_LOSS":
            for oid, ord in list(self.orders.items()):
                if ord.symbol == position.symbol:
                    ord.realized_pnl = pnl_usd
                    self.order_history.append(ord)
                    del self.orders[oid]
                    break
        
        self.stats['total_pnl_usd'] += pnl_usd
        if close_pct >= 100 or reason == "STOP_LOSS" or (close_pct < 100 and not position.tp1_filled):
            self.stats['wins' if pnl_pct > 0 else 'losses'] += 1
        
        # Return margin + pnl to balance
        self.demo_balance += margin_closed + pnl_usd
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
        logger.info(
            f"{emoji} {position.symbol} | {reason} | {close_pct:.0f}% | "
            f"P&L: {leveraged_pnl_pct:+.1f}% (${pnl_usd:+.2f}) | "
            f"Bal: ${self.demo_balance:.2f}"
        )
        
        if close_pct >= 100 or reason == "STOP_LOSS" or position.closed_portions >= 99:
            if position.exit_plan:
                exit_manager.remove_plan(position.symbol)
            del self.positions[position.symbol]
            self.stats['positions_closed'] += 1
            if self.demo_mode:
                save_demo_state(self.demo_balance, self.demo_pnl, self.order_history, self.stats)
            
            if self.on_position_closed:
                await self.on_position_closed(position, pnl_pct, pnl_usd, reason)
        else:
            position.quantity -= close_quantity
            logger.debug(f"📊 {position.symbol}: {100-position.closed_portions:.0f}% remaining")
    
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

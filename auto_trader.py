"""
MEXC Pump Monitor - Auto Trading Engine
Автоматическое исполнение сигналов
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hmac
import hashlib
import aiohttp

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Статус ордера"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionSide(Enum):
    """Сторона позиции"""
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class AutoOrder:
    """Автоматический ордер"""
    order_id: str
    symbol: str
    side: PositionSide
    
    # Цены
    entry_price: float
    quantity: float
    
    # SL/TP
    stop_loss: float
    take_profit1: float
    take_profit2: float = 0
    take_profit3: float = 0
    
    # Статус
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float = 0
    filled_quantity: float = 0
    
    # Время
    created_at: datetime = None
    filled_at: datetime = None
    
    # P&L
    realized_pnl: float = 0
    unrealized_pnl: float = 0
    
    # Мета
    signal_source: str = ""
    confidence: int = 50


@dataclass
class Position:
    """Открытая позиция"""
    symbol: str
    side: PositionSide
    
    entry_price: float
    quantity: float
    leverage: int = 1
    
    # SL/TP ордера
    stop_loss_order_id: str = ""
    tp1_order_id: str = ""
    tp2_order_id: str = ""
    tp3_order_id: str = ""
    
    # Текущее состояние
    current_price: float = 0
    unrealized_pnl_pct: float = 0
    unrealized_pnl_usd: float = 0
    
    # Частичные выходы
    tp1_filled: bool = False
    tp2_filled: bool = False
    
    # Время
    opened_at: datetime = None
    
    def update_pnl(self, current_price: float):
        """Обновить P&L"""
        self.current_price = current_price
        
        if self.side == PositionSide.SHORT:
            self.unrealized_pnl_pct = (self.entry_price - current_price) / self.entry_price * 100
        else:
            self.unrealized_pnl_pct = (current_price - self.entry_price) / self.entry_price * 100
        
        self.unrealized_pnl_usd = self.quantity * self.entry_price * (self.unrealized_pnl_pct / 100)


class AutoTrader:
    """
    Автоматический трейдер
    
    ВНИМАНИЕ: Только для демо/тестирования!
    Реальная торговля требует API ключи
    """
    
    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        demo_mode: bool = True,
        max_positions: int = 5,
        max_position_size_pct: float = 10
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.demo_mode = demo_mode
        
        self.max_positions = max_positions
        self.max_position_size_pct = max_position_size_pct
        
        # Состояние
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, AutoOrder] = {}
        self.order_history: List[AutoOrder] = []
        
        # Баланс (демо)
        self.demo_balance = 10000
        self.demo_pnl = 0
        
        # Колбэки
        self.on_order_filled: Optional[Callable] = None
        self.on_position_closed: Optional[Callable] = None
        
        # Статистика
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
            logger.info("🎮 AutoTrader запущен в ДЕМО режиме")
        else:
            logger.warning("⚠️ AutoTrader запущен в РЕАЛЬНОМ режиме!")
    
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
        """
        Разместить SHORT ордер
        
        Returns:
            AutoOrder или None при ошибке
        """
        # Проверки
        if len(self.positions) >= self.max_positions:
            logger.warning(f"Достигнут лимит позиций ({self.max_positions})")
            return None
        
        if symbol in self.positions:
            logger.warning(f"Позиция {symbol} уже открыта")
            return None
        
        # Размер позиции
        if position_size_usd <= 0:
            position_size_usd = self.demo_balance * (self.max_position_size_pct / 100)
        
        quantity = position_size_usd / entry_price
        
        # Создать ордер
        order_id = f"ORD_{symbol}_{int(time.time())}"
        
        order = AutoOrder(
            order_id=order_id,
            symbol=symbol,
            side=PositionSide.SHORT,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit1=take_profit1,
            take_profit2=take_profit2 or take_profit1 * 0.95,
            take_profit3=take_profit3 or take_profit1 * 0.90,
            created_at=datetime.now(),
            signal_source=signal_source,
            confidence=confidence
        )
        
        self.orders[order_id] = order
        self.stats['orders_placed'] += 1
        
        if self.demo_mode:
            # В демо режиме сразу исполняем
            await self._demo_fill_order(order)
        else:
            # Реальное размещение через API
            await self._place_real_order(order, leverage)
        
        logger.info(
            f"📝 SHORT ордер: {symbol} @ ${entry_price:.8f} | "
            f"SL: ${stop_loss:.8f} | TP1: ${take_profit1:.8f}"
        )
        
        return order
    
    async def _demo_fill_order(self, order: AutoOrder):
        """Исполнить ордер в демо режиме"""
        order.status = OrderStatus.FILLED
        order.filled_price = order.entry_price
        order.filled_quantity = order.quantity
        order.filled_at = datetime.now()
        
        self.stats['orders_filled'] += 1
        
        # Создать позицию
        position = Position(
            symbol=order.symbol,
            side=order.side,
            entry_price=order.filled_price,
            quantity=order.filled_quantity,
            opened_at=datetime.now()
        )
        
        self.positions[order.symbol] = position
        self.stats['positions_opened'] += 1
        
        # Зарезервировать баланс
        self.demo_balance -= order.filled_price * order.filled_quantity
        
        if self.on_order_filled:
            await self.on_order_filled(order)
    
    async def _place_real_order(self, order: AutoOrder, leverage: int):
        """Разместить реальный ордер через MEXC API"""
        # TODO: Реализовать MEXC Futures API
        logger.warning("Реальная торговля ещё не реализована")
        pass
    
    async def update_positions(self, prices: Dict[str, float]):
        """Обновить позиции с текущими ценами"""
        for symbol, position in list(self.positions.items()):
            if symbol not in prices:
                continue
            
            current_price = prices[symbol]
            position.update_pnl(current_price)
            
            # Проверить SL/TP
            await self._check_exits(position, current_price)
    
    async def _check_exits(self, position: Position, current_price: float):
        """Проверить выходы по SL/TP"""
        if position.symbol not in self.orders:
            return
        
        # Найти оригинальный ордер
        order = None
        for o in self.orders.values():
            if o.symbol == position.symbol:
                order = o
                break
        
        if not order:
            return
        
        should_close = False
        close_reason = ""
        close_pct = 100  # Сколько % позиции закрыть
        
        if position.side == PositionSide.SHORT:
            # SHORT: SL если цена выросла, TP если упала
            if current_price >= order.stop_loss:
                should_close = True
                close_reason = "STOP_LOSS"
            elif current_price <= order.take_profit1 and not position.tp1_filled:
                should_close = True
                close_reason = "TAKE_PROFIT_1"
                close_pct = 30
                position.tp1_filled = True
            elif current_price <= order.take_profit2 and not position.tp2_filled:
                should_close = True
                close_reason = "TAKE_PROFIT_2"
                close_pct = 40
                position.tp2_filled = True
            elif current_price <= order.take_profit3:
                should_close = True
                close_reason = "TAKE_PROFIT_3"
                close_pct = 100
        
        if should_close:
            await self._close_position(position, current_price, close_reason, close_pct)
    
    async def _close_position(
        self,
        position: Position,
        exit_price: float,
        reason: str,
        close_pct: float = 100
    ):
        """Закрыть позицию"""
        # Рассчитать P&L
        if position.side == PositionSide.SHORT:
            pnl_pct = (position.entry_price - exit_price) / position.entry_price * 100
        else:
            pnl_pct = (exit_price - position.entry_price) / position.entry_price * 100
        
        close_quantity = position.quantity * (close_pct / 100)
        pnl_usd = close_quantity * position.entry_price * (pnl_pct / 100)
        
        # Обновить статистику
        self.stats['total_pnl_usd'] += pnl_usd
        
        if pnl_pct > 0:
            self.stats['wins'] += 1
        else:
            self.stats['losses'] += 1
        
        # Обновить демо баланс
        self.demo_balance += close_quantity * exit_price + pnl_usd
        self.demo_pnl += pnl_usd
        
        logger.info(
            f"{'✅' if pnl_pct > 0 else '❌'} Позиция закрыта: {position.symbol} | "
            f"P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) | Причина: {reason}"
        )
        
        # Полное закрытие
        if close_pct >= 100 or reason == "STOP_LOSS":
            del self.positions[position.symbol]
            self.stats['positions_closed'] += 1
            
            if self.on_position_closed:
                await self.on_position_closed(position, pnl_pct, pnl_usd, reason)
        else:
            # Частичное закрытие
            position.quantity -= close_quantity
    
    async def close_all_positions(self, prices: Dict[str, float]):
        """Закрыть все позиции"""
        for symbol, position in list(self.positions.items()):
            if symbol in prices:
                await self._close_position(position, prices[symbol], "MANUAL_CLOSE", 100)
    
    def get_open_positions(self) -> List[Position]:
        """Получить открытые позиции"""
        return list(self.positions.values())
    
    def format_status(self) -> str:
        """Форматировать статус"""
        pnl_emoji = "🟢" if self.demo_pnl >= 0 else "🔴"
        
        msg = f"""
🤖 <b>AUTO TRADER СТАТУС</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>БАЛАНС:</b>
├ Начальный: $10,000
├ Текущий: ${self.demo_balance:,.2f}
└ {pnl_emoji} P&L: ${self.demo_pnl:+,.2f}

📊 <b>ПОЗИЦИИ:</b>
├ Открыто: {len(self.positions)}/{self.max_positions}
├ Всего открыто: {self.stats['positions_opened']}
└ Всего закрыто: {self.stats['positions_closed']}

📈 <b>РЕЗУЛЬТАТЫ:</b>
├ ✅ Винов: {self.stats['wins']}
├ ❌ Лоссов: {self.stats['losses']}
└ Винрейт: {self.stats['wins'] / max(1, self.stats['wins'] + self.stats['losses']) * 100:.1f}%
"""
        
        if self.positions:
            msg += "\n<b>ОТКРЫТЫЕ ПОЗИЦИИ:</b>\n"
            for symbol, pos in self.positions.items():
                pnl_emoji = "🟢" if pos.unrealized_pnl_pct >= 0 else "🔴"
                msg += f"├ {symbol}: {pnl_emoji} {pos.unrealized_pnl_pct:+.2f}%\n"
        
        return msg.strip()
    
    def format_positions(self) -> str:
        """Форматировать открытые позиции"""
        if not self.positions:
            return "📭 Нет открытых позиций"
        
        msg = "📊 <b>ОТКРЫТЫЕ ПОЗИЦИИ</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        for symbol, pos in self.positions.items():
            pnl_emoji = "🟢" if pos.unrealized_pnl_pct >= 0 else "🔴"
            side_emoji = "🔴" if pos.side == PositionSide.SHORT else "🟢"
            
            msg += f"""
{side_emoji} <b>{symbol}</b>
├ Сторона: {pos.side.value}
├ Вход: ${pos.entry_price:.8f}
├ Текущая: ${pos.current_price:.8f}
├ {pnl_emoji} P&L: {pos.unrealized_pnl_pct:+.2f}% (${pos.unrealized_pnl_usd:+.2f})
├ TP1: {'✅' if pos.tp1_filled else '⏳'}
└ TP2: {'✅' if pos.tp2_filled else '⏳'}
"""
        
        return msg.strip()

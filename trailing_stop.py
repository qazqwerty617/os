"""
MEXC Pump Monitor - Trailing Stop Engine
Динамическое управление стоп-лоссами с трейлингом
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TrailingMode(Enum):
    """Режимы трейлинга"""
    FIXED_PERCENT = "fixed_percent"      # Фиксированный % от цены
    ATR_BASED = "atr_based"              # На основе ATR
    STEP_BASED = "step_based"            # Ступенчатый (после каждых X%)
    CHANDELIER = "chandelier"            # Chandelier Exit
    PARABOLIC = "parabolic"              # Parabolic SAR style


@dataclass
class TrailingPosition:
    """Позиция с трейлингом"""
    position_id: str
    symbol: str
    entry_price: float
    current_price: float
    
    # Direction
    is_short: bool
    
    # Trailing parameters
    mode: TrailingMode
    trail_percent: float  # For FIXED_PERCENT
    trail_atr: float = 0  # For ATR_BASED
    step_size: float = 0  # For STEP_BASED
    
    # Current levels
    initial_stop: float = 0
    current_stop: float = 0
    highest_profit: float = 0  # Highest profit reached
    
    # Status
    is_active: bool = True
    activated_at: int = 0
    last_update: int = 0
    
    # Breakeven
    breakeven_activated: bool = False
    breakeven_trigger_pct: float = 1.0  # Activate after 1% profit
    
    # Take profit levels hit
    tp1_hit: bool = False
    tp2_hit: bool = False


@dataclass
class TrailUpdate:
    """Обновление трейлинга"""
    position_id: str
    old_stop: float
    new_stop: float
    reason: str
    timestamp: int


class TrailingStopEngine:
    """
    📈 Trailing Stop Engine
    
    Функции:
    - Динамический трейлинг стоп
    - Несколько режимов трейлинга
    - Автоматический Breakeven
    - Ступенчатое подтягивание
    - Логирование всех изменений
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Active positions
        self.positions: Dict[str, TrailingPosition] = {}
        
        # Update history
        self.updates: List[TrailUpdate] = []
        self.max_updates = 1000
        
        # Callbacks
        self._stop_hit_callbacks: List[Callable] = []
        
        # Stats
        self.stats = {
            'positions_tracked': 0,
            'trail_updates': 0,
            'stops_triggered': 0,
            'breakevens_activated': 0
        }
        
        self._running = False
    
    async def start(self):
        """Запустить engine"""
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("📈 Trailing Stop Engine started")
    
    async def stop(self):
        """Остановить engine"""
        self._running = False
    
    def on_stop_hit(self, callback: Callable):
        """Callback когда стоп сработал"""
        self._stop_hit_callbacks.append(callback)
    
    def add_position(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        initial_stop: float,
        is_short: bool = True,
        mode: TrailingMode = TrailingMode.FIXED_PERCENT,
        trail_percent: float = 2.0,
        trail_atr: float = 0,
        step_size: float = 1.0,
        breakeven_trigger: float = 1.0
    ) -> TrailingPosition:
        """
        Добавить позицию для трейлинга
        
        Args:
            position_id: ID позиции
            symbol: Символ
            entry_price: Цена входа
            initial_stop: Начальный стоп
            is_short: True для шортов
            mode: Режим трейлинга
            trail_percent: Процент трейлинга (для FIXED_PERCENT)
            trail_atr: ATR значение (для ATR_BASED)
            step_size: Размер шага в % (для STEP_BASED)
            breakeven_trigger: Триггер для breakeven в %
        
        Returns:
            TrailingPosition
        """
        now = int(time.time() * 1000)
        
        position = TrailingPosition(
            position_id=position_id,
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,
            is_short=is_short,
            mode=mode,
            trail_percent=trail_percent,
            trail_atr=trail_atr,
            step_size=step_size,
            initial_stop=initial_stop,
            current_stop=initial_stop,
            activated_at=now,
            last_update=now,
            breakeven_trigger_pct=breakeven_trigger
        )
        
        self.positions[position_id] = position
        self.stats['positions_tracked'] = len(self.positions)
        
        logger.info(f"Trailing added: {symbol} @ {entry_price}, SL: {initial_stop}")
        
        return position
    
    def remove_position(self, position_id: str):
        """Удалить позицию"""
        if position_id in self.positions:
            del self.positions[position_id]
            self.stats['positions_tracked'] = len(self.positions)
    
    async def update_price(self, symbol: str, current_price: float):
        """
        Обновить цену и пересчитать трейлинг
        """
        for pos_id, pos in list(self.positions.items()):
            if pos.symbol != symbol or not pos.is_active:
                continue
            
            pos.current_price = current_price
            pos.last_update = int(time.time() * 1000)
            
            # Calculate current profit
            if pos.is_short:
                profit_pct = ((pos.entry_price - current_price) / pos.entry_price) * 100
            else:
                profit_pct = ((current_price - pos.entry_price) / pos.entry_price) * 100
            
            # Update highest profit
            if profit_pct > pos.highest_profit:
                pos.highest_profit = profit_pct
            
            # Check breakeven activation
            if not pos.breakeven_activated and profit_pct >= pos.breakeven_trigger_pct:
                await self._activate_breakeven(pos)
            
            # Update trailing stop
            new_stop = self._calculate_trail(pos, current_price, profit_pct)
            
            if new_stop and new_stop != pos.current_stop:
                # Validate: for shorts, new stop should be lower (better)
                # for longs, new stop should be higher (better)
                should_update = False
                
                if pos.is_short:
                    if new_stop < pos.current_stop:
                        should_update = True
                else:
                    if new_stop > pos.current_stop:
                        should_update = True
                
                if should_update:
                    await self._update_stop(pos, new_stop, "Trail update")
            
            # Check if stop hit
            stop_hit = False
            if pos.is_short:
                if current_price >= pos.current_stop:
                    stop_hit = True
            else:
                if current_price <= pos.current_stop:
                    stop_hit = True
            
            if stop_hit:
                await self._trigger_stop(pos)
    
    async def _activate_breakeven(self, pos: TrailingPosition):
        """Активировать breakeven"""
        # Move stop to entry + small buffer
        if pos.is_short:
            new_stop = pos.entry_price * 0.999  # Slightly below entry for short
        else:
            new_stop = pos.entry_price * 1.001  # Slightly above entry for long
        
        pos.breakeven_activated = True
        await self._update_stop(pos, new_stop, "Breakeven activated")
        
        self.stats['breakevens_activated'] += 1
        
        if self.telegram:
            await self.telegram.send_message(
                f"🔒 <b>BREAKEVEN:</b> {pos.symbol}\n"
                f"SL moved to ${new_stop:.6f}"
            )
    
    def _calculate_trail(
        self,
        pos: TrailingPosition,
        current_price: float,
        profit_pct: float
    ) -> Optional[float]:
        """Рассчитать новый уровень трейлинга"""
        
        if pos.mode == TrailingMode.FIXED_PERCENT:
            return self._calc_fixed_percent(pos, current_price)
        
        elif pos.mode == TrailingMode.STEP_BASED:
            return self._calc_step_based(pos, current_price, profit_pct)
        
        elif pos.mode == TrailingMode.ATR_BASED:
            return self._calc_atr_based(pos, current_price)
        
        elif pos.mode == TrailingMode.CHANDELIER:
            return self._calc_chandelier(pos, current_price)
        
        elif pos.mode == TrailingMode.PARABOLIC:
            return self._calc_parabolic(pos, current_price, profit_pct)
        
        return None
    
    def _calc_fixed_percent(self, pos: TrailingPosition, price: float) -> float:
        """Fixed percentage trailing"""
        trail_distance = price * (pos.trail_percent / 100)
        
        if pos.is_short:
            # For short: stop is above price
            return price + trail_distance
        else:
            # For long: stop is below price
            return price - trail_distance
    
    def _calc_step_based(
        self,
        pos: TrailingPosition,
        price: float,
        profit_pct: float
    ) -> Optional[float]:
        """Step-based trailing - move stop after each step_size % profit"""
        if profit_pct <= 0:
            return None
        
        # Calculate number of steps completed
        steps = int(profit_pct / pos.step_size)
        
        if steps <= 0:
            return None
        
        # Each step moves stop by step_size/2 %
        move_pct = steps * (pos.step_size / 2)
        
        if pos.is_short:
            # Move stop down (closer to current price)
            new_stop = pos.entry_price * (1 - move_pct / 100)
        else:
            # Move stop up
            new_stop = pos.entry_price * (1 + move_pct / 100)
        
        return new_stop
    
    def _calc_atr_based(self, pos: TrailingPosition, price: float) -> float:
        """ATR-based trailing"""
        if pos.is_short:
            return price + (pos.trail_atr * 2)
        else:
            return price - (pos.trail_atr * 2)
    
    def _calc_chandelier(self, pos: TrailingPosition, price: float) -> float:
        """Chandelier Exit style"""
        # Use highest profit as reference
        if pos.highest_profit <= 0:
            return pos.current_stop
        
        # Trail 3x ATR from high
        trail = pos.trail_atr * 3 if pos.trail_atr > 0 else price * 0.03
        
        if pos.is_short:
            low_point = pos.entry_price * (1 - pos.highest_profit / 100)
            return low_point + trail
        else:
            high_point = pos.entry_price * (1 + pos.highest_profit / 100)
            return high_point - trail
    
    def _calc_parabolic(
        self,
        pos: TrailingPosition,
        price: float,
        profit_pct: float
    ) -> Optional[float]:
        """Parabolic-style trailing - accelerates as profit grows"""
        if profit_pct <= 0:
            return None
        
        # Acceleration factor increases with profit
        af = min(0.02 + (profit_pct * 0.002), 0.20)  # Max 20% acceleration
        
        # Move stop towards price
        current_diff = abs(price - pos.current_stop)
        new_diff = current_diff * (1 - af)
        
        if pos.is_short:
            return price + new_diff
        else:
            return price - new_diff
    
    async def _update_stop(self, pos: TrailingPosition, new_stop: float, reason: str):
        """Обновить стоп"""
        old_stop = pos.current_stop
        pos.current_stop = new_stop
        
        update = TrailUpdate(
            position_id=pos.position_id,
            old_stop=old_stop,
            new_stop=new_stop,
            reason=reason,
            timestamp=int(time.time() * 1000)
        )
        
        self.updates.append(update)
        if len(self.updates) > self.max_updates:
            self.updates = self.updates[-self.max_updates:]
        
        self.stats['trail_updates'] += 1
        
        logger.debug(f"Trail update {pos.symbol}: {old_stop:.6f} -> {new_stop:.6f}")
    
    async def _trigger_stop(self, pos: TrailingPosition):
        """Стоп сработал"""
        pos.is_active = False
        self.stats['stops_triggered'] += 1
        
        # Calculate P&L
        if pos.is_short:
            pnl_pct = ((pos.entry_price - pos.current_price) / pos.entry_price) * 100
        else:
            pnl_pct = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100
        
        emoji = "🟢" if pnl_pct > 0 else "🔴"
        
        logger.info(f"Stop triggered: {pos.symbol} @ {pos.current_price}, P&L: {pnl_pct:.2f}%")
        
        if self.telegram:
            await self.telegram.send_message(
                f"{emoji} <b>STOP TRIGGERED:</b> {pos.symbol}\n"
                f"Exit: ${pos.current_price:.6f}\n"
                f"P&L: {pnl_pct:+.2f}%"
            )
        
        # Notify callbacks
        for callback in self._stop_hit_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(pos, pnl_pct)
                else:
                    callback(pos, pnl_pct)
            except Exception as e:
                logger.error(f"Stop callback error: {e}")
        
        # Remove position
        self.remove_position(pos.position_id)
    
    async def _monitor_loop(self):
        """Мониторинг позиций"""
        while self._running:
            try:
                # Cleanup stale positions (>24h without update)
                now = int(time.time() * 1000)
                cutoff = now - (24 * 60 * 60 * 1000)
                
                stale = [
                    pid for pid, pos in self.positions.items()
                    if pos.last_update < cutoff
                ]
                
                for pid in stale:
                    logger.warning(f"Removing stale position: {pid}")
                    self.remove_position(pid)
                
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Trail monitor error: {e}")
    
    def get_position(self, position_id: str) -> Optional[TrailingPosition]:
        """Получить позицию"""
        return self.positions.get(position_id)
    
    def get_all_positions(self) -> List[TrailingPosition]:
        """Получить все позиции"""
        return list(self.positions.values())
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return self.stats

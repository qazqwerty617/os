"""
MEXC Pump Monitor - DCA Module & Breakeven Mover
Dollar Cost Averaging и автоматический перенос в безубыток
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DCAStrategy(Enum):
    """Стратегии DCA"""
    FIXED_AMOUNT = "fixed"           # Фиксированная сумма
    MARTINGALE = "martingale"        # Увеличение после убытка (опасно!)
    ANTI_MARTINGALE = "anti_martin"  # Увеличение после прибыли
    SCALED = "scaled"                # Масштабирование по цене


@dataclass
class DCALevel:
    """Уровень DCA"""
    level: int
    trigger_price: float
    amount_usd: float
    executed: bool = False
    executed_at: int = 0
    actual_price: float = 0


@dataclass
class DCAPosition:
    """Позиция с DCA"""
    position_id: str
    symbol: str
    
    # Direction
    is_short: bool
    
    # Initial entry
    initial_entry: float
    initial_amount: float
    
    # DCA settings
    strategy: DCAStrategy
    max_dca_levels: int
    dca_step_pct: float  # % падения для каждого DCA
    dca_multiplier: float  # Множитель для martingale
    
    # DCA levels
    levels: List[DCALevel] = field(default_factory=list)
    
    # Aggregated position
    avg_entry: float = 0
    total_amount: float = 0
    total_cost: float = 0
    
    # Status
    is_active: bool = True
    created_at: int = 0
    last_update: int = 0


@dataclass
class BreakevenConfig:
    """Настройки Breakeven"""
    trigger_profit_pct: float = 1.0   # Активация при 1% профите
    buffer_pct: float = 0.1           # Буфер над/под входом
    notify: bool = True


class DCAModule:
    """
    💰 DCA (Dollar Cost Averaging) Module
    
    Функции:
    - Автоматическое усреднение позиций
    - Несколько стратегий DCA
    - Расчёт средней цены входа
    - Управление уровнями
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Active DCA positions
        self.positions: Dict[str, DCAPosition] = {}
        
        # Stats
        self.stats = {
            'dca_executions': 0,
            'total_averaged': 0,
            'positions_managed': 0
        }
    
    def create_dca_plan(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        initial_amount: float,
        is_short: bool = True,
        max_levels: int = 3,
        step_pct: float = 3.0,
        strategy: DCAStrategy = DCAStrategy.FIXED_AMOUNT,
        multiplier: float = 1.5
    ) -> DCAPosition:
        """
        Создать план DCA
        
        Args:
            position_id: ID позиции
            symbol: Символ
            entry_price: Начальная цена входа
            initial_amount: Начальная сумма в USD
            is_short: True для шортов
            max_levels: Макс кол-во DCA уровней
            step_pct: Шаг между уровнями в %
            strategy: Стратегия DCA
            multiplier: Множитель для martingale
        
        Returns:
            DCAPosition
        """
        now = int(time.time() * 1000)
        
        # Create DCA levels
        levels = []
        current_amount = initial_amount
        
        for i in range(1, max_levels + 1):
            # Calculate trigger price
            if is_short:
                # For short: DCA when price goes UP (against us)
                trigger = entry_price * (1 + (step_pct * i) / 100)
            else:
                # For long: DCA when price goes DOWN
                trigger = entry_price * (1 - (step_pct * i) / 100)
            
            # Calculate amount based on strategy
            if strategy == DCAStrategy.MARTINGALE:
                level_amount = current_amount * multiplier
                current_amount = level_amount
            elif strategy == DCAStrategy.ANTI_MARTINGALE:
                level_amount = initial_amount  # Keep fixed
            elif strategy == DCAStrategy.SCALED:
                # Increase amount as price gets worse
                level_amount = initial_amount * (1 + (i * 0.5))
            else:  # FIXED_AMOUNT
                level_amount = initial_amount
            
            levels.append(DCALevel(
                level=i,
                trigger_price=trigger,
                amount_usd=level_amount
            ))
        
        position = DCAPosition(
            position_id=position_id,
            symbol=symbol,
            is_short=is_short,
            initial_entry=entry_price,
            initial_amount=initial_amount,
            strategy=strategy,
            max_dca_levels=max_levels,
            dca_step_pct=step_pct,
            dca_multiplier=multiplier,
            levels=levels,
            avg_entry=entry_price,
            total_amount=initial_amount / entry_price,
            total_cost=initial_amount,
            created_at=now,
            last_update=now
        )
        
        self.positions[position_id] = position
        self.stats['positions_managed'] = len(self.positions)
        
        logger.info(f"DCA plan created: {symbol}, {max_levels} levels @ {step_pct}% steps")
        
        return position
    
    async def check_price(self, symbol: str, current_price: float):
        """
        Проверить цену и выполнить DCA если нужно
        """
        for pos_id, pos in list(self.positions.items()):
            if pos.symbol != symbol or not pos.is_active:
                continue
            
            pos.last_update = int(time.time() * 1000)
            
            for level in pos.levels:
                if level.executed:
                    continue
                
                # Check if trigger hit
                should_execute = False
                if pos.is_short:
                    if current_price >= level.trigger_price:
                        should_execute = True
                else:
                    if current_price <= level.trigger_price:
                        should_execute = True
                
                if should_execute:
                    await self._execute_dca(pos, level, current_price)
    
    async def _execute_dca(
        self,
        pos: DCAPosition,
        level: DCALevel,
        price: float
    ):
        """Выполнить DCA"""
        level.executed = True
        level.executed_at = int(time.time() * 1000)
        level.actual_price = price
        
        # Update aggregated position
        new_qty = level.amount_usd / price
        pos.total_amount += new_qty
        pos.total_cost += level.amount_usd
        pos.avg_entry = pos.total_cost / pos.total_amount
        
        self.stats['dca_executions'] += 1
        self.stats['total_averaged'] += level.amount_usd
        
        logger.info(
            f"DCA executed: {pos.symbol} level {level.level} "
            f"@ ${price:.6f}, new avg: ${pos.avg_entry:.6f}"
        )
        
        if self.telegram:
            await self.telegram.send_message(
                f"💰 <b>DCA EXECUTED:</b> {pos.symbol}\n"
                f"Level: {level.level}/{pos.max_dca_levels}\n"
                f"Price: ${price:.6f}\n"
                f"Amount: ${level.amount_usd:.2f}\n"
                f"New Avg: ${pos.avg_entry:.6f}"
            )
    
    def get_position(self, position_id: str) -> Optional[DCAPosition]:
        """Получить позицию"""
        return self.positions.get(position_id)
    
    def get_unrealized_pnl(self, position_id: str, current_price: float) -> float:
        """Получить нереализованный P&L"""
        pos = self.positions.get(position_id)
        if not pos:
            return 0
        
        if pos.is_short:
            pnl = (pos.avg_entry - current_price) * pos.total_amount
        else:
            pnl = (current_price - pos.avg_entry) * pos.total_amount
        
        return pnl
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return self.stats


class BreakevenMover:
    """
    🔒 Breakeven Mover
    
    Автоматический перенос стоп-лосса в безубыток
    после достижения определённого профита
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Tracked positions
        self.positions: Dict[str, dict] = {}
        
        # Default config
        self.default_config = BreakevenConfig()
        
        # Callbacks
        self._callbacks: List[Callable] = []
        
        # Stats
        self.stats = {
            'breakevens_moved': 0,
            'positions_tracked': 0
        }
    
    def on_breakeven(self, callback: Callable):
        """Callback при переносе в BE"""
        self._callbacks.append(callback)
    
    def track_position(
        self,
        position_id: str,
        symbol: str,
        entry_price: float,
        current_stop: float,
        is_short: bool = True,
        config: BreakevenConfig = None
    ):
        """
        Отслеживать позицию для BE
        """
        cfg = config or self.default_config
        
        self.positions[position_id] = {
            'symbol': symbol,
            'entry_price': entry_price,
            'current_stop': current_stop,
            'is_short': is_short,
            'config': cfg,
            'breakeven_price': self._calc_breakeven(entry_price, cfg.buffer_pct, is_short),
            'activated': False,
            'activated_at': 0
        }
        
        self.stats['positions_tracked'] = len(self.positions)
    
    def _calc_breakeven(
        self,
        entry: float,
        buffer_pct: float,
        is_short: bool
    ) -> float:
        """Рассчитать цену безубытка"""
        if is_short:
            # For short: BE is slightly below entry
            return entry * (1 - buffer_pct / 100)
        else:
            # For long: BE is slightly above entry
            return entry * (1 + buffer_pct / 100)
    
    async def check_price(self, symbol: str, current_price: float) -> List[str]:
        """
        Проверить цену и активировать BE
        
        Returns:
            List позиций где активирован BE
        """
        activated = []
        
        for pos_id, data in list(self.positions.items()):
            if data['symbol'] != symbol:
                continue
            
            if data['activated']:
                continue
            
            config: BreakevenConfig = data['config']
            entry = data['entry_price']
            is_short = data['is_short']
            
            # Calculate current profit %
            if is_short:
                profit_pct = ((entry - current_price) / entry) * 100
            else:
                profit_pct = ((current_price - entry) / entry) * 100
            
            # Check if trigger hit
            if profit_pct >= config.trigger_profit_pct:
                await self._activate_breakeven(pos_id, data, current_price)
                activated.append(pos_id)
        
        return activated
    
    async def _activate_breakeven(self, pos_id: str, data: dict, price: float):
        """Активировать breakeven"""
        data['activated'] = True
        data['activated_at'] = int(time.time() * 1000)
        
        old_stop = data['current_stop']
        new_stop = data['breakeven_price']
        data['current_stop'] = new_stop
        
        self.stats['breakevens_moved'] += 1
        
        logger.info(
            f"Breakeven activated: {data['symbol']} "
            f"SL: ${old_stop:.6f} -> ${new_stop:.6f}"
        )
        
        if self.telegram and data['config'].notify:
            await self.telegram.send_message(
                f"🔒 <b>BREAKEVEN:</b> {data['symbol']}\n"
                f"Price: ${price:.6f}\n"
                f"SL moved: ${old_stop:.6f} → ${new_stop:.6f}\n"
                f"<i>Position now risk-free!</i>"
            )
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(pos_id, old_stop, new_stop)
                else:
                    callback(pos_id, old_stop, new_stop)
            except Exception as e:
                logger.error(f"BE callback error: {e}")
    
    def remove_position(self, position_id: str):
        """Удалить позицию"""
        if position_id in self.positions:
            del self.positions[position_id]
            self.stats['positions_tracked'] = len(self.positions)
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return self.stats

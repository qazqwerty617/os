"""
MEXC Pump Monitor - DCA Engine
Dollar Cost Averaging and Breakeven Calculator
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum

logger = logging.getLogger("DCAEngine")


class DCAStrategy(Enum):
    FIXED = "fixed"           # Fixed intervals
    MARTINGALE = "martingale" # Double down on dips
    FIBONACCI = "fibonacci"   # Fib-scaled additions
    SMART = "smart"           # AI-adjusted


@dataclass
class DCALevel:
    """Single DCA level"""
    level: int
    trigger_pct: float      # % drop from entry to trigger
    size_multiplier: float  # Size relative to base
    executed: bool = False
    execution_price: Optional[float] = None
    execution_time: Optional[datetime] = None


@dataclass 
class DCAPosition:
    """Position with DCA tracking"""
    symbol: str
    side: str  # LONG or SHORT
    base_entry: float
    base_size: float
    levels: List[DCALevel] = field(default_factory=list)
    total_size: float = 0.0
    average_entry: float = 0.0
    breakeven_price: float = 0.0
    
    def __post_init__(self):
        self.total_size = self.base_size
        self.average_entry = self.base_entry
        self.breakeven_price = self.base_entry


class DCAEngine:
    """
    Dollar Cost Averaging Engine
    - Manages layered entries
    - Calculates breakeven prices
    - Supports multiple strategies
    """
    
    def __init__(self, strategy: DCAStrategy = DCAStrategy.SMART, max_levels: int = 5):
        self.strategy = strategy
        self.max_levels = max_levels
        self.positions: Dict[str, DCAPosition] = {}
        
        # Default level configs by strategy
        self.level_configs = {
            DCAStrategy.FIXED: [
                (5.0, 1.0),   # 5% drop, same size
                (10.0, 1.0),
                (15.0, 1.0),
                (20.0, 1.0),
                (25.0, 1.0),
            ],
            DCAStrategy.MARTINGALE: [
                (5.0, 2.0),   # Double each level
                (10.0, 4.0),
                (15.0, 8.0),
                (20.0, 16.0),
            ],
            DCAStrategy.FIBONACCI: [
                (3.0, 1.0),
                (5.0, 1.0),
                (8.0, 2.0),
                (13.0, 3.0),
                (21.0, 5.0),
            ],
            DCAStrategy.SMART: [
                (4.0, 1.5),
                (8.0, 2.0),
                (12.0, 2.5),
                (18.0, 3.0),
            ],
        }
        
        logger.info(f"📊 DCA Engine initialized: {strategy.value}, max {max_levels} levels")
    
    def create_position(self, symbol: str, side: str, entry_price: float, 
                       base_size: float) -> DCAPosition:
        """Create new DCA-tracked position"""
        levels = []
        config = self.level_configs.get(self.strategy, self.level_configs[DCAStrategy.FIXED])
        
        for i, (trigger_pct, size_mult) in enumerate(config[:self.max_levels]):
            levels.append(DCALevel(
                level=i + 1,
                trigger_pct=trigger_pct,
                size_multiplier=size_mult
            ))
        
        position = DCAPosition(
            symbol=symbol,
            side=side,
            base_entry=entry_price,
            base_size=base_size,
            levels=levels
        )
        
        self.positions[symbol] = position
        logger.info(f"📈 DCA Position created: {symbol} @ {entry_price}, {len(levels)} levels")
        return position
    
    def check_triggers(self, symbol: str, current_price: float) -> Optional[DCALevel]:
        """Check if any DCA level should trigger"""
        position = self.positions.get(symbol)
        if not position:
            return None
        
        # Calculate price change from average entry
        if position.side == "LONG":
            change_pct = ((position.average_entry - current_price) / position.average_entry) * 100
        else:  # SHORT
            change_pct = ((current_price - position.average_entry) / position.average_entry) * 100
        
        for level in position.levels:
            if not level.executed and change_pct >= level.trigger_pct:
                return level
        
        return None
    
    def execute_level(self, symbol: str, level: DCALevel, execution_price: float) -> DCAPosition:
        """Execute a DCA level and recalculate averages"""
        position = self.positions.get(symbol)
        if not position:
            raise ValueError(f"No position found for {symbol}")
        
        # Calculate new size
        add_size = position.base_size * level.size_multiplier
        
        # Update position
        old_total = position.total_size
        old_avg = position.average_entry
        
        position.total_size += add_size
        position.average_entry = (
            (old_avg * old_total + execution_price * add_size) / position.total_size
        )
        
        # Mark level as executed
        level.executed = True
        level.execution_price = execution_price
        level.execution_time = datetime.now()
        
        # Calculate new breakeven (including ~0.1% fees for safety)
        fee_adjustment = 1.001 if position.side == "LONG" else 0.999
        position.breakeven_price = position.average_entry * fee_adjustment
        
        logger.info(f"💰 DCA Level {level.level} executed: {symbol} +{add_size:.4f} @ {execution_price}")
        logger.info(f"   New Avg: {position.average_entry:.6f}, Breakeven: {position.breakeven_price:.6f}")
        
        return position
    
    def get_breakeven(self, symbol: str) -> Optional[float]:
        """Get breakeven price for position"""
        position = self.positions.get(symbol)
        return position.breakeven_price if position else None
    
    def get_position_summary(self, symbol: str) -> Optional[Dict]:
        """Get full position summary"""
        position = self.positions.get(symbol)
        if not position:
            return None
        
        executed_levels = [l for l in position.levels if l.executed]
        pending_levels = [l for l in position.levels if not l.executed]
        
        return {
            "symbol": symbol,
            "side": position.side,
            "base_entry": position.base_entry,
            "average_entry": position.average_entry,
            "breakeven": position.breakeven_price,
            "total_size": position.total_size,
            "levels_executed": len(executed_levels),
            "levels_remaining": len(pending_levels),
            "next_trigger_pct": pending_levels[0].trigger_pct if pending_levels else None
        }
    
    def close_position(self, symbol: str):
        """Remove position from tracking"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"🔴 DCA Position closed: {symbol}")


# Convenience instance
dca_engine = DCAEngine()

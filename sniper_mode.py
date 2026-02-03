"""
MEXC Pump Monitor - Sniper Mode
Мгновенный вход в позицию при детекции сильного сигнала
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SniperTrigger(Enum):
    """Триггеры для снайпера"""
    NEW_LISTING = "new_listing"           # Новый листинг
    WHALE_BUY = "whale_buy"               # Покупка китом
    PUMP_DETECTED = "pump_detected"       # Детекция пампа
    BREAKOUT = "breakout"                 # Пробой уровня
    VOLUME_SPIKE = "volume_spike"         # Всплеск объёма
    CUSTOM = "custom"                     # Кастомный триггер


@dataclass
class SniperTarget:
    """Цель для снайпинга"""
    target_id: str
    symbol: str
    trigger: SniperTrigger
    
    # Entry params
    entry_type: str  # 'market' or 'limit'
    position_size_usd: float
    leverage: int
    direction: str  # 'long' or 'short'
    
    # Limits
    max_entry_price: float = 0  # Don't buy above this
    min_entry_price: float = 0  # Don't buy below this
    max_slippage_pct: float = 1.0
    
    # Auto SL/TP
    auto_stop_loss_pct: float = 3.0
    auto_take_profit_pct: float = 6.0
    
    # Time limits
    expires_at: int = 0  # 0 = never expires
    
    # Status
    is_active: bool = True
    triggered: bool = False
    triggered_at: int = 0
    entry_price: float = 0
    
    # Conditions (optional filters)
    min_volume_usd: float = 0
    min_price_change_pct: float = 0
    required_quality: str = ""  # 'S', 'A', 'B', etc.


@dataclass
class SniperResult:
    """Результат снайпинга"""
    target_id: str
    success: bool
    entry_price: float
    filled_size: float
    slippage_pct: float
    execution_time_ms: int
    error: str = ""


class SniperMode:
    """
    🎯 Sniper Mode
    
    Мгновенный вход при детекции цели:
    - Новые листинги
    - Покупки китов
    - Пробои уровней
    - Всплески объёма
    
    Фичи:
    - Предустановленные цели
    - Авто SL/TP
    - Контроль слиппейджа
    - Время истечения
    """
    
    def __init__(
        self,
        mexc_client=None,
        telegram=None,
        auto_trader=None
    ):
        self.client = mexc_client
        self.telegram = telegram
        self.auto_trader = auto_trader
        
        # Active targets
        self.targets: Dict[str, SniperTarget] = {}
        
        # Results history
        self.results: List[SniperResult] = []
        self.max_results = 100
        
        # Event subscriptions
        self._triggers: Dict[SniperTrigger, List[SniperTarget]] = {
            t: [] for t in SniperTrigger
        }
        
        # Stats
        self.stats = {
            'targets_set': 0,
            'triggers_fired': 0,
            'successful_entries': 0,
            'failed_entries': 0,
            'total_slippage_pct': 0
        }
        
        self._running = False
    
    async def start(self):
        """Запустить снайпер"""
        self._running = True
        asyncio.create_task(self._cleanup_loop())
        logger.info("🎯 Sniper Mode activated")
    
    async def stop(self):
        """Остановить"""
        self._running = False
    
    def add_target(
        self,
        symbol: str,
        trigger: SniperTrigger,
        position_size_usd: float,
        leverage: int = 10,
        direction: str = 'long',
        entry_type: str = 'market',
        max_entry_price: float = 0,
        min_entry_price: float = 0,
        max_slippage_pct: float = 1.0,
        stop_loss_pct: float = 3.0,
        take_profit_pct: float = 6.0,
        expires_in_minutes: int = 0,
        min_volume_usd: float = 0,
        min_price_change_pct: float = 0,
        required_quality: str = ""
    ) -> str:
        """
        Добавить цель для снайпинга
        
        Returns:
            target_id
        """
        target_id = f"snipe_{symbol}_{int(time.time()*1000)}"
        
        expires_at = 0
        if expires_in_minutes > 0:
            expires_at = int(time.time() * 1000) + (expires_in_minutes * 60 * 1000)
        
        target = SniperTarget(
            target_id=target_id,
            symbol=symbol,
            trigger=trigger,
            entry_type=entry_type,
            position_size_usd=position_size_usd,
            leverage=leverage,
            direction=direction,
            max_entry_price=max_entry_price,
            min_entry_price=min_entry_price,
            max_slippage_pct=max_slippage_pct,
            auto_stop_loss_pct=stop_loss_pct,
            auto_take_profit_pct=take_profit_pct,
            expires_at=expires_at,
            min_volume_usd=min_volume_usd,
            min_price_change_pct=min_price_change_pct,
            required_quality=required_quality
        )
        
        self.targets[target_id] = target
        self._triggers[trigger].append(target)
        
        self.stats['targets_set'] += 1
        
        logger.info(f"🎯 Sniper target set: {symbol} on {trigger.value}")
        
        return target_id
    
    def remove_target(self, target_id: str):
        """Удалить цель"""
        target = self.targets.pop(target_id, None)
        if target:
            self._triggers[target.trigger] = [
                t for t in self._triggers[target.trigger]
                if t.target_id != target_id
            ]
    
    async def on_event(
        self,
        trigger: SniperTrigger,
        symbol: str,
        data: Dict[str, Any]
    ):
        """
        Обработать событие
        
        Args:
            trigger: Тип триггера
            symbol: Символ
            data: Дополнительные данные (price, volume, etc.)
        """
        targets = [
            t for t in self._triggers.get(trigger, [])
            if t.symbol == symbol and t.is_active and not t.triggered
        ]
        
        for target in targets:
            # Check if valid
            if not self._validate_target(target, data):
                continue
            
            # Fire!
            await self._fire_target(target, data)
    
    def _validate_target(self, target: SniperTarget, data: Dict) -> bool:
        """Проверить цель перед выстрелом"""
        now = int(time.time() * 1000)
        
        # Check expiration
        if target.expires_at > 0 and now > target.expires_at:
            target.is_active = False
            return False
        
        price = data.get('price', 0)
        
        # Check price limits
        if target.max_entry_price > 0 and price > target.max_entry_price:
            return False
        
        if target.min_entry_price > 0 and price < target.min_entry_price:
            return False
        
        # Check volume
        if target.min_volume_usd > 0:
            volume = data.get('volume_usd', 0)
            if volume < target.min_volume_usd:
                return False
        
        # Check price change
        if target.min_price_change_pct > 0:
            change = abs(data.get('price_change_pct', 0))
            if change < target.min_price_change_pct:
                return False
        
        # Check quality
        if target.required_quality:
            quality = data.get('quality', '')
            if quality and quality > target.required_quality:
                return False
        
        return True
    
    async def _fire_target(self, target: SniperTarget, data: Dict):
        """Выстрелить! Войти в позицию"""
        start_time = time.time()
        
        target.triggered = True
        target.triggered_at = int(time.time() * 1000)
        
        self.stats['triggers_fired'] += 1
        
        price = data.get('price', 0)
        
        logger.info(f"🎯 SNIPER FIRING: {target.symbol} @ ${price}")
        
        # Send alert first
        if self.telegram:
            await self.telegram.send_message(
                f"🎯 <b>SNIPER FIRING!</b>\n\n"
                f"Symbol: {target.symbol}\n"
                f"Trigger: {target.trigger.value}\n"
                f"Direction: {target.direction.upper()}\n"
                f"Size: ${target.position_size_usd}\n"
                f"Leverage: {target.leverage}x\n"
                f"Price: ${price:.6f}"
            )
        
        result = SniperResult(
            target_id=target.target_id,
            success=False,
            entry_price=0,
            filled_size=0,
            slippage_pct=0,
            execution_time_ms=0
        )
        
        try:
            # Execute entry
            if self.auto_trader:
                # Use auto trader
                order_result = await self.auto_trader.open_position(
                    symbol=target.symbol,
                    side=target.direction,
                    amount_usd=target.position_size_usd,
                    leverage=target.leverage,
                    stop_loss_pct=target.auto_stop_loss_pct,
                    take_profit_pct=target.auto_take_profit_pct
                )
                
                if order_result and order_result.get('success'):
                    result.success = True
                    result.entry_price = order_result.get('entry_price', price)
                    result.filled_size = order_result.get('filled_size', 0)
                    
                    # Calculate slippage
                    if price > 0:
                        result.slippage_pct = abs(result.entry_price - price) / price * 100
                else:
                    result.error = order_result.get('error', 'Unknown error')
            
            elif self.client:
                # Direct API call (simulated for safety)
                logger.info(f"Would execute: {target.direction} {target.symbol} ${target.position_size_usd}")
                result.success = True
                result.entry_price = price
                result.slippage_pct = 0
            
            else:
                result.error = "No execution client configured"
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"Sniper execution error: {e}")
        
        # Calculate execution time
        result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        # Update stats
        if result.success:
            self.stats['successful_entries'] += 1
            self.stats['total_slippage_pct'] += result.slippage_pct
            target.entry_price = result.entry_price
            
            if self.telegram:
                await self.telegram.send_message(
                    f"✅ <b>SNIPER HIT!</b>\n\n"
                    f"Symbol: {target.symbol}\n"
                    f"Entry: ${result.entry_price:.6f}\n"
                    f"Slippage: {result.slippage_pct:.2f}%\n"
                    f"Execution: {result.execution_time_ms}ms"
                )
        else:
            self.stats['failed_entries'] += 1
            
            if self.telegram:
                await self.telegram.send_message(
                    f"❌ <b>SNIPER MISSED!</b>\n\n"
                    f"Symbol: {target.symbol}\n"
                    f"Error: {result.error}"
                )
        
        # Store result
        self.results.append(result)
        if len(self.results) > self.max_results:
            self.results = self.results[-self.max_results:]
        
        # Deactivate target
        target.is_active = False
        
        return result
    
    async def _cleanup_loop(self):
        """Очистка истёкших целей"""
        while self._running:
            try:
                now = int(time.time() * 1000)
                
                expired = [
                    tid for tid, t in self.targets.items()
                    if t.expires_at > 0 and now > t.expires_at and t.is_active
                ]
                
                for tid in expired:
                    self.targets[tid].is_active = False
                    logger.debug(f"Sniper target expired: {tid}")
                
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Sniper cleanup error: {e}")
    
    def get_active_targets(self) -> List[SniperTarget]:
        """Получить активные цели"""
        return [t for t in self.targets.values() if t.is_active and not t.triggered]
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        avg_slippage = (
            self.stats['total_slippage_pct'] / self.stats['successful_entries']
            if self.stats['successful_entries'] > 0 else 0
        )
        
        return {
            **self.stats,
            'active_targets': len(self.get_active_targets()),
            'avg_slippage_pct': round(avg_slippage, 3),
            'hit_rate': (
                self.stats['successful_entries'] / self.stats['triggers_fired']
                if self.stats['triggers_fired'] > 0 else 0
            )
        }

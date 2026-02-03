"""
MEXC Pump Monitor - Smart Alerts
Настраиваемые алерты с гибкими условиями
"""

import asyncio
import logging
import time
import re
from typing import Dict, List, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AlertCondition(Enum):
    """Типы условий"""
    PRICE_ABOVE = "price_above"
    PRICE_BELOW = "price_below"
    PRICE_CHANGE_PCT = "price_change_pct"
    VOLUME_ABOVE = "volume_above"
    RSI_ABOVE = "rsi_above"
    RSI_BELOW = "rsi_below"
    PUMP_DETECTED = "pump_detected"
    WHALE_ACTIVITY = "whale_activity"
    NEW_LISTING = "new_listing"
    CUSTOM = "custom"


class AlertPriority(Enum):
    """Приоритеты"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class AlertRule:
    """Правило алерта"""
    rule_id: str
    name: str
    
    # Target
    symbol: str  # '*' for all symbols
    
    # Condition
    condition: AlertCondition
    threshold: float
    comparison: str = ">"  # >, <, >=, <=, ==
    
    # Settings
    priority: AlertPriority = AlertPriority.MEDIUM
    cooldown_seconds: int = 300  # Min time between alerts
    max_triggers: int = 0  # 0 = unlimited
    expires_at: int = 0  # 0 = never
    
    # Status
    is_active: bool = True
    trigger_count: int = 0
    last_triggered: int = 0
    
    # Custom message template
    message_template: str = ""
    
    # Sound/notification settings
    play_sound: bool = False
    send_telegram: bool = True


@dataclass
class AlertEvent:
    """Событие алерта"""
    rule_id: str
    symbol: str
    timestamp: int
    
    # Data
    condition: AlertCondition
    value: float
    threshold: float
    
    # Message
    message: str
    priority: AlertPriority


class SmartAlerts:
    """
    🔔 Smart Alerts
    
    Гибкие настраиваемые алерты:
    - Цена выше/ниже уровня
    - Изменение цены в %
    - RSI перекуплен/перепродан
    - Объём выше порога
    - Кастомные условия
    
    Фичи:
    - Cooldown между алертами
    - Лимит срабатываний
    - Время истечения
    - Шаблоны сообщений
    - Приоритеты
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Active rules
        self.rules: Dict[str, AlertRule] = {}
        
        # Event history
        self.events: List[AlertEvent] = []
        self.max_events = 500
        
        # Rate limiting
        self._last_alert_time: Dict[str, int] = {}
        
        # Custom handlers
        self._custom_handlers: Dict[str, Callable] = {}
        
        # Stats
        self.stats = {
            'rules_created': 0,
            'alerts_triggered': 0,
            'alerts_sent': 0,
            'alerts_suppressed': 0
        }
    
    def create_rule(
        self,
        name: str,
        symbol: str,
        condition: AlertCondition,
        threshold: float,
        comparison: str = ">",
        priority: AlertPriority = AlertPriority.MEDIUM,
        cooldown: int = 300,
        max_triggers: int = 0,
        expires_in_hours: int = 0,
        message_template: str = "",
        send_telegram: bool = True
    ) -> str:
        """
        Создать правило алерта
        
        Returns:
            rule_id
        """
        rule_id = f"alert_{symbol}_{condition.value}_{int(time.time()*1000)}"
        
        expires_at = 0
        if expires_in_hours > 0:
            expires_at = int(time.time() * 1000) + (expires_in_hours * 3600 * 1000)
        
        rule = AlertRule(
            rule_id=rule_id,
            name=name,
            symbol=symbol.upper(),
            condition=condition,
            threshold=threshold,
            comparison=comparison,
            priority=priority,
            cooldown_seconds=cooldown,
            max_triggers=max_triggers,
            expires_at=expires_at,
            message_template=message_template,
            send_telegram=send_telegram
        )
        
        self.rules[rule_id] = rule
        self.stats['rules_created'] += 1
        
        logger.info(f"🔔 Alert rule created: {name} ({symbol} {condition.value})")
        
        return rule_id
    
    def delete_rule(self, rule_id: str):
        """Удалить правило"""
        if rule_id in self.rules:
            del self.rules[rule_id]
    
    def disable_rule(self, rule_id: str):
        """Отключить правило"""
        if rule_id in self.rules:
            self.rules[rule_id].is_active = False
    
    def enable_rule(self, rule_id: str):
        """Включить правило"""
        if rule_id in self.rules:
            self.rules[rule_id].is_active = True
    
    async def check(self, symbol: str, data: Dict[str, Any]):
        """
        Проверить все правила для символа
        
        Args:
            symbol: Символ
            data: Данные (price, volume, rsi, price_change_pct, etc.)
        """
        symbol = symbol.upper()
        now = int(time.time() * 1000)
        
        for rule in list(self.rules.values()):
            # Check if rule applies
            if not self._rule_applies(rule, symbol, now):
                continue
            
            # Get value to check
            value = self._get_value(rule.condition, data)
            
            if value is None:
                continue
            
            # Check condition
            if self._check_condition(value, rule.threshold, rule.comparison):
                await self._trigger_alert(rule, symbol, value, data)
    
    def _rule_applies(self, rule: AlertRule, symbol: str, now: int) -> bool:
        """Проверить применимость правила"""
        if not rule.is_active:
            return False
        
        # Symbol match
        if rule.symbol != '*' and rule.symbol != symbol:
            return False
        
        # Expiration
        if rule.expires_at > 0 and now > rule.expires_at:
            rule.is_active = False
            return False
        
        # Max triggers
        if rule.max_triggers > 0 and rule.trigger_count >= rule.max_triggers:
            rule.is_active = False
            return False
        
        # Cooldown
        if rule.last_triggered > 0:
            elapsed = (now - rule.last_triggered) / 1000
            if elapsed < rule.cooldown_seconds:
                return False
        
        return True
    
    def _get_value(self, condition: AlertCondition, data: Dict) -> Optional[float]:
        """Получить значение для проверки"""
        mapping = {
            AlertCondition.PRICE_ABOVE: 'price',
            AlertCondition.PRICE_BELOW: 'price',
            AlertCondition.PRICE_CHANGE_PCT: 'price_change_pct',
            AlertCondition.VOLUME_ABOVE: 'volume',
            AlertCondition.RSI_ABOVE: 'rsi',
            AlertCondition.RSI_BELOW: 'rsi',
        }
        
        key = mapping.get(condition)
        if key:
            return data.get(key)
        
        return None
    
    def _check_condition(self, value: float, threshold: float, comparison: str) -> bool:
        """Проверить условие"""
        if comparison == ">":
            return value > threshold
        elif comparison == "<":
            return value < threshold
        elif comparison == ">=":
            return value >= threshold
        elif comparison == "<=":
            return value <= threshold
        elif comparison == "==":
            return abs(value - threshold) < 0.0001
        return False
    
    async def _trigger_alert(
        self,
        rule: AlertRule,
        symbol: str,
        value: float,
        data: Dict
    ):
        """Триггер алерта"""
        now = int(time.time() * 1000)
        
        rule.trigger_count += 1
        rule.last_triggered = now
        
        self.stats['alerts_triggered'] += 1
        
        # Build message
        message = self._build_message(rule, symbol, value, data)
        
        # Create event
        event = AlertEvent(
            rule_id=rule.rule_id,
            symbol=symbol,
            timestamp=now,
            condition=rule.condition,
            value=value,
            threshold=rule.threshold,
            message=message,
            priority=rule.priority
        )
        
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
        
        logger.info(f"🔔 Alert: {rule.name} - {symbol}")
        
        # Send notification
        if rule.send_telegram and self.telegram:
            await self.telegram.send_message(message)
            self.stats['alerts_sent'] += 1
    
    def _build_message(
        self,
        rule: AlertRule,
        symbol: str,
        value: float,
        data: Dict
    ) -> str:
        """Построить сообщение"""
        # Priority emoji
        priority_emoji = {
            AlertPriority.LOW: "ℹ️",
            AlertPriority.MEDIUM: "🔔",
            AlertPriority.HIGH: "⚠️",
            AlertPriority.CRITICAL: "🚨"
        }
        
        emoji = priority_emoji.get(rule.priority, "🔔")
        
        # Condition description
        condition_desc = {
            AlertCondition.PRICE_ABOVE: f"Price above ${rule.threshold}",
            AlertCondition.PRICE_BELOW: f"Price below ${rule.threshold}",
            AlertCondition.PRICE_CHANGE_PCT: f"Price change {rule.comparison} {rule.threshold}%",
            AlertCondition.VOLUME_ABOVE: f"Volume above ${rule.threshold:,.0f}",
            AlertCondition.RSI_ABOVE: f"RSI above {rule.threshold}",
            AlertCondition.RSI_BELOW: f"RSI below {rule.threshold}",
        }
        
        desc = condition_desc.get(rule.condition, rule.condition.value)
        
        # Custom template or default
        if rule.message_template:
            message = rule.message_template
            message = message.replace("{symbol}", symbol)
            message = message.replace("{value}", f"{value:.6f}")
            message = message.replace("{threshold}", f"{rule.threshold}")
            message = message.replace("{price}", f"${data.get('price', 0):.6f}")
        else:
            message = f"""
{emoji} <b>SMART ALERT</b>

📊 <b>{symbol}</b>
🎯 {rule.name}

{desc}
Current: {value:.6f}

⏰ {time.strftime('%H:%M:%S')}
"""
        
        return message
    
    async def trigger_event(
        self,
        condition: AlertCondition,
        symbol: str,
        data: Dict = None
    ):
        """
        Триггер события напрямую
        
        Используется для событий типа NEW_LISTING, WHALE_ACTIVITY
        """
        data = data or {}
        
        for rule in list(self.rules.values()):
            if rule.condition != condition:
                continue
            
            if not self._rule_applies(rule, symbol, int(time.time() * 1000)):
                continue
            
            await self._trigger_alert(rule, symbol, 0, data)
    
    # === Preset Alert Templates ===
    
    def add_price_alert(
        self,
        symbol: str,
        price: float,
        direction: str = "above",
        priority: AlertPriority = AlertPriority.MEDIUM
    ) -> str:
        """Добавить ценовой алерт"""
        condition = AlertCondition.PRICE_ABOVE if direction == "above" else AlertCondition.PRICE_BELOW
        name = f"{symbol} Price {direction.title()} ${price}"
        
        return self.create_rule(
            name=name,
            symbol=symbol,
            condition=condition,
            threshold=price,
            priority=priority,
            max_triggers=1
        )
    
    def add_rsi_alert(
        self,
        symbol: str,
        rsi_level: float,
        direction: str = "above"
    ) -> str:
        """Добавить RSI алерт"""
        condition = AlertCondition.RSI_ABOVE if direction == "above" else AlertCondition.RSI_BELOW
        name = f"{symbol} RSI {direction} {rsi_level}"
        
        return self.create_rule(
            name=name,
            symbol=symbol,
            condition=condition,
            threshold=rsi_level,
            priority=AlertPriority.HIGH,
            cooldown=600
        )
    
    def add_pump_alert(self, symbol: str = "*", min_change_pct: float = 5.0) -> str:
        """Добавить алерт на памп"""
        return self.create_rule(
            name=f"Pump Alert {min_change_pct}%+",
            symbol=symbol,
            condition=AlertCondition.PRICE_CHANGE_PCT,
            threshold=min_change_pct,
            comparison=">=",
            priority=AlertPriority.HIGH,
            cooldown=600
        )
    
    def get_active_rules(self) -> List[AlertRule]:
        """Получить активные правила"""
        return [r for r in self.rules.values() if r.is_active]
    
    def get_recent_events(self, limit: int = 20) -> List[AlertEvent]:
        """Получить недавние события"""
        return self.events[-limit:]
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            **self.stats,
            'active_rules': len(self.get_active_rules()),
            'total_rules': len(self.rules)
        }

"""
MEXC Pump Monitor - Smart Alerts
Optimized customizable alerts with flexible conditions
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AlertCondition(Enum):
    """Condition types"""
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
    """Alert priorities"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Condition to data key mapping
CONDITION_DATA_KEYS = {
    AlertCondition.PRICE_ABOVE: 'price',
    AlertCondition.PRICE_BELOW: 'price',
    AlertCondition.PRICE_CHANGE_PCT: 'price_change_pct',
    AlertCondition.VOLUME_ABOVE: 'volume',
    AlertCondition.RSI_ABOVE: 'rsi',
    AlertCondition.RSI_BELOW: 'rsi',
}

# Priority emojis
PRIORITY_EMOJIS = {
    AlertPriority.LOW: "ℹ️",
    AlertPriority.MEDIUM: "🔔",
    AlertPriority.HIGH: "⚠️",
    AlertPriority.CRITICAL: "🚨"
}


@dataclass
class AlertRule:
    """Alert rule"""
    rule_id: str
    name: str
    symbol: str
    condition: AlertCondition
    threshold: float
    comparison: str = ">"
    priority: AlertPriority = AlertPriority.MEDIUM
    cooldown_seconds: int = 300
    max_triggers: int = 0
    expires_at: int = 0
    is_active: bool = True
    trigger_count: int = 0
    last_triggered: int = 0
    message_template: str = ""
    play_sound: bool = False
    send_telegram: bool = True


@dataclass
class AlertEvent:
    """Alert event"""
    rule_id: str
    symbol: str
    timestamp: int
    condition: AlertCondition
    value: float
    threshold: float
    message: str
    priority: AlertPriority


class SmartAlerts:
    """
    Optimized Smart Alerts
    
    Features:
    - Price above/below levels
    - Price change percentage
    - RSI overbought/oversold
    - Volume threshold alerts
    - Custom conditions
    - Cooldowns (rate limiting) between alerts
    - Max trigger limits
    - Expiration time
    - Message templates
    """
    
    # Comparison operators
    COMPARISONS = {
        '>': lambda v, t: v > t,
        '<': lambda v, t: v < t,
        '>=': lambda v, t: v >= t,
        '<=': lambda v, t: v <= t,
        '==': lambda v, t: abs(v - t) < 0.0001,
    }
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        self.rules: Dict[str, AlertRule] = {}
        self.events: List[AlertEvent] = []
        self.max_events = 500
        self._last_alert_time: Dict[str, int] = {}
        self._custom_handlers: Dict[str, Callable] = {}
        
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
        """Create alert rule"""
        rule_id = f"alert_{symbol}_{condition.value}_{int(time.time()*1000)}"
        
        expires_at = (int(time.time() * 1000) + (expires_in_hours * 3600000)) if expires_in_hours > 0 else 0
        
        self.rules[rule_id] = AlertRule(
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
        
        self.stats['rules_created'] += 1
        logger.info(f"🔔 Alert rule: {name} ({symbol} {condition.value})")
        
        return rule_id
    
    def delete_rule(self, rule_id: str):
        self.rules.pop(rule_id, None)
    
    def disable_rule(self, rule_id: str):
        if rule_id in self.rules:
            self.rules[rule_id].is_active = False
    
    def enable_rule(self, rule_id: str):
        if rule_id in self.rules:
            self.rules[rule_id].is_active = True
    
    async def check(self, symbol: str, data: Dict[str, Any]):
        """Check all rules for symbol"""
        symbol = symbol.upper()
        now = int(time.time() * 1000)
        
        for rule in list(self.rules.values()):
            if not self._rule_applies(rule, symbol, now):
                continue
            
            key = CONDITION_DATA_KEYS.get(rule.condition)
            value = data.get(key) if key else None
            
            if value is None:
                continue
            
            comparator = self.COMPARISONS.get(rule.comparison)
            if comparator and comparator(value, rule.threshold):
                await self._trigger_alert(rule, symbol, value, data)
    
    def _rule_applies(self, rule: AlertRule, symbol: str, now: int) -> bool:
        """Check if rule applies"""
        if not rule.is_active:
            return False
        
        if rule.symbol != '*' and rule.symbol != symbol:
            return False
        
        if rule.expires_at > 0 and now > rule.expires_at:
            rule.is_active = False
            return False
        
        if rule.max_triggers > 0 and rule.trigger_count >= rule.max_triggers:
            rule.is_active = False
            return False
        
        if rule.last_triggered > 0:
            elapsed_sec = (now - rule.last_triggered) / 1000
            if elapsed_sec < rule.cooldown_seconds:
                return False
        
        return True
    
    async def _trigger_alert(self, rule: AlertRule, symbol: str, value: float, data: Dict):
        """Trigger alert"""
        now = int(time.time() * 1000)
        
        rule.trigger_count += 1
        rule.last_triggered = now
        self.stats['alerts_triggered'] += 1
        
        message = self._build_message(rule, symbol, value, data)
        
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
        
        if rule.send_telegram and self.telegram:
            await self.telegram.send_message(message)
            self.stats['alerts_sent'] += 1
    
    def _build_message(self, rule: AlertRule, symbol: str, value: float, data: Dict) -> str:
        """Build alert message"""
        emoji = PRIORITY_EMOJIS.get(rule.priority, "🔔")
        
        condition_desc = {
            AlertCondition.PRICE_ABOVE: f"Price above ${rule.threshold}",
            AlertCondition.PRICE_BELOW: f"Price below ${rule.threshold}",
            AlertCondition.PRICE_CHANGE_PCT: f"Price change {rule.comparison} {rule.threshold}%",
            AlertCondition.VOLUME_ABOVE: f"Volume above ${rule.threshold:,.0f}",
            AlertCondition.RSI_ABOVE: f"RSI above {rule.threshold}",
            AlertCondition.RSI_BELOW: f"RSI below {rule.threshold}",
        }.get(rule.condition, rule.condition.value)
        
        if rule.message_template:
            return (rule.message_template
                    .replace("{symbol}", symbol)
                    .replace("{value}", f"{value:.6f}")
                    .replace("{threshold}", f"{rule.threshold}")
                    .replace("{price}", f"${data.get('price', 0):.6f}"))
        
        return f"""
{emoji} <b>SMART ALERT</b>

📊 <b>{symbol}</b>
🎯 {rule.name}

{condition_desc}
Current: {value:.6f}

⏰ {time.strftime('%H:%M:%S')}
"""
    
    async def trigger_event(self, condition: AlertCondition, symbol: str, data: Dict = None):
        """Trigger event directly (for NEW_LISTING, WHALE_ACTIVITY)"""
        data = data or {}
        now = int(time.time() * 1000)
        
        for rule in list(self.rules.values()):
            if rule.condition == condition and self._rule_applies(rule, symbol, now):
                await self._trigger_alert(rule, symbol, 0, data)
    
    # === Preset Templates ===
    
    def add_price_alert(
        self,
        symbol: str,
        price: float,
        direction: str = "above",
        priority: AlertPriority = AlertPriority.MEDIUM
    ) -> str:
        """Add price alert"""
        condition = AlertCondition.PRICE_ABOVE if direction == "above" else AlertCondition.PRICE_BELOW
        return self.create_rule(
            name=f"{symbol} Price {direction.title()} ${price}",
            symbol=symbol,
            condition=condition,
            threshold=price,
            priority=priority,
            max_triggers=1
        )
    
    def add_rsi_alert(self, symbol: str, rsi_level: float, direction: str = "above") -> str:
        """Add RSI alert"""
        condition = AlertCondition.RSI_ABOVE if direction == "above" else AlertCondition.RSI_BELOW
        return self.create_rule(
            name=f"{symbol} RSI {direction} {rsi_level}",
            symbol=symbol,
            condition=condition,
            threshold=rsi_level,
            priority=AlertPriority.HIGH,
            cooldown=600
        )
    
    def add_pump_alert(self, symbol: str = "*", min_change_pct: float = 5.0) -> str:
        """Add pump alert"""
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
        return [r for r in self.rules.values() if r.is_active]
    
    def get_recent_events(self, limit: int = 20) -> List[AlertEvent]:
        return self.events[-limit:]
    
    def get_stats(self) -> Dict:
        return {
            **self.stats,
            'active_rules': len(self.get_active_rules()),
            'total_rules': len(self.rules)
        }

"""
MEXC Pump Monitor - Event Calendar & Trading Signals
Tracks upcoming token events and generates trading recommendations
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of token events"""
    TOKEN_UNLOCK = "TOKEN_UNLOCK"       # Team/investor unlock
    AIRDROP = "AIRDROP"                 # Token airdrop
    CLIFF_END = "CLIFF_END"             # End of cliff period
    VESTING_END = "VESTING_END"         # Full vesting complete
    LISTING = "LISTING"                 # New exchange listing
    DELISTING = "DELISTING"             # Exchange delisting
    HALVING = "HALVING"                 # Supply halving
    STAKING_END = "STAKING_END"         # Staking period ends
    SNAPSHOT = "SNAPSHOT"               # Airdrop snapshot
    MAINNET = "MAINNET"                 # Mainnet launch
    UPGRADE = "UPGRADE"                 # Protocol upgrade
    BURN = "BURN"                       # Token burn event


class TradingAction(Enum):
    """Recommended trading actions"""
    LONG = "LONG"                       # Go long
    SHORT = "SHORT"                     # Go short
    AVOID = "AVOID"                     # Don't trade
    WATCH = "WATCH"                     # Monitor closely
    SCALP_LONG = "SCALP_LONG"          # Quick long
    SCALP_SHORT = "SCALP_SHORT"        # Quick short
    HEDGE = "HEDGE"                     # Hedge position


@dataclass
class TokenEvent:
    """Token event with trading implications"""
    symbol: str
    event_type: EventType
    date: datetime
    
    # Event details
    title: str
    description: str = ""
    
    # Amount (if applicable)
    amount: float = 0               # Token amount
    amount_pct: float = 0           # % of supply
    usd_value: float = 0            # USD value
    
    # Category
    category: str = ""              # Team, Investors, Ecosystem, etc.
    
    # Trading signal
    trading_action: TradingAction = TradingAction.WATCH
    signal_strength: int = 50       # 0-100
    reasoning: str = ""
    
    # Timing
    days_until: int = 0
    hours_until: int = 0
    
    # Impact prediction
    expected_price_impact: str = ""  # e.g., "-5% to -15%"
    volatility_expected: str = ""    # HIGH, MEDIUM, LOW
    
    def is_upcoming(self, days: int = 7) -> bool:
        """Check if event is within next N days"""
        return 0 <= self.days_until <= days
    
    def is_imminent(self, hours: int = 24) -> bool:
        """Check if event is within next N hours"""
        total_hours = self.days_until * 24 + self.hours_until
        return 0 <= total_hours <= hours
    
    def format_countdown(self) -> str:
        """Format time until event"""
        if self.days_until > 0:
            return f"{self.days_until}d {self.hours_until}h"
        elif self.hours_until > 0:
            return f"{self.hours_until}h"
        else:
            return "NOW"
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'event_type': self.event_type.value,
            'date': self.date.isoformat(),
            'title': self.title,
            'description': self.description,
            'amount_pct': self.amount_pct,
            'usd_value': self.usd_value,
            'category': self.category,
            'trading_action': self.trading_action.value,
            'signal_strength': self.signal_strength,
            'reasoning': self.reasoning,
            'days_until': self.days_until,
            'expected_impact': self.expected_price_impact,
            'volatility': self.volatility_expected
        }


class EventCalendar:
    """
    Tracks upcoming token events and generates trading signals
    
    Key events that affect price:
    - Token unlocks → Usually bearish (sell pressure)
    - Airdrops → Bearish after (recipients dump)
    - Cliff ends → Major unlock incoming
    - Listings → Often bullish short-term
    """
    
    # Торговые сигналы по типам событий
    EVENT_SIGNALS = {
        EventType.TOKEN_UNLOCK: {
            'action': TradingAction.SHORT,
            'timing': 'before',
            'reasoning': 'Анлок создаёт давление на продажу - холдеры дампят токены',
            'expected_impact': '-5% до -20%',
            'volatility': 'ВЫСОКАЯ'
        },
        EventType.AIRDROP: {
            'action': TradingAction.SHORT,
            'timing': 'after',
            'reasoning': 'Получатели дропа обычно сразу продают',
            'expected_impact': '-10% до -30%',
            'volatility': 'ВЫСОКАЯ'
        },
        EventType.CLIFF_END: {
            'action': TradingAction.SHORT,
            'timing': 'before',
            'reasoning': 'Крупный анлок, ожидается сильное давление на продажу',
            'expected_impact': '-10% до -25%',
            'volatility': 'ВЫСОКАЯ'
        },
        EventType.VESTING_END: {
            'action': TradingAction.SHORT,
            'timing': 'before',
            'reasoning': 'Последние токены разлочены, команда/инвесторы могут выйти',
            'expected_impact': '-5% до -15%',
            'volatility': 'СРЕДНЯЯ'
        },
        EventType.LISTING: {
            'action': TradingAction.SCALP_LONG,
            'timing': 'before',
            'reasoning': 'Новые листинги часто пампят на хайпе, потом дамп',
            'expected_impact': '+20% до +100% потом -30%',
            'volatility': 'ЭКСТРИМ'
        },
        EventType.DELISTING: {
            'action': TradingAction.SHORT,
            'timing': 'before',
            'reasoning': 'Делистинг вызывает панические продажи',
            'expected_impact': '-30% до -70%',
            'volatility': 'ЭКСТРИМ'
        },
        EventType.SNAPSHOT: {
            'action': TradingAction.LONG,
            'timing': 'before',
            'reasoning': 'Покупатели накапливают перед снэпшотом для дропа',
            'expected_impact': '+10% до +30%',
            'volatility': 'СРЕДНЯЯ'
        },
        EventType.MAINNET: {
            'action': TradingAction.WATCH,
            'timing': 'before',
            'reasoning': 'Обычно бычий, но рискованно - может пампнуть или дампнуть',
            'expected_impact': '-20% до +50%',
            'volatility': 'ЭКСТРИМ'
        },
        EventType.BURN: {
            'action': TradingAction.SCALP_LONG,
            'timing': 'before',
            'reasoning': 'Сокращение саплая - бычий сигнал',
            'expected_impact': '+5% до +20%',
            'volatility': 'СРЕДНЯЯ'
        },
    }
    
    def __init__(self):
        # All events
        self.events: List[TokenEvent] = []
        
        # Stats
        self.stats = {
            'events_tracked': 0,
            'signals_generated': 0
        }
        
        # Pre-populated events (known schedule)
        self._load_known_events()
    
    def _load_known_events(self):
        """Load known upcoming events"""
        now = datetime.now()
        
        # Основные анлоки токенов (обновлять регулярно)
        known_events = [
            # ARB
            TokenEvent(
                symbol='ARB',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 3, 16),
                title='ARB Анлок Команды',
                amount_pct=2.75,
                usd_value=270_000_000,
                category='Команда',
                description='Ежемесячный анлок токенов команды'
            ),
            # OP
            TokenEvent(
                symbol='OP',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 2, 29),
                title='OP Анлок Инвесторов',
                amount_pct=2.0,
                category='Инвесторы'
            ),
            # SUI
            TokenEvent(
                symbol='SUI',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 3, 3),
                title='SUI Крупный Анлок',
                amount_pct=4.0,
                category='Команда + Инвесторы'
            ),
            # APT
            TokenEvent(
                symbol='APT',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 3, 12),
                title='APT Месячный Анлок',
                amount_pct=2.5,
                category='Фонд'
            ),
            # TIA
            TokenEvent(
                symbol='TIA',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 10, 31),
                title='TIA Конец Клифа',
                amount_pct=30.0,
                category='Команда + Инвесторы',
                description='ВАЖНО: Клиф заканчивается, первый большой анлок'
            ),
            # JUP
            TokenEvent(
                symbol='JUP',
                event_type=EventType.AIRDROP,
                date=datetime(2024, 1, 31),
                title='JUP Дроп #1',
                amount_pct=40.0,
                category='Комьюнити',
                description='Первый 40% дроп для комьюнити'
            ),
            # STRK
            TokenEvent(
                symbol='STRK',
                event_type=EventType.AIRDROP,
                date=datetime(2024, 2, 20),
                title='STRK Дроп',
                amount_pct=9.0,
                category='Комьюнити'
            ),
            # WLD
            TokenEvent(
                symbol='WLD',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 7, 24),
                title='WLD Конец Клифа',
                amount_pct=20.0,
                category='Команда',
                description='Клиф команды заканчивается'
            ),
            # SEI
            TokenEvent(
                symbol='SEI',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 2, 15),
                title='SEI Анлок Экосистемы',
                amount_pct=3.0,
                category='Экосистема'
            ),
            # PYTH
            TokenEvent(
                symbol='PYTH',
                event_type=EventType.TOKEN_UNLOCK,
                date=datetime(2024, 5, 20),
                title='PYTH Конец Клифа',
                amount_pct=15.0,
                category='Команда + Инвесторы',
                description='6-месячный клиф заканчивается'
            ),
        ]
        
        for event in known_events:
            self.add_event(event)
    
    def add_event(self, event: TokenEvent):
        """Add event and calculate trading signal"""
        now = datetime.now()
        
        # Calculate time until
        delta = event.date - now
        event.days_until = max(0, delta.days)
        event.hours_until = max(0, delta.seconds // 3600)
        
        # Generate trading signal
        self._generate_signal(event)
        
        self.events.append(event)
        self.stats['events_tracked'] = len(self.events)
    
    def _generate_signal(self, event: TokenEvent):
        """Generate trading signal for event"""
        signal_config = self.EVENT_SIGNALS.get(event.event_type)
        
        if not signal_config:
            event.trading_action = TradingAction.WATCH
            event.reasoning = "Неизвестный тип события, следи внимательно"
            return
        
        event.trading_action = signal_config['action']
        event.reasoning = signal_config['reasoning']
        event.expected_price_impact = signal_config['expected_impact']
        event.volatility_expected = signal_config['volatility']
        
        # Calculate signal strength based on size and timing
        strength = 50
        
        # Larger unlocks = stronger signal
        if event.amount_pct >= 10:
            strength += 30
        elif event.amount_pct >= 5:
            strength += 20
        elif event.amount_pct >= 2:
            strength += 10
        
        # Imminent events = stronger signal
        if event.days_until <= 1:
            strength += 20
        elif event.days_until <= 3:
            strength += 10
        elif event.days_until <= 7:
            strength += 5
        
        # Team/Investor unlocks are more impactful
        if 'team' in event.category.lower() or 'investor' in event.category.lower():
            strength += 10
        
        event.signal_strength = min(100, strength)
        self.stats['signals_generated'] += 1
    
    def get_upcoming_events(self, days: int = 7, symbol: str = None) -> List[TokenEvent]:
        """Get events in next N days"""
        events = [e for e in self.events if e.is_upcoming(days)]
        
        if symbol:
            events = [e for e in events if e.symbol.upper() == symbol.upper()]
        
        return sorted(events, key=lambda e: e.date)
    
    def get_imminent_events(self, hours: int = 24) -> List[TokenEvent]:
        """Get events in next N hours"""
        return [e for e in self.events if e.is_imminent(hours)]
    
    def get_short_opportunities(self, days: int = 7) -> List[TokenEvent]:
        """Get upcoming short opportunities (unlocks, airdrops)"""
        events = self.get_upcoming_events(days)
        return [
            e for e in events 
            if e.trading_action in [TradingAction.SHORT, TradingAction.SCALP_SHORT]
            and e.signal_strength >= 60
        ]
    
    def get_long_opportunities(self, days: int = 7) -> List[TokenEvent]:
        """Get upcoming long opportunities (snapshots, listings)"""
        events = self.get_upcoming_events(days)
        return [
            e for e in events 
            if e.trading_action in [TradingAction.LONG, TradingAction.SCALP_LONG]
            and e.signal_strength >= 60
        ]
    
    def get_token_events(self, symbol: str) -> List[TokenEvent]:
        """Get all events for a token"""
        return [e for e in self.events if e.symbol.upper() == symbol.upper()]
    
    def format_calendar(self, days: int = 7) -> str:
        """Форматировать календарь"""
        events = self.get_upcoming_events(days)
        
        if not events:
            return f"📅 Нет событий в ближайшие {days} дней"
        
        lines = [
            f"📅 БЛИЖАЙШИЕ СОБЫТИЯ (Следующие {days} дней)",
            "━" * 40
        ]
        
        for event in events:
            # Эмодзи действия
            action_emoji = {
                TradingAction.SHORT: "🔴",
                TradingAction.LONG: "🟢",
                TradingAction.SCALP_LONG: "🟡",
                TradingAction.SCALP_SHORT: "🟠",
                TradingAction.AVOID: "⚫",
                TradingAction.WATCH: "⚪",
                TradingAction.HEDGE: "🔵"
            }
            emoji = action_emoji.get(event.trading_action, "⚪")
            
            lines.append("")
            lines.append(f"{emoji} <b>{event.symbol}</b> - {event.title}")
            lines.append(f"   📆 {event.date.strftime('%Y-%m-%d')} ({event.format_countdown()})")
            
            if event.amount_pct > 0:
                lines.append(f"   📊 {event.amount_pct:.1f}% саплая")
            
            if event.category:
                lines.append(f"   👥 Категория: {event.category}")
            
            # Торговый сигнал
            lines.append(f"   💡 <b>{event.trading_action.value}</b> ({event.signal_strength}%)")
            lines.append(f"   📉 Ожидается: {event.expected_price_impact}")
            
            if event.reasoning:
                lines.append(f"   ℹ️ {event.reasoning}")
        
        return "\n".join(lines)
    
    def format_trading_signals(self) -> str:
        """Сформатировать торговые сигналы"""
        shorts = self.get_short_opportunities(14)
        longs = self.get_long_opportunities(14)
        
        lines = [
            "🎯 ТОРГОВЫЕ СИГНАЛЫ",
            "━" * 35
        ]
        
        if shorts:
            lines.append("")
            lines.append("🔴 <b>ШОРТ ВОЗМОЖНОСТИ:</b>")
            for e in shorts[:5]:
                lines.append(f"├ {e.symbol}: {e.title} ({e.format_countdown()})")
                lines.append(f"│  Сигнал: {e.signal_strength}% | Ожидается: {e.expected_price_impact}")
        
        if longs:
            lines.append("")
            lines.append("🟢 <b>ЛОНГ ВОЗМОЖНОСТИ:</b>")
            for e in longs[:5]:
                lines.append(f"├ {e.symbol}: {e.title} ({e.format_countdown()})")
                lines.append(f"│  Сигнал: {e.signal_strength}% | Ожидается: {e.expected_price_impact}")
        
        if not shorts and not longs:
            lines.append("")
            lines.append("Сильных сигналов сейчас нет")
        
        return "\n".join(lines)
    
    def get_token_summary(self, symbol: str) -> str:
        """Получить сводку событий по токену"""
        events = self.get_token_events(symbol)
        
        if not events:
            return f"Нет событий для {symbol.upper()}"
        
        lines = [
            f"📅 {symbol.upper()} КАЛЕНДАРЬ СОБЫТИЙ",
            "━" * 30
        ]
        
        for event in sorted(events, key=lambda e: e.date)[:5]:
            action_emoji = "🔴" if event.trading_action == TradingAction.SHORT else "🟢"
            
            lines.append("")
            lines.append(f"{action_emoji} {event.title}")
            lines.append(f"   📆 {event.date.strftime('%Y-%m-%d')} ({event.format_countdown()})")
            
            if event.amount_pct > 0:
                lines.append(f"   📊 {event.amount_pct:.1f}% анлок | {event.category}")
            
            lines.append(f"   💡 {event.trading_action.value} возможность")
            lines.append(f"   📉 Ожидается: {event.expected_price_impact}")
        
        return "\n".join(lines)

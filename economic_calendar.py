"""
MEXC Pump Monitor - Economic Calendar
Отслеживание важных экономических событий (CPI, FOMC, NFP и др.)
"""

import asyncio
import logging
import ssl
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class EventImpact(Enum):
    """Важность события"""
    LOW = "🟢 Low"
    MEDIUM = "🟡 Medium"
    HIGH = "🔴 High"
    CRITICAL = "💥 CRITICAL"


class EventType(Enum):
    """Тип события"""
    FED = "Federal Reserve"
    CPI = "Consumer Price Index"
    NFP = "Non-Farm Payrolls"
    GDP = "GDP"
    RATES = "Interest Rate"
    FOMC = "FOMC Meeting"
    CRYPTO = "Crypto Event"
    OTHER = "Other"


@dataclass
class EconomicEvent:
    """Экономическое событие"""
    id: str
    title: str
    event_type: EventType
    impact: EventImpact
    
    # Время
    datetime_utc: datetime
    country: str = "US"
    
    # Данные
    previous: str = ""
    forecast: str = ""
    actual: str = ""
    
    # Описание
    description: str = ""
    
    # Торговые рекомендации
    bullish_if: str = ""
    bearish_if: str = ""
    
    # Алерт отправлен
    alert_sent: bool = False
    result_alert_sent: bool = False


# Стандартные важные события
MAJOR_EVENTS = [
    {
        "title": "US CPI (YoY)",
        "type": EventType.CPI,
        "impact": EventImpact.CRITICAL,
        "description": "Индекс потребительских цен - главный показатель инфляции",
        "bullish_if": "Ниже прогноза = меньше ставки = рост крипты",
        "bearish_if": "Выше прогноза = больше ставки = падение крипты"
    },
    {
        "title": "FOMC Rate Decision",
        "type": EventType.FOMC,
        "impact": EventImpact.CRITICAL,
        "description": "Решение ФРС по процентной ставке",
        "bullish_if": "Снижение ставки или dovish риторика",
        "bearish_if": "Повышение ставки или hawkish риторика"
    },
    {
        "title": "US Non-Farm Payrolls",
        "type": EventType.NFP,
        "impact": EventImpact.HIGH,
        "description": "Изменение числа занятых вне с/х сектора",
        "bullish_if": "Слабее прогноза = soft landing",
        "bearish_if": "Сильнее прогноза = ставки дольше высокие"
    },
    {
        "title": "US GDP (QoQ)",
        "type": EventType.GDP,
        "impact": EventImpact.HIGH,
        "description": "Квартальный рост ВВП США",
        "bullish_if": "Умеренный рост = soft landing",
        "bearish_if": "Отрицательный = рецессия"
    },
    {
        "title": "Fed Chair Powell Speaks",
        "type": EventType.FED,
        "impact": EventImpact.HIGH,
        "description": "Выступление главы ФРС Пауэлла",
        "bullish_if": "Dovish комментарии",
        "bearish_if": "Hawkish комментарии"
    },
]


class EconomicCalendar:
    """
    📅 Economic Calendar
    
    Отслеживает важные экономические события и отправляет алерты:
    - За 24 часа до события
    - За 1 час до события
    - При публикации результата
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Календарь событий
        self.events: Dict[str, EconomicEvent] = {}
        
        # Настройки алертов
        self.alert_before_hours = [24, 1]  # За сколько часов алертить
        
        # Последнее обновление
        self.last_fetch = None
        self.fetch_interval = 3600  # Обновлять каждый час
        
        # Флаг работы
        self._running = False
        
    async def start(self):
        """Запуск"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)
        self._running = True
        
        # Загрузить события
        await self.fetch_events()
        
        # Запустить мониторинг
        asyncio.create_task(self._monitor_loop())
        
        logger.info("📅 Economic Calendar started")
        
    async def stop(self):
        """Остановка"""
        self._running = False
        if self._session:
            await self._session.close()
    
    async def fetch_events(self):
        """Получить события из API"""
        try:
            # Пробуем ForexFactory или TradingEconomics
            events = await self._fetch_from_api()
            
            if not events:
                # Используем статические данные
                events = self._generate_upcoming_events()
            
            for event in events:
                self.events[event.id] = event
            
            self.last_fetch = datetime.utcnow()
            logger.info(f"📅 Loaded {len(self.events)} economic events")
            
        except Exception as e:
            logger.error(f"Error fetching events: {e}")
    
    async def _fetch_from_api(self) -> List[EconomicEvent]:
        """Получить данные из API"""
        # TODO: Интеграция с реальным API
        # Forex Factory, TradingEconomics, Investing.com
        return []
    
    def _generate_upcoming_events(self) -> List[EconomicEvent]:
        """Генерировать примерные события на основе расписания"""
        events = []
        now = datetime.utcnow()
        
        # CPI обычно выходит 13-14 числа каждого месяца
        next_cpi = now.replace(
            day=13, 
            hour=12, 
            minute=30, 
            second=0, 
            microsecond=0
        )
        if next_cpi < now:
            if now.month == 12:
                next_cpi = next_cpi.replace(year=now.year + 1, month=1)
            else:
                next_cpi = next_cpi.replace(month=now.month + 1)
        
        events.append(EconomicEvent(
            id=f"cpi_{next_cpi.strftime('%Y%m')}",
            title="US CPI (YoY)",
            event_type=EventType.CPI,
            impact=EventImpact.CRITICAL,
            datetime_utc=next_cpi,
            country="US",
            description="Индекс потребительских цен США",
            bullish_if="Ниже прогноза",
            bearish_if="Выше прогноза"
        ))
        
        # FOMC - каждые 6 недель (примерно)
        next_fomc = now + timedelta(days=30)
        next_fomc = next_fomc.replace(hour=18, minute=0)
        
        events.append(EconomicEvent(
            id=f"fomc_{next_fomc.strftime('%Y%m%d')}",
            title="FOMC Rate Decision",
            event_type=EventType.FOMC,
            impact=EventImpact.CRITICAL,
            datetime_utc=next_fomc,
            country="US",
            description="Решение ФРС по ставке",
            bullish_if="Снижение или pause",
            bearish_if="Повышение"
        ))
        
        # NFP - первая пятница месяца
        next_nfp = now.replace(day=1)
        while next_nfp.weekday() != 4:  # Пятница
            next_nfp += timedelta(days=1)
        if next_nfp < now:
            next_nfp = (next_nfp.replace(day=1) + timedelta(days=32)).replace(day=1)
            while next_nfp.weekday() != 4:
                next_nfp += timedelta(days=1)
        next_nfp = next_nfp.replace(hour=12, minute=30)
        
        events.append(EconomicEvent(
            id=f"nfp_{next_nfp.strftime('%Y%m')}",
            title="US Non-Farm Payrolls",
            event_type=EventType.NFP,
            impact=EventImpact.HIGH,
            datetime_utc=next_nfp,
            country="US",
            description="Изменение занятости в США",
            bullish_if="Слабее прогноза",
            bearish_if="Сильнее прогноза"
        ))
        
        return events
    
    async def _monitor_loop(self):
        """Цикл мониторинга событий"""
        while self._running:
            try:
                now = datetime.utcnow()
                
                for event_id, event in list(self.events.items()):
                    time_to_event = (event.datetime_utc - now).total_seconds() / 3600
                    
                    # Проверить нужен ли алерт
                    if not event.alert_sent:
                        for hours in self.alert_before_hours:
                            if hours - 0.5 <= time_to_event <= hours + 0.5:
                                await self.send_event_alert(event, hours)
                                if hours == 1:
                                    event.alert_sent = True
                                break
                    
                    # Удалить старые события
                    if time_to_event < -24:
                        del self.events[event_id]
                
                # Обновить календарь периодически
                if self.last_fetch:
                    time_since_fetch = (now - self.last_fetch).total_seconds()
                    if time_since_fetch > self.fetch_interval:
                        await self.fetch_events()
                
            except Exception as e:
                logger.error(f"Calendar monitor error: {e}")
            
            await asyncio.sleep(300)  # Проверять каждые 5 минут
    
    async def send_event_alert(self, event: EconomicEvent, hours_before: float):
        """Отправить алерт о событии"""
        
        # Форматирование времени
        time_str = event.datetime_utc.strftime('%d %b %H:%M UTC')
        
        if hours_before >= 24:
            time_label = "⏰ Завтра"
        elif hours_before >= 1:
            time_label = f"⏰ Через {int(hours_before)} час"
        else:
            time_label = "⏰ Скоро!"
        
        msg = f"""
📅 <b>ECONOMIC EVENT ALERT</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{event.impact.value}

📊 <b>{event.title}</b>
🌍 {event.country}
{time_label} | {time_str}

📝 <b>Описание:</b>
{event.description}

📈 <b>Bullish если:</b> {event.bullish_if}
📉 <b>Bearish если:</b> {event.bearish_if}
"""
        
        if event.forecast:
            msg += f"\n📊 <b>Прогноз:</b> {event.forecast}"
        if event.previous:
            msg += f"\n📊 <b>Предыдущее:</b> {event.previous}"
        
        msg += """

⚠️ <b>РЕКОМЕНДАЦИЯ:</b>
├ Уменьшить позиции перед событием
├ Не открывать новые сделки
└ Дождаться реакции рынка
"""
        
        if self.telegram:
            await self.telegram.send_message(msg)
        else:
            logger.info(f"Economic event alert: {event.title}")
    
    def get_upcoming_events(self, hours: int = 48) -> List[EconomicEvent]:
        """Получить предстоящие события"""
        now = datetime.utcnow()
        cutoff = now + timedelta(hours=hours)
        
        upcoming = [
            e for e in self.events.values()
            if now <= e.datetime_utc <= cutoff
        ]
        
        return sorted(upcoming, key=lambda x: x.datetime_utc)
    
    def format_calendar_message(self, days: int = 7) -> str:
        """Форматировать календарь на неделю"""
        events = self.get_upcoming_events(hours=days * 24)
        
        if not events:
            return "📅 Нет важных событий в ближайшие дни"
        
        msg = f"""
📅 <b>ECONOMIC CALENDAR</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ближайшие {days} дней:

"""
        current_date = None
        
        for event in events:
            event_date = event.datetime_utc.date()
            
            if event_date != current_date:
                current_date = event_date
                msg += f"\n📆 <b>{event_date.strftime('%d %B %Y')}</b>\n"
            
            time_str = event.datetime_utc.strftime('%H:%M')
            msg += f"├ {time_str} | {event.impact.value[0:2]} | {event.title}\n"
        
        return msg
    
    async def send_weekly_calendar(self):
        """Отправить еженедельный календарь"""
        msg = self.format_calendar_message(days=7)
        
        if self.telegram:
            await self.telegram.send_message(msg)

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
    sent_thresholds: List[int] = field(default_factory=list)


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
    
    def __init__(self, telegram=None, orchestrator=None, groq=None, openrouter=None):
        self.telegram = telegram
        self.orchestrator = orchestrator
        self.groq = groq
        self.openrouter = openrouter
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
                if event.id not in self.events:
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
        
        # CPI: 13 Feb 2026, 12:30 UTC
        target_cpi = datetime(2026, 2, 13, 12, 30)
        if target_cpi > now - timedelta(hours=24):
            events.append(EconomicEvent(
                id="cpi_20260213",
                title="US CPI (YoY)",
                event_type=EventType.CPI,
                impact=EventImpact.CRITICAL,
                datetime_utc=target_cpi,
                country="US",
                previous="3.4%",
                forecast="2.9%",
                description="Индекс потребительских цен (Инфляция). Один из самых волатильных отчетов.",
                bullish_if="Ниже прогноза (<2.9%)",
                bearish_if="Выше прогноза (>2.9%)"
            ))

        # NFP: 6 March 2026 (approx first friday)
        next_nfp = datetime(2026, 3, 6, 13, 30)
        events.append(EconomicEvent(
            id="nfp_20260306",
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
                    
                    # 1. Проверить предупреждающие алерты (24ч, 1ч)
                    if not event.alert_sent:
                        for hours in self.alert_before_hours:
                            if hours - 0.5 <= time_to_event <= hours + 0.5:
                                if hours not in event.sent_thresholds:
                                    await self.send_event_alert(event, hours)
                                    event.sent_thresholds.append(hours)
                                    if hours == min(self.alert_before_hours):
                                        event.alert_sent = True
                                break
                    
                    # 2. Проверить публикацию результата (Actual)
                    if not event.result_alert_sent and -0.01 <= time_to_event <= 0.2:
                        # Время публикации пришло!
                        await self.handle_event_result(event)
                        event.result_alert_sent = True

                    # Удалить совсем старые события
                    if time_to_event < -24:
                        del self.events[event_id]
                
                # Обновить календарь периодически
                if self.last_fetch:
                    time_since_fetch = (now - self.last_fetch).total_seconds()
                    if time_since_fetch > self.fetch_interval:
                        await self.fetch_events()
                
            except Exception as e:
                logger.error(f"Calendar monitor error: {e}")
            
            await asyncio.sleep(60) # Чаще проверяем в моменты выхода новостей

    async def handle_event_result(self, event: EconomicEvent):
        """Обработать выход данных и отправить ИИ-анализ"""
        logger.info(f"🔔 Event time reached: {event.title}. Analyzing results...")
        
        # 1. Пауза новостей для приоритета ИИ
        if self.orchestrator:
            self.orchestrator.pause_news_parser(15) # Пауза на 15 секунд
            
        # 2. Попытка получить фактические данные (Actual)
        actual_val = event.actual or "Ожидается..." 
        
        # 3. Анализ ИИ (Groq с фоллбеком на OpenRouter)
        analysis = None
        
        # Сначала пробуем Groq
        if self.groq:
            try:
                analysis = await self.groq.analyze_economic_result(
                    event_title=event.title,
                    actual=actual_val,
                    forecast=event.forecast,
                    previous=event.previous,
                    description=event.description
                )
            except Exception as e:
                logger.warning(f"Groq analysis failed: {e}")

        # Если Groq не сработал - пробуем OpenRouter
        if not analysis and self.openrouter:
            logger.info(f"🔄 Falling back to OpenRouter for event: {event.title}")
            try:
                # Используем метод анализа из OpenRouterAnalyzer с флагом важности
                is_high = event.impact in [EventImpact.HIGH, EventImpact.CRITICAL]
                analysis = await self.openrouter.analyze_event_result(event.__dict__, actual_val, high_impact=is_high)
            except Exception as e:
                logger.error(f"OpenRouter analysis failed: {e}")
            
        if not analysis:
            logger.warning(f"Could not get AI analysis for {event.title}")
            return

        # 4. Формирование и отправка алерта
        verdict = analysis.get('verdict', 'NEUTRAL') if analysis else 'NEUTRAL'
        verdict_emoji = "🚀 LONG" if verdict == 'LONG' else "📉 SHORT" if verdict == 'SHORT' else "⚪ NEUTRAL"
        
        msg = f"""
📅 <b>ECONOMIC RESULT ALERT</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{event.impact.value} | <b>{event.title}</b>

📊 <b>Фактическое:</b> {actual_val}
🎯 <b>Прогноз:</b> {event.forecast}
📉 <b>Предыдущее:</b> {event.previous}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 <b>ИИ ВЕРДИКТ (Groq):</b>
👉 <b>{verdict_emoji}</b>

🔥 <b>ВАЖНОСТЬ:</b> {analysis.get('importance', 'N/A')}/10
⚡ <b>ПРОГНОЗ ВОЛАТИЛЬНОСТИ BTC:</b> {analysis.get('btc_move_projection', '±0.5%')}

🔢 <b>АНАЛИЗ ДЕЛЬТЫ:</b>
{analysis.get('delta_analysis', 'Расчет отклонения в процессе...')}

📝 <b>СУТЬ:</b>
{analysis.get('summary', 'Данные вышли. Рынок анализирует волатильность.') if analysis else 'Анализ временно недоступен.'}

💡 <b>ДЕТАЛИ:</b>
"""
        if analysis and analysis.get('key_points'):
            for pt in analysis['key_points']:
                msg += f"• {pt}\n"
        else:
            msg += "• Дождитесь реакции цены\n• Повышенная волатильность\n"

        msg += f"""
🎯 <b>Ожидаемая реакция:</b>
{analysis.get('market_reaction_expected', 'Неопределено') if analysis else 'Следите за графиком'}
"""

        if self.telegram:
            await self.telegram.send_message(msg)
        else:
            logger.info(f"Economic result: {event.title} -> {verdict}")    
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

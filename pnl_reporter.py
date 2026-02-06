"""
MEXC Pump Monitor - PnL Reporter
Ежедневные и недельные отчёты по P&L
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """Запись о сделке"""
    trade_id: str
    symbol: str
    side: str              # "LONG" или "SHORT"
    
    entry_price: float
    exit_price: float
    quantity: float
    
    entry_time: datetime
    exit_time: datetime
    
    pnl_pct: float
    pnl_usd: float
    
    signal_source: str = ""  # Откуда пришёл сигнал


@dataclass
class DailyReport:
    """Дневной отчёт"""
    date: datetime
    
    # Сделки
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # P&L
    total_pnl_usd: float = 0
    total_pnl_pct: float = 0
    
    # Лучшие/худшие
    best_trade: Optional[TradeRecord] = None
    worst_trade: Optional[TradeRecord] = None
    
    # По символам
    trades_by_symbol: Dict[str, int] = field(default_factory=dict)
    pnl_by_symbol: Dict[str, float] = field(default_factory=dict)
    
    # Метрики
    win_rate: float = 0
    avg_win: float = 0
    avg_loss: float = 0
    profit_factor: float = 0


@dataclass
class WeeklyReport:
    """Недельный отчёт"""
    week_start: datetime
    week_end: datetime
    
    # Суммарно
    total_trades: int = 0
    total_pnl_usd: float = 0
    total_pnl_pct: float = 0
    
    # Дневные данные
    daily_reports: List[DailyReport] = field(default_factory=list)
    
    # По дням недели
    pnl_by_weekday: Dict[str, float] = field(default_factory=dict)
    
    # Лучший/худший день
    best_day: Optional[DailyReport] = None
    worst_day: Optional[DailyReport] = None
    
    # Метрики
    win_rate: float = 0
    avg_daily_pnl: float = 0
    max_drawdown: float = 0


class PnLReporter:
    """
    Генератор P&L отчётов
    
    Отправляет:
    - Ежедневные отчёты в 00:00
    - Недельные отчёты в воскресенье
    """
    
    def __init__(self, telegram_notifier=None):
        self.telegram = telegram_notifier
        
        # Хранилище сделок
        self.trades: List[TradeRecord] = []
        self.daily_reports: List[DailyReport] = []
        self.weekly_reports: List[WeeklyReport] = []
        
        # Текущий баланс
        self.starting_balance: float = 100
        self.current_balance: float = 100
        
        # Статистика
        self.stats = {
            'reports_generated': 0,
            'total_pnl_usd': 0,
            'all_time_trades': 0
        }
    
    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        entry_time: datetime = None,
        exit_time: datetime = None,
        signal_source: str = ""
    ):
        """Записать завершённую сделку"""
        entry_time = entry_time or datetime.now()
        exit_time = exit_time or datetime.now()
        
        # Рассчитать P&L
        if side == "SHORT":
            pnl_pct = (entry_price - exit_price) / entry_price * 100
        else:
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        
        pnl_usd = quantity * entry_price * (pnl_pct / 100)
        
        trade = TradeRecord(
            trade_id=f"T_{len(self.trades)}_{int(time.time())}",
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            entry_time=entry_time,
            exit_time=exit_time,
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            signal_source=signal_source
        )
        
        self.trades.append(trade)
        self.current_balance += pnl_usd
        self.stats['total_pnl_usd'] += pnl_usd
        self.stats['all_time_trades'] += 1
        
        return trade
    
    def generate_daily_report(self, date: datetime = None) -> DailyReport:
        """Сгенерировать дневной отчёт"""
        date = date or datetime.now()
        day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        
        # Фильтр сделок за день
        day_trades = [
            t for t in self.trades
            if day_start <= t.exit_time < day_end
        ]
        
        report = DailyReport(date=day_start)
        
        if not day_trades:
            return report
        
        report.total_trades = len(day_trades)
        
        wins = [t for t in day_trades if t.pnl_pct > 0]
        losses = [t for t in day_trades if t.pnl_pct < 0]
        
        report.winning_trades = len(wins)
        report.losing_trades = len(losses)
        
        report.total_pnl_usd = sum(t.pnl_usd for t in day_trades)
        report.total_pnl_pct = sum(t.pnl_pct for t in day_trades)
        
        # Лучшая/худшая
        if day_trades:
            report.best_trade = max(day_trades, key=lambda t: t.pnl_pct)
            report.worst_trade = min(day_trades, key=lambda t: t.pnl_pct)
        
        # По символам
        for trade in day_trades:
            report.trades_by_symbol[trade.symbol] = report.trades_by_symbol.get(trade.symbol, 0) + 1
            report.pnl_by_symbol[trade.symbol] = report.pnl_by_symbol.get(trade.symbol, 0) + trade.pnl_usd
        
        # Метрики
        if report.winning_trades + report.losing_trades > 0:
            report.win_rate = report.winning_trades / (report.winning_trades + report.losing_trades) * 100
        
        if wins:
            report.avg_win = sum(t.pnl_pct for t in wins) / len(wins)
        if losses:
            report.avg_loss = sum(t.pnl_pct for t in losses) / len(losses)
        
        gross_profit = sum(t.pnl_usd for t in wins) if wins else 0
        gross_loss = abs(sum(t.pnl_usd for t in losses)) if losses else 0
        if gross_loss > 0:
            report.profit_factor = gross_profit / gross_loss
        
        self.daily_reports.append(report)
        self.stats['reports_generated'] += 1
        
        return report
    
    def generate_weekly_report(self) -> WeeklyReport:
        """Сгенерировать недельный отчёт"""
        today = datetime.now()
        
        # Найти начало недели (понедельник)
        week_start = today - timedelta(days=today.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)
        
        report = WeeklyReport(week_start=week_start, week_end=week_end)
        
        # Генерировать отчёты за каждый день
        weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        
        for i in range(7):
            day = week_start + timedelta(days=i)
            if day <= today:
                daily = self.generate_daily_report(day)
                report.daily_reports.append(daily)
                report.pnl_by_weekday[weekdays[i]] = daily.total_pnl_usd
                
                report.total_trades += daily.total_trades
                report.total_pnl_usd += daily.total_pnl_usd
                report.total_pnl_pct += daily.total_pnl_pct
        
        # Лучший/худший день
        if report.daily_reports:
            report.best_day = max(report.daily_reports, key=lambda d: d.total_pnl_usd)
            report.worst_day = min(report.daily_reports, key=lambda d: d.total_pnl_usd)
        
        # Метрики
        wins = sum(1 for d in report.daily_reports if d.total_pnl_usd > 0)
        total_days = len([d for d in report.daily_reports if d.total_trades > 0])
        if total_days > 0:
            report.win_rate = wins / total_days * 100
            report.avg_daily_pnl = report.total_pnl_usd / total_days
        
        self.weekly_reports.append(report)
        
        return report
    
    def format_daily_report(self, report: DailyReport = None) -> str:
        """Форматировать дневной отчёт для Telegram"""
        if report is None:
            report = self.generate_daily_report()
        
        pnl_emoji = "🟢" if report.total_pnl_usd >= 0 else "🔴"
        wr_emoji = "🟢" if report.win_rate >= 50 else "🟡" if report.win_rate >= 40 else "🔴"
        
        msg = f"""
📊 <b>ДНЕВНОЙ ОТЧЁТ</b>
📅 {report.date.strftime('%d.%m.%Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 <b>СДЕЛКИ:</b>
├ Всего: {report.total_trades}
├ ✅ Профит: {report.winning_trades}
└ ❌ Лосс: {report.losing_trades}

{wr_emoji} <b>ВИНРЕЙТ:</b> {report.win_rate:.1f}%

{pnl_emoji} <b>P&L:</b>
├ USD: <b>${report.total_pnl_usd:+,.2f}</b>
└ %: <b>{report.total_pnl_pct:+.2f}%</b>

💰 <b>СРЕДНИЕ:</b>
├ Ср. вин: {report.avg_win:+.2f}%
├ Ср. лосс: {report.avg_loss:+.2f}%
└ Profit Factor: {report.profit_factor:.2f}
"""
        
        if report.best_trade:
            msg += f"""
🏆 <b>ЛУЧШАЯ:</b> {report.best_trade.symbol} {report.best_trade.pnl_pct:+.2f}%
💀 <b>ХУДШАЯ:</b> {report.worst_trade.symbol} {report.worst_trade.pnl_pct:+.2f}%
"""
        
        # Топ символы
        if report.pnl_by_symbol:
            sorted_symbols = sorted(report.pnl_by_symbol.items(), key=lambda x: -x[1])[:3]
            msg += "\n📊 <b>ТОП МОНЕТЫ:</b>\n"
            for symbol, pnl in sorted_symbols:
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"├ {emoji} {symbol}: ${pnl:+.2f}\n"
        
        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 <b>БАЛАНС:</b> ${self.current_balance:,.2f}
📈 <b>ALL-TIME:</b> ${self.stats['total_pnl_usd']:+,.2f}
"""
        
        return msg.strip()
    
    def format_weekly_report(self, report: WeeklyReport = None) -> str:
        """Форматировать недельный отчёт"""
        if report is None:
            report = self.generate_weekly_report()
        
        pnl_emoji = "🟢" if report.total_pnl_usd >= 0 else "🔴"
        
        msg = f"""
📊 <b>НЕДЕЛЬНЫЙ ОТЧЁТ</b>
📅 {report.week_start.strftime('%d.%m')} - {report.week_end.strftime('%d.%m.%Y')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 <b>ИТОГО ЗА НЕДЕЛЮ:</b>
├ Сделок: {report.total_trades}
├ {pnl_emoji} P&L: <b>${report.total_pnl_usd:+,.2f}</b>
└ Ср. в день: ${report.avg_daily_pnl:+,.2f}

📅 <b>ПО ДНЯМ:</b>
"""
        
        weekdays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        for day in weekdays:
            pnl = report.pnl_by_weekday.get(day, 0)
            emoji = "🟢" if pnl >= 0 else "🔴" if pnl < 0 else "⚪"
            bar_len = min(10, abs(int(pnl / 50)))
            bar = "▓" * bar_len if pnl >= 0 else "░" * bar_len
            msg += f"├ {day}: {emoji} ${pnl:+.0f} {bar}\n"
        
        if report.best_day and report.best_day.total_trades > 0:
            msg += f"""
🏆 <b>ЛУЧШИЙ ДЕНЬ:</b> {report.best_day.date.strftime('%d.%m')} (${report.best_day.total_pnl_usd:+.2f})
💀 <b>ХУДШИЙ ДЕНЬ:</b> {report.worst_day.date.strftime('%d.%m')} (${report.worst_day.total_pnl_usd:+.2f})
"""
        
        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 <b>ТЕКУЩИЙ БАЛАНС:</b> ${self.current_balance:,.2f}
📈 <b>ИЗМЕНЕНИЕ:</b> {((self.current_balance - self.starting_balance) / self.starting_balance * 100):+.1f}%
"""
        
        return msg.strip()
    
    async def send_daily_report(self):
        """Отправить дневной отчёт в Telegram"""
        report = self.generate_daily_report()
        message = self.format_daily_report(report)
        
        if self.telegram:
            await self.telegram.send_message(message)
        
        return message
    
    async def send_weekly_report(self):
        """Отправить недельный отчёт в Telegram"""
        report = self.generate_weekly_report()
        message = self.format_weekly_report(report)
        
        if self.telegram:
            await self.telegram.send_message(message)
        
        return message
    
    async def schedule_reports(self):
        """Запланировать отправку отчётов"""
        while True:
            now = datetime.now()
            
            # Проверить время для дневного отчёта (00:00)
            if now.hour == 0 and now.minute == 0:
                await self.send_daily_report()
                
                # Воскресенье = недельный отчёт
                if now.weekday() == 6:
                    await self.send_weekly_report()
            
            await asyncio.sleep(60)  # Проверять каждую минуту

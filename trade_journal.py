"""
MEXC Pump Monitor - Trade Journal
Автоматический журнал всех сделок с аналитикой
"""

import asyncio
import json
import logging
import time
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class TradeEntry:
    """Запись о сделке"""
    trade_id: str
    symbol: str
    
    # Entry
    entry_time: int
    entry_price: float
    position_size: float
    leverage: int
    direction: str  # 'long' or 'short'
    
    # Signal info
    signal_type: str  # 'pump', 'short', 'whale', etc.
    signal_score: int
    signal_quality: str
    
    # Levels
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    
    # Exit
    exit_time: int = 0
    exit_price: float = 0
    exit_reason: str = ""  # 'tp1', 'tp2', 'sl', 'manual', 'timeout'
    
    # Result
    profit_usd: float = 0
    profit_pct: float = 0
    is_win: bool = False
    
    # Duration
    duration_minutes: int = 0
    
    # Notes
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Market context
    market_regime: str = ""  # 'trending', 'ranging', 'volatile'
    btc_price_at_entry: float = 0


@dataclass
class JournalStats:
    """Статистика журнала"""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0
    
    total_profit_usd: float = 0
    total_profit_pct: float = 0
    
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    
    largest_win_pct: float = 0
    largest_loss_pct: float = 0
    
    profit_factor: float = 0
    expectancy: float = 0
    
    avg_duration_minutes: float = 0
    
    best_signal_type: str = ""
    worst_signal_type: str = ""
    
    current_streak: int = 0
    max_win_streak: int = 0
    max_loss_streak: int = 0


class TradeJournal:
    """
    📔 Trade Journal
    
    Функции:
    - Автоматическое логирование сделок
    - Расчёт статистики (Win Rate, P/F, Expectancy)
    - Анализ по типам сигналов
    - Экспорт в JSON/CSV
    - Ежедневные/еженедельные отчёты
    """
    
    def __init__(self, data_dir: str = None, telegram=None):
        self.data_dir = Path(data_dir or "./journal_data")
        self.data_dir.mkdir(exist_ok=True)
        
        self.telegram = telegram
        
        # Trades storage
        self.trades: List[TradeEntry] = []
        self.open_trades: Dict[str, TradeEntry] = {}
        
        # Stats cache
        self._stats_cache: Optional[JournalStats] = None
        self._stats_time = 0
        
        # Load existing data
        self._load_data()
    
    def _load_data(self):
        """Загрузить данные"""
        trades_file = self.data_dir / "trades.json"
        
        try:
            if trades_file.exists():
                with open(trades_file, 'r') as f:
                    data = json.load(f)
                    self.trades = [TradeEntry(**t) for t in data]
                logger.info(f"Loaded {len(self.trades)} trades from journal")
        except Exception as e:
            logger.error(f"Failed to load journal: {e}")
    
    def _save_data(self):
        """Сохранить данные"""
        try:
            trades_file = self.data_dir / "trades.json"
            with open(trades_file, 'w') as f:
                json.dump([asdict(t) for t in self.trades], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save journal: {e}")
    
    def open_trade(
        self,
        symbol: str,
        entry_price: float,
        position_size: float,
        leverage: int,
        direction: str,
        signal_type: str,
        signal_score: int,
        signal_quality: str,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float = 0,
        market_regime: str = "",
        btc_price: float = 0,
        notes: str = "",
        tags: List[str] = None
    ) -> str:
        """
        Открыть сделку
        
        Returns:
            trade_id
        """
        trade_id = f"{symbol}_{int(time.time()*1000)}"
        
        trade = TradeEntry(
            trade_id=trade_id,
            symbol=symbol,
            entry_time=int(time.time() * 1000),
            entry_price=entry_price,
            position_size=position_size,
            leverage=leverage,
            direction=direction,
            signal_type=signal_type,
            signal_score=signal_score,
            signal_quality=signal_quality,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2 or take_profit_1 * (0.9 if direction == 'short' else 1.1),
            market_regime=market_regime,
            btc_price_at_entry=btc_price,
            notes=notes,
            tags=tags or []
        )
        
        self.open_trades[trade_id] = trade
        
        logger.info(f"Journal: Opened trade {trade_id}")
        
        return trade_id
    
    def close_trade(
        self,
        trade_id: str,
        exit_price: float,
        exit_reason: str,
        notes: str = ""
    ) -> Optional[TradeEntry]:
        """
        Закрыть сделку
        """
        trade = self.open_trades.pop(trade_id, None)
        if not trade:
            logger.warning(f"Trade not found: {trade_id}")
            return None
        
        # Calculate results
        trade.exit_time = int(time.time() * 1000)
        trade.exit_price = exit_price
        trade.exit_reason = exit_reason
        
        # Duration
        trade.duration_minutes = (trade.exit_time - trade.entry_time) // 60000
        
        # Profit calculation
        if trade.direction == 'short':
            price_diff = trade.entry_price - exit_price
        else:
            price_diff = exit_price - trade.entry_price
        
        trade.profit_pct = (price_diff / trade.entry_price) * 100 * trade.leverage
        trade.profit_usd = trade.position_size * (trade.profit_pct / 100)
        trade.is_win = trade.profit_pct > 0
        
        if notes:
            trade.notes = f"{trade.notes} | {notes}" if trade.notes else notes
        
        # Store trade
        self.trades.append(trade)
        self._save_data()
        
        # Invalidate cache
        self._stats_cache = None
        
        logger.info(
            f"Journal: Closed {trade_id} - "
            f"{'WIN' if trade.is_win else 'LOSS'} {trade.profit_pct:+.2f}%"
        )
        
        return trade
    
    def get_stats(self, recalculate: bool = False) -> JournalStats:
        """Получить статистику"""
        if self._stats_cache and not recalculate:
            return self._stats_cache
        
        stats = JournalStats()
        
        if not self.trades:
            return stats
        
        closed = [t for t in self.trades if t.exit_time > 0]
        
        if not closed:
            return stats
        
        wins = [t for t in closed if t.is_win]
        losses = [t for t in closed if not t.is_win]
        
        stats.total_trades = len(closed)
        stats.wins = len(wins)
        stats.losses = len(losses)
        stats.win_rate = stats.wins / stats.total_trades if stats.total_trades > 0 else 0
        
        stats.total_profit_usd = sum(t.profit_usd for t in closed)
        stats.total_profit_pct = sum(t.profit_pct for t in closed)
        
        if wins:
            stats.avg_win_pct = sum(t.profit_pct for t in wins) / len(wins)
            stats.largest_win_pct = max(t.profit_pct for t in wins)
        
        if losses:
            stats.avg_loss_pct = sum(abs(t.profit_pct) for t in losses) / len(losses)
            stats.largest_loss_pct = min(t.profit_pct for t in losses)
        
        # Profit factor
        gross_profit = sum(t.profit_pct for t in wins) if wins else 0
        gross_loss = sum(abs(t.profit_pct) for t in losses) if losses else 1
        stats.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Expectancy
        stats.expectancy = (
            (stats.win_rate * stats.avg_win_pct) -
            ((1 - stats.win_rate) * stats.avg_loss_pct)
        ) if stats.total_trades > 0 else 0
        
        # Average duration
        stats.avg_duration_minutes = sum(t.duration_minutes for t in closed) / len(closed)
        
        # Streaks
        current_streak = 0
        max_win = 0
        max_loss = 0
        streak = 0
        last_win = None
        
        for t in sorted(closed, key=lambda x: x.entry_time):
            if last_win is None:
                streak = 1
                last_win = t.is_win
            elif t.is_win == last_win:
                streak += 1
            else:
                if last_win:
                    max_win = max(max_win, streak)
                else:
                    max_loss = max(max_loss, streak)
                streak = 1
                last_win = t.is_win
        
        if last_win:
            max_win = max(max_win, streak)
            current_streak = streak
        else:
            max_loss = max(max_loss, streak)
            current_streak = -streak
        
        stats.current_streak = current_streak
        stats.max_win_streak = max_win
        stats.max_loss_streak = max_loss
        
        # Best/worst signal type
        by_type = defaultdict(list)
        for t in closed:
            by_type[t.signal_type].append(t.profit_pct)
        
        type_performance = {
            t: sum(profits) / len(profits)
            for t, profits in by_type.items()
            if len(profits) >= 3
        }
        
        if type_performance:
            stats.best_signal_type = max(type_performance, key=type_performance.get)
            stats.worst_signal_type = min(type_performance, key=type_performance.get)
        
        self._stats_cache = stats
        self._stats_time = int(time.time())
        
        return stats
    
    def get_today_trades(self) -> List[TradeEntry]:
        """Получить сделки за сегодня"""
        today_start = int(datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp() * 1000)
        
        return [t for t in self.trades if t.entry_time >= today_start]
    
    def get_week_trades(self) -> List[TradeEntry]:
        """Получить сделки за неделю"""
        week_ago = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
        return [t for t in self.trades if t.entry_time >= week_ago]
    
    async def send_daily_report(self):
        """Отправить дневной отчёт"""
        today = self.get_today_trades()
        
        if not today:
            return
        
        closed = [t for t in today if t.exit_time > 0]
        wins = len([t for t in closed if t.is_win])
        losses = len(closed) - wins
        total_pnl = sum(t.profit_pct for t in closed)
        
        report = f"""
📔 <b>DAILY JOURNAL REPORT</b>
{datetime.now().strftime('%Y-%m-%d')}

📊 Trades: {len(closed)}
✅ Wins: {wins}
❌ Losses: {losses}
📈 Win Rate: {wins/len(closed)*100 if closed else 0:.1f}%

💰 Total P/L: {total_pnl:+.2f}%

🔥 Best: {max(t.profit_pct for t in closed) if closed else 0:+.2f}%
💀 Worst: {min(t.profit_pct for t in closed) if closed else 0:+.2f}%
"""
        
        if self.telegram:
            await self.telegram.send_message(report)
    
    def format_stats(self) -> str:
        """Форматировать статистику"""
        stats = self.get_stats()
        
        return f"""
📔 <b>TRADE JOURNAL STATS</b>

📊 <b>Overview:</b>
├ Total Trades: {stats.total_trades}
├ Wins: {stats.wins} | Losses: {stats.losses}
├ Win Rate: {stats.win_rate:.1%}
└ Profit Factor: {stats.profit_factor:.2f}

💰 <b>Profits:</b>
├ Total P/L: {stats.total_profit_pct:+.2f}%
├ Avg Win: +{stats.avg_win_pct:.2f}%
├ Avg Loss: -{stats.avg_loss_pct:.2f}%
└ Expectancy: {stats.expectancy:.2f}%

🔥 <b>Records:</b>
├ Largest Win: +{stats.largest_win_pct:.2f}%
├ Largest Loss: {stats.largest_loss_pct:.2f}%
├ Win Streak: {stats.max_win_streak}
└ Loss Streak: {stats.max_loss_streak}

⏱️ Avg Duration: {stats.avg_duration_minutes:.0f} min
🎯 Best Signal: {stats.best_signal_type or 'N/A'}
"""
    
    def export_csv(self, filename: str = None) -> str:
        """Экспорт в CSV"""
        import csv
        
        filename = filename or f"trades_{datetime.now().strftime('%Y%m%d')}.csv"
        filepath = self.data_dir / filename
        
        with open(filepath, 'w', newline='') as f:
            if self.trades:
                writer = csv.DictWriter(f, fieldnames=asdict(self.trades[0]).keys())
                writer.writeheader()
                for trade in self.trades:
                    writer.writerow(asdict(trade))
        
        return str(filepath)

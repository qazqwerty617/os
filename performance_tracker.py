"""
MEXC Pump Monitor - Performance Tracker
Tracks signal accuracy and trading performance over time
Optimized DB interaction and stats calculation
"""

import time
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class SignalOutcome(Enum):
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    EXPIRED = "EXPIRED"


@dataclass
class TrackedSignal:
    signal_id: str
    symbol: str
    quality: str
    score: int
    entry_price: float
    entry_time: int
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    outcome: SignalOutcome = SignalOutcome.PENDING
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    pnl_pct: float = 0
    hit_tp1: bool = False
    hit_tp2: bool = False
    max_profit_pct: float = 0
    max_drawdown_pct: float = 0
    duration_minutes: int = 0


@dataclass
class PerformanceStats:
    period: str
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    pending: int = 0
    win_rate: float = 0
    total_pnl_pct: float = 0
    avg_pnl_pct: float = 0
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    profit_factor: float = 0
    quality_win_rates: Dict[str, float] = field(default_factory=dict)
    quality_counts: Dict[str, int] = field(default_factory=dict)
    best_trade_pct: float = 0
    worst_trade_pct: float = 0
    best_symbol: str = ""
    worst_symbol: str = ""


class PerformanceTracker:
    """Optimized Performance Tracker"""
    
    def __init__(self, db_path: str = "performance.db"):
        self.db_path = db_path
        self.active_signals: Dict[str, TrackedSignal] = {}
        self._init_db()
    
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY, symbol TEXT, quality TEXT, score INTEGER,
                    entry_price REAL, entry_time INTEGER, stop_loss REAL,
                    take_profit_1 REAL, take_profit_2 REAL, outcome TEXT,
                    exit_price REAL, exit_time INTEGER, pnl_pct REAL,
                    hit_tp1 INTEGER, hit_tp2 INTEGER, max_profit_pct REAL,
                    max_drawdown_pct REAL, duration_minutes INTEGER
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_stats (
                    date TEXT PRIMARY KEY, total_signals INTEGER,
                    wins INTEGER, losses INTEGER, total_pnl_pct REAL
                )
            ''')
    
    def start_tracking(self, signal_id: str, symbol: str, quality: str, score: int,
                       entry_price: float, stop_loss: float, tp1: float, tp2: float) -> TrackedSignal:
        signal = TrackedSignal(
            signal_id, symbol, quality, score, entry_price, int(time.time()*1000),
            stop_loss, tp1, tp2
        )
        self.active_signals[signal_id] = signal
        self._save_signal(signal)
        logger.info(f"📊 Tracking: {symbol} {quality}-tier")
        return signal
    
    def update_price(self, signal_id: str, price: float):
        if signal_id not in self.active_signals: return
        s = self.active_signals[signal_id]
        
        pnl = ((s.entry_price - price) / s.entry_price) * 100
        s.max_profit_pct = max(s.max_profit_pct, pnl)
        s.max_drawdown_pct = min(s.max_drawdown_pct, pnl)
        
        if price <= s.take_profit_1 and not s.hit_tp1:
            s.hit_tp1 = True
        if price <= s.take_profit_2 and not s.hit_tp2:
            s.hit_tp2 = True
        
        if price >= s.stop_loss:
            self.close_signal(signal_id, price, SignalOutcome.LOSS)
        elif s.hit_tp2:
            self.close_signal(signal_id, price, SignalOutcome.WIN)
    
    def close_signal(self, signal_id: str, price: float, outcome: SignalOutcome):
        if signal_id not in self.active_signals: return
        s = self.active_signals[signal_id]
        
        s.exit_price = price
        s.exit_time = int(time.time()*1000)
        s.outcome = outcome
        s.pnl_pct = ((s.entry_price - price) / s.entry_price) * 100
        s.duration_minutes = (s.exit_time - s.entry_time) // 60000
        
        self._save_signal(s)
        del self.active_signals[signal_id]
        
        emoji = "✅" if outcome == SignalOutcome.WIN else "❌"
        logger.info(f"{emoji} Closed: {s.symbol} {outcome.value} {s.pnl_pct:+.2f}%")
    
    def _save_signal(self, s: TrackedSignal):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT OR REPLACE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (s.signal_id, s.symbol, s.quality, s.score, s.entry_price, s.entry_time,
                 s.stop_loss, s.take_profit_1, s.take_profit_2, s.outcome.value,
                 s.exit_price, s.exit_time, s.pnl_pct, int(s.hit_tp1), int(s.hit_tp2),
                 s.max_profit_pct, s.max_drawdown_pct, s.duration_minutes)
            )
    
    def get_stats(self, period: str = "7d") -> PerformanceStats:
        cutoff = 0
        if period != "all":
            days = int(period[:-1]) if period[:-1].isdigit() else 7
            cutoff = int(time.time()*1000) - (days * 86400000)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM signals WHERE entry_time > ?", (cutoff,))
            rows = cursor.fetchall()
        
        if not rows: return PerformanceStats(period)
        
        signals = [{'q': r[2], 'out': r[9], 'pnl': r[12] or 0, 'sym': r[1]} for r in rows]
        wins = [s for s in signals if s['out'] == 'WIN']
        losses = [s for s in signals if s['out'] == 'LOSS']
        
        total = len(wins) + len(losses)
        wr = len(wins) / total * 100 if total else 0
        all_pnls = [s['pnl'] for s in signals if s['out'] in ('WIN', 'LOSS')]
        
        gross_profit = sum(p for p in all_pnls if p > 0)
        gross_loss = abs(sum(p for p in all_pnls if p < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else gross_profit
        
        q_stats = {'rates': {}, 'counts': {}}
        for q in ['S', 'A', 'B', 'C']:
            qs = [s for s in signals if s['q'] == q]
            qw = [s for s in qs if s['out'] == 'WIN']
            qt = len([s for s in qs if s['out'] in ('WIN', 'LOSS')])
            q_stats['counts'][q] = len(qs)
            q_stats['rates'][q] = len(qw) / qt * 100 if qt else 0
        
        best = max(signals, key=lambda s: s['pnl']) if signals else {'pnl': 0, 'sym': ''}
        worst = min(signals, key=lambda s: s['pnl']) if signals else {'pnl': 0, 'sym': ''}
        
        return PerformanceStats(
            period, len(signals), len(wins), len(losses), 0,
            len([s for s in signals if s['out'] == 'PENDING']),
            wr, sum(all_pnls), statistics.mean(all_pnls) if all_pnls else 0,
            statistics.mean([s['pnl'] for s in wins]) if wins else 0,
            statistics.mean([s['pnl'] for s in losses]) if losses else 0,
            pf, q_stats['rates'], q_stats['counts'],
            best['pnl'], worst['pnl'], best['sym'], worst['sym']
        )
    
    def generate_report(self) -> str:
        s7 = self.get_stats("7d")
        return f"""
📊 PERFORMANCE REPORT
────────────────────
📈 7-DAY STATS
├ Signals: {s7.total_signals}
├ Win Rate: {s7.win_rate:.1f}%
├ Total PnL: {s7.total_pnl_pct:+.2f}%
└ Profit Factor: {s7.profit_factor:.2f}

🎯 QUALITY
├ S-Tier: {s7.quality_win_rates.get('S',0):.0f}% ({s7.quality_counts.get('S',0)})
├ A-Tier: {s7.quality_win_rates.get('A',0):.0f}% ({s7.quality_counts.get('A',0)})
└ B-Tier: {s7.quality_win_rates.get('B',0):.0f}% ({s7.quality_counts.get('B',0)})
"""

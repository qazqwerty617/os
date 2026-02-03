"""
MEXC Pump Monitor - Performance Tracker
Tracks signal accuracy and trading performance over time
"""

import time
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


class SignalOutcome(Enum):
    """Signal outcome types"""
    PENDING = "PENDING"
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    EXPIRED = "EXPIRED"


@dataclass
class TrackedSignal:
    """Signal being tracked for performance"""
    signal_id: str
    symbol: str
    quality: str  # S, A, B, C
    score: int
    
    # Entry
    entry_price: float
    entry_time: int
    
    # Targets
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    
    # Outcome
    outcome: SignalOutcome = SignalOutcome.PENDING
    exit_price: Optional[float] = None
    exit_time: Optional[int] = None
    
    # Performance
    pnl_pct: float = 0
    hit_tp1: bool = False
    hit_tp2: bool = False
    max_profit_pct: float = 0  # Max favorable excursion
    max_drawdown_pct: float = 0  # Max adverse excursion
    
    # Duration
    duration_minutes: int = 0


@dataclass
class PerformanceStats:
    """Performance statistics"""
    period: str  # "1d", "7d", "30d", "all"
    
    # Counts
    total_signals: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    pending: int = 0
    
    # Rates
    win_rate: float = 0
    
    # PnL
    total_pnl_pct: float = 0
    avg_pnl_pct: float = 0
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    profit_factor: float = 0  # Gross profit / Gross loss
    
    # By quality
    quality_win_rates: Dict[str, float] = field(default_factory=dict)
    quality_counts: Dict[str, int] = field(default_factory=dict)
    
    # Streaks
    current_streak: int = 0  # Positive = wins, negative = losses
    max_win_streak: int = 0
    max_loss_streak: int = 0
    
    # Best/Worst
    best_trade_pct: float = 0
    worst_trade_pct: float = 0
    best_symbol: str = ""
    worst_symbol: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'period': self.period,
            'total_signals': self.total_signals,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': self.win_rate,
            'total_pnl_pct': self.total_pnl_pct,
            'avg_pnl_pct': self.avg_pnl_pct,
            'profit_factor': self.profit_factor,
            'quality_win_rates': self.quality_win_rates,
            'current_streak': self.current_streak,
            'best_trade_pct': self.best_trade_pct,
            'worst_trade_pct': self.worst_trade_pct
        }


class PerformanceTracker:
    """
    Tracks signal accuracy and performance over time
    Stores data in SQLite for historical analysis
    """
    
    def __init__(self, db_path: str = "performance.db"):
        self.db_path = db_path
        
        # Active signals being tracked
        self.active_signals: Dict[str, TrackedSignal] = {}
        
        # Initialize database
        self._init_db()
    
    def _init_db(self):
        """Initialize performance database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                signal_id TEXT PRIMARY KEY,
                symbol TEXT,
                quality TEXT,
                score INTEGER,
                entry_price REAL,
                entry_time INTEGER,
                stop_loss REAL,
                take_profit_1 REAL,
                take_profit_2 REAL,
                outcome TEXT,
                exit_price REAL,
                exit_time INTEGER,
                pnl_pct REAL,
                hit_tp1 INTEGER,
                hit_tp2 INTEGER,
                max_profit_pct REAL,
                max_drawdown_pct REAL,
                duration_minutes INTEGER
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                total_signals INTEGER,
                wins INTEGER,
                losses INTEGER,
                total_pnl_pct REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def start_tracking(
        self,
        signal_id: str,
        symbol: str,
        quality: str,
        score: int,
        entry_price: float,
        stop_loss: float,
        take_profit_1: float,
        take_profit_2: float
    ) -> TrackedSignal:
        """Start tracking a new signal"""
        signal = TrackedSignal(
            signal_id=signal_id,
            symbol=symbol,
            quality=quality,
            score=score,
            entry_price=entry_price,
            entry_time=int(time.time() * 1000),
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2
        )
        
        self.active_signals[signal_id] = signal
        
        # Save to DB
        self._save_signal(signal)
        
        logger.info(f"📊 Tracking signal: {symbol} {quality}-tier")
        
        return signal
    
    def update_price(self, signal_id: str, current_price: float):
        """Update signal with current price"""
        if signal_id not in self.active_signals:
            return
        
        signal = self.active_signals[signal_id]
        
        # Calculate current PnL (for SHORT position)
        pnl_pct = ((signal.entry_price - current_price) / signal.entry_price) * 100
        
        # Update max profit/drawdown
        if pnl_pct > signal.max_profit_pct:
            signal.max_profit_pct = pnl_pct
        if pnl_pct < signal.max_drawdown_pct:
            signal.max_drawdown_pct = pnl_pct
        
        # Check targets (for SHORT)
        if current_price <= signal.take_profit_1 and not signal.hit_tp1:
            signal.hit_tp1 = True
            logger.info(f"🎯 TP1 HIT: {signal.symbol}")
        
        if current_price <= signal.take_profit_2 and not signal.hit_tp2:
            signal.hit_tp2 = True
            logger.info(f"🎯 TP2 HIT: {signal.symbol}")
        
        # Check stop loss
        if current_price >= signal.stop_loss:
            self.close_signal(signal_id, current_price, SignalOutcome.LOSS)
        
        # Check if both TPs hit
        if signal.hit_tp2:
            self.close_signal(signal_id, current_price, SignalOutcome.WIN)
    
    def close_signal(
        self,
        signal_id: str,
        exit_price: float,
        outcome: SignalOutcome
    ):
        """Close and record signal outcome"""
        if signal_id not in self.active_signals:
            return
        
        signal = self.active_signals[signal_id]
        
        signal.exit_price = exit_price
        signal.exit_time = int(time.time() * 1000)
        signal.outcome = outcome
        signal.pnl_pct = ((signal.entry_price - exit_price) / signal.entry_price) * 100
        signal.duration_minutes = (signal.exit_time - signal.entry_time) // 60000
        
        # Save to DB
        self._save_signal(signal)
        
        # Remove from active
        del self.active_signals[signal_id]
        
        emoji = "✅" if outcome == SignalOutcome.WIN else "❌"
        logger.info(
            f"{emoji} Signal closed: {signal.symbol} {outcome.value} "
            f"{signal.pnl_pct:+.2f}%"
        )
    
    def _save_signal(self, signal: TrackedSignal):
        """Save signal to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            signal.signal_id,
            signal.symbol,
            signal.quality,
            signal.score,
            signal.entry_price,
            signal.entry_time,
            signal.stop_loss,
            signal.take_profit_1,
            signal.take_profit_2,
            signal.outcome.value,
            signal.exit_price,
            signal.exit_time,
            signal.pnl_pct,
            1 if signal.hit_tp1 else 0,
            1 if signal.hit_tp2 else 0,
            signal.max_profit_pct,
            signal.max_drawdown_pct,
            signal.duration_minutes
        ))
        
        conn.commit()
        conn.close()
    
    def get_stats(self, period: str = "7d") -> PerformanceStats:
        """Get performance statistics for period"""
        # Calculate cutoff time
        now = int(time.time() * 1000)
        
        if period == "1d":
            cutoff = now - 86400000
        elif period == "7d":
            cutoff = now - 7 * 86400000
        elif period == "30d":
            cutoff = now - 30 * 86400000
        else:
            cutoff = 0  # All time
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get signals in period
        cursor.execute('''
            SELECT * FROM signals WHERE entry_time > ?
        ''', (cutoff,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return PerformanceStats(period=period)
        
        # Parse results
        signals = []
        for row in rows:
            signals.append({
                'quality': row[2],
                'score': row[3],
                'outcome': row[9],
                'pnl_pct': row[12] or 0,
                'symbol': row[1]
            })
        
        # Calculate stats
        wins = [s for s in signals if s['outcome'] == 'WIN']
        losses = [s for s in signals if s['outcome'] == 'LOSS']
        
        total = len(wins) + len(losses)
        win_rate = len(wins) / total * 100 if total > 0 else 0
        
        win_pnls = [s['pnl_pct'] for s in wins]
        loss_pnls = [s['pnl_pct'] for s in losses]
        all_pnls = [s['pnl_pct'] for s in signals if s['outcome'] in ['WIN', 'LOSS']]
        
        avg_win = statistics.mean(win_pnls) if win_pnls else 0
        avg_loss = statistics.mean(loss_pnls) if loss_pnls else 0
        
        gross_profit = sum(p for p in all_pnls if p > 0)
        gross_loss = abs(sum(p for p in all_pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
        
        # By quality
        quality_win_rates = {}
        quality_counts = {}
        
        for q in ['S', 'A', 'B', 'C']:
            q_signals = [s for s in signals if s['quality'] == q]
            q_wins = [s for s in q_signals if s['outcome'] == 'WIN']
            q_total = len([s for s in q_signals if s['outcome'] in ['WIN', 'LOSS']])
            
            quality_counts[q] = len(q_signals)
            quality_win_rates[q] = len(q_wins) / q_total * 100 if q_total > 0 else 0
        
        # Best/worst
        best_pnl = max(all_pnls) if all_pnls else 0
        worst_pnl = min(all_pnls) if all_pnls else 0
        
        best_signal = next((s for s in signals if s['pnl_pct'] == best_pnl), None)
        worst_signal = next((s for s in signals if s['pnl_pct'] == worst_pnl), None)
        
        return PerformanceStats(
            period=period,
            total_signals=len(signals),
            wins=len(wins),
            losses=len(losses),
            pending=len([s for s in signals if s['outcome'] == 'PENDING']),
            win_rate=win_rate,
            total_pnl_pct=sum(all_pnls),
            avg_pnl_pct=statistics.mean(all_pnls) if all_pnls else 0,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            profit_factor=profit_factor,
            quality_win_rates=quality_win_rates,
            quality_counts=quality_counts,
            best_trade_pct=best_pnl,
            worst_trade_pct=worst_pnl,
            best_symbol=best_signal['symbol'] if best_signal else "",
            worst_symbol=worst_signal['symbol'] if worst_signal else ""
        )
    
    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """Get best performing symbols"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT symbol, 
                   COUNT(*) as total,
                   SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                   SUM(pnl_pct) as total_pnl
            FROM signals
            WHERE outcome IN ('WIN', 'LOSS')
            GROUP BY symbol
            ORDER BY total_pnl DESC
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                'symbol': row[0],
                'total_signals': row[1],
                'wins': row[2],
                'win_rate': row[2] / row[1] * 100 if row[1] > 0 else 0,
                'total_pnl_pct': row[3]
            }
            for row in rows
        ]
    
    def get_quality_analysis(self) -> Dict:
        """Analyze performance by signal quality"""
        stats_all = self.get_stats("all")
        
        return {
            'S_tier': {
                'count': stats_all.quality_counts.get('S', 0),
                'win_rate': stats_all.quality_win_rates.get('S', 0),
                'verdict': 'EXCELLENT' if stats_all.quality_win_rates.get('S', 0) > 70 else 'GOOD'
            },
            'A_tier': {
                'count': stats_all.quality_counts.get('A', 0),
                'win_rate': stats_all.quality_win_rates.get('A', 0),
                'verdict': 'GOOD' if stats_all.quality_win_rates.get('A', 0) > 60 else 'AVERAGE'
            },
            'B_tier': {
                'count': stats_all.quality_counts.get('B', 0),
                'win_rate': stats_all.quality_win_rates.get('B', 0),
                'verdict': 'AVERAGE' if stats_all.quality_win_rates.get('B', 0) > 50 else 'POOR'
            },
            'C_tier': {
                'count': stats_all.quality_counts.get('C', 0),
                'win_rate': stats_all.quality_win_rates.get('C', 0),
                'verdict': 'RISKY'
            }
        }
    
    def generate_report(self) -> str:
        """Generate performance report"""
        stats_7d = self.get_stats("7d")
        stats_30d = self.get_stats("30d")
        quality = self.get_quality_analysis()
        leaderboard = self.get_leaderboard(5)
        
        report = f"""
📊 PERFORMANCE REPORT
{'=' * 40}

📈 7-DAY STATS
├ Signals: {stats_7d.total_signals}
├ Win Rate: {stats_7d.win_rate:.1f}%
├ Total PnL: {stats_7d.total_pnl_pct:+.2f}%
├ Profit Factor: {stats_7d.profit_factor:.2f}
└ Best Trade: {stats_7d.best_trade_pct:+.2f}%

📈 30-DAY STATS
├ Signals: {stats_30d.total_signals}
├ Win Rate: {stats_30d.win_rate:.1f}%
├ Total PnL: {stats_30d.total_pnl_pct:+.2f}%
└ Profit Factor: {stats_30d.profit_factor:.2f}

🎯 QUALITY BREAKDOWN
├ S-Tier: {quality['S_tier']['win_rate']:.0f}% WR ({quality['S_tier']['count']} signals)
├ A-Tier: {quality['A_tier']['win_rate']:.0f}% WR ({quality['A_tier']['count']} signals)
├ B-Tier: {quality['B_tier']['win_rate']:.0f}% WR ({quality['B_tier']['count']} signals)
└ C-Tier: {quality['C_tier']['win_rate']:.0f}% WR ({quality['C_tier']['count']} signals)

🏆 TOP SYMBOLS
"""
        for i, sym in enumerate(leaderboard, 1):
            report += f"  {i}. {sym['symbol']}: {sym['total_pnl_pct']:+.2f}% ({sym['win_rate']:.0f}% WR)\n"
        
        return report

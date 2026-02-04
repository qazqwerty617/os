"""
MEXC Pump Monitor - Signal Database
Optimized SQLite storage for signals, trades, and analysis
"""

import sqlite3
import json
import time
import logging
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


# SQL Table definitions
TABLE_DEFINITIONS = {
    'signals': """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            price REAL NOT NULL,
            price_change_pct REAL NOT NULL,
            volume_ratio REAL,
            volume_usd REAL,
            rsi REAL,
            ema_extension_pct REAL,
            score INTEGER NOT NULL,
            tier TEXT,
            entry_low REAL,
            entry_high REAL,
            stop_loss REAL,
            take_profit REAL,
            has_divergence INTEGER,
            divergence_type TEXT,
            score_breakdown TEXT,
            mtf_score INTEGER,
            whale_pressure INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        )
    """,
    'whale_orders': """
        CREATE TABLE IF NOT EXISTS whale_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            value_usd REAL NOT NULL,
            category TEXT NOT NULL,
            is_aggressive INTEGER,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        )
    """,
    'liquidations': """
        CREATE TABLE IF NOT EXISTS liquidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            side TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            value_usd REAL NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s', 'now') * 1000)
        )
    """,
    'trades': """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            side TEXT NOT NULL,
            value_usd REAL NOT NULL
        )
    """,
    'market_snapshots': """
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            price REAL NOT NULL,
            volume_24h REAL,
            open_interest REAL,
            funding_rate REAL,
            long_short_ratio REAL
        )
    """,
    'signal_performance': """
        CREATE TABLE IF NOT EXISTS signal_performance (
            signal_id INTEGER PRIMARY KEY,
            outcome TEXT,
            max_profit_pct REAL,
            max_loss_pct REAL,
            final_pct REAL,
            duration_seconds INTEGER,
            hit_tp INTEGER,
            hit_sl INTEGER,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    """
}

# Indexes
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score)",
    "CREATE INDEX IF NOT EXISTS idx_whale_symbol ON whale_orders(symbol)",
    "CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol, timestamp)"
]

# Tier thresholds
TIER_THRESHOLDS = [
    (50, 'MEGA'),
    (30, 'MASSIVE'),
    (15, 'STRONG'),
    (0, 'EARLY')
]


class SignalDatabase:
    """Optimized SQLite database for signal storage"""
    
    def __init__(self, db_path: str = "pump_monitor.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for table_sql in TABLE_DEFINITIONS.values():
                cursor.execute(table_sql)
            
            for index_sql in INDEXES:
                cursor.execute(index_sql)
            
            conn.commit()
            logger.info(f"Database initialized: {self.db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def _get_tier(self, price_change: float) -> str:
        """Get signal tier based on price change"""
        for threshold, tier in TIER_THRESHOLDS:
            if price_change >= threshold:
                return tier
        return 'EARLY'
    
    def save_signal(self, signal) -> int:
        """Save a pump signal to database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO signals (
                    symbol, timestamp, price, price_change_pct,
                    volume_ratio, volume_usd, rsi, ema_extension_pct,
                    score, tier, entry_low, entry_high, stop_loss, take_profit,
                    has_divergence, divergence_type, score_breakdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.symbol, signal.timestamp, signal.price, signal.price_change_pct,
                signal.volume_ratio, signal.volume_usd, signal.rsi, signal.ema_extension_pct,
                signal.score, self._get_tier(signal.price_change_pct),
                signal.entry_zone_low, signal.entry_zone_high, signal.stop_loss, signal.take_profit,
                1 if signal.has_divergence else 0, signal.divergence_type,
                json.dumps(signal.score_breakdown)
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def save_whale_order(self, order) -> int:
        """Save whale order to database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO whale_orders (
                    symbol, timestamp, side, price, quantity, value_usd, category, is_aggressive
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.symbol, order.timestamp, order.side.value, order.price,
                order.quantity, order.value_usd, order.category.value,
                1 if order.is_aggressive else 0
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def save_trade(self, symbol: str, timestamp: int, price: float, quantity: float, side: str):
        """Save trade for volume profile analysis"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO trades (symbol, timestamp, price, quantity, side, value_usd) VALUES (?, ?, ?, ?, ?, ?)",
                (symbol, timestamp, price, quantity, side, price * quantity)
            )
            conn.commit()
    
    def save_liquidation(self, symbol: str, timestamp: int, side: str, price: float, quantity: float):
        """Save liquidation event"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO liquidations (symbol, timestamp, side, price, quantity, value_usd) VALUES (?, ?, ?, ?, ?, ?)",
                (symbol, timestamp, side, price, quantity, price * quantity)
            )
            conn.commit()
    
    def save_market_snapshot(
        self, symbol: str, price: float,
        volume_24h: float = None, open_interest: float = None,
        funding_rate: float = None, long_short_ratio: float = None
    ):
        """Save market state snapshot"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_snapshots 
                (symbol, timestamp, price, volume_24h, open_interest, funding_rate, long_short_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (symbol, int(time.time() * 1000), price, volume_24h, open_interest, funding_rate, long_short_ratio))
            conn.commit()
    
    def get_signals(
        self, symbol: str = None, min_score: int = None, tier: str = None,
        limit: int = 100, start_time: int = None, end_time: int = None
    ) -> List[Dict]:
        """Query signals with filters"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            conditions, params = ["1=1"], []
            
            if symbol:
                conditions.append("symbol = ?")
                params.append(symbol)
            if min_score:
                conditions.append("score >= ?")
                params.append(min_score)
            if tier:
                conditions.append("tier = ?")
                params.append(tier)
            if start_time:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time:
                conditions.append("timestamp <= ?")
                params.append(end_time)
            
            params.append(limit)
            query = f"SELECT * FROM signals WHERE {' AND '.join(conditions)} ORDER BY timestamp DESC LIMIT ?"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_whale_activity(self, symbol: str = None, hours: int = 24) -> Dict[str, Any]:
        """Get whale activity summary"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = int(time.time() * 1000) - (hours * 3600000)
            
            if symbol:
                cursor.execute("""
                    SELECT side, category, COUNT(*) as count, SUM(value_usd) as total_value
                    FROM whale_orders WHERE symbol = ? AND timestamp > ? GROUP BY side, category
                """, (symbol, cutoff))
            else:
                cursor.execute("""
                    SELECT side, category, COUNT(*) as count, SUM(value_usd) as total_value
                    FROM whale_orders WHERE timestamp > ? GROUP BY side, category
                """, (cutoff,))
            
            summary = {'buy_volume': 0, 'sell_volume': 0, 'buy_count': 0, 'sell_count': 0, 'by_category': {}}
            
            for row in cursor.fetchall():
                side, cat, count, val = row['side'], row['category'], row['count'], row['total_value']
                
                key = 'buy' if side == 'BUY' else 'sell'
                summary[f'{key}_volume'] += val
                summary[f'{key}_count'] += count
                
                if cat not in summary['by_category']:
                    summary['by_category'][cat] = {'buy': 0, 'sell': 0}
                summary['by_category'][cat][key] += val
            
            return summary
    
    def get_liquidation_stats(self, symbol: str = None, hours: int = 24) -> Dict[str, Any]:
        """Get liquidation statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = int(time.time() * 1000) - (hours * 3600000)
            
            query = """
                SELECT side, COUNT(*) as count, SUM(value_usd) as total_value, AVG(value_usd) as avg_value
                FROM liquidations WHERE {} AND timestamp > ? GROUP BY side
            """
            
            if symbol:
                cursor.execute(query.format("symbol = ?"), (symbol, cutoff))
            else:
                cursor.execute(query.format("1=1"), (cutoff,))
            
            stats = {'long_liquidations': 0, 'short_liquidations': 0, 'long_volume': 0, 'short_volume': 0}
            
            for row in cursor.fetchall():
                prefix = 'long' if row['side'] == 'LONG' else 'short'
                stats[f'{prefix}_liquidations'] = row['count']
                stats[f'{prefix}_volume'] = row['total_value']
            
            return stats
    
    def get_signal_win_rate(self, min_score: int = 70, days: int = 7) -> Dict[str, Any]:
        """Calculate signal win rate from historical data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = int(time.time() * 1000) - (days * 86400000)
            
            cursor.execute("""
                SELECT s.tier, COUNT(*) as total,
                    SUM(CASE WHEN p.hit_tp = 1 THEN 1 ELSE 0 END) as wins,
                    AVG(p.max_profit_pct) as avg_max_profit,
                    AVG(p.max_loss_pct) as avg_max_loss
                FROM signals s LEFT JOIN signal_performance p ON s.id = p.signal_id
                WHERE s.score >= ? AND s.timestamp > ? GROUP BY s.tier
            """, (min_score, cutoff))
            
            return {
                row['tier']: {
                    'total_signals': row['total'],
                    'winning': row['wins'] or 0,
                    'win_rate': (row['wins'] / row['total'] * 100) if row['total'] > 0 and row['wins'] else 0,
                    'avg_max_profit': row['avg_max_profit'],
                    'avg_max_loss': row['avg_max_loss']
                }
                for row in cursor.fetchall()
            }
    
    def update_signal_performance(
        self, signal_id: int, outcome: str, max_profit_pct: float,
        max_loss_pct: float, final_pct: float, duration_seconds: int,
        hit_tp: bool, hit_sl: bool
    ):
        """Update signal performance after trade completes"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO signal_performance
                (signal_id, outcome, max_profit_pct, max_loss_pct, final_pct, duration_seconds, hit_tp, hit_sl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (signal_id, outcome, max_profit_pct, max_loss_pct, final_pct, duration_seconds, 1 if hit_tp else 0, 1 if hit_sl else 0))
            conn.commit()
    
    def cleanup_old_data(self, days: int = 30):
        """Remove data older than specified days"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cutoff = int(time.time() * 1000) - (days * 86400000)
            
            for table in ['trades', 'market_snapshots']:
                cursor.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
            
            conn.commit()
            logger.info(f"Cleaned up data older than {days} days")
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            return {
                table: cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in TABLE_DEFINITIONS.keys()
            }

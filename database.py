"""
MEXC Pump Monitor - Signal Database
SQLite storage for all signals, trades, and historical analysis
"""

import sqlite3
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)


class SignalDatabase:
    """
    SQLite database for persistent signal storage
    Stores all signals, whale orders, liquidations for analysis
    """
    
    def __init__(self, db_path: str = "pump_monitor.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Signals table
            cursor.execute("""
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
            """)
            
            # Whale orders table
            cursor.execute("""
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
            """)
            
            # Liquidations table
            cursor.execute("""
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
            """)
            
            # Trades table (for volume profile)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    side TEXT NOT NULL,
                    value_usd REAL NOT NULL
                )
            """)
            
            # Market snapshots
            cursor.execute("""
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
            """)
            
            # Performance tracking (for backtesting signals)
            cursor.execute("""
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
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_whale_symbol ON whale_orders(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol_time ON trades(symbol, timestamp)")
            
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
    
    def save_signal(self, signal) -> int:
        """
        Save a pump signal to database
        
        Args:
            signal: PumpSignal object
        
        Returns:
            Signal ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Determine tier
            tier = 'STRONG'
            if signal.price_change_pct >= 50:
                tier = 'MEGA'
            elif signal.price_change_pct >= 30:
                tier = 'MASSIVE'
            elif signal.price_change_pct >= 15:
                tier = 'STRONG'
            else:
                tier = 'EARLY'
            
            cursor.execute("""
                INSERT INTO signals (
                    symbol, timestamp, price, price_change_pct,
                    volume_ratio, volume_usd, rsi, ema_extension_pct,
                    score, tier, entry_low, entry_high, stop_loss, take_profit,
                    has_divergence, divergence_type, score_breakdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal.symbol,
                signal.timestamp,
                signal.price,
                signal.price_change_pct,
                signal.volume_ratio,
                signal.volume_usd,
                signal.rsi,
                signal.ema_extension_pct,
                signal.score,
                tier,
                signal.entry_zone_low,
                signal.entry_zone_high,
                signal.stop_loss,
                signal.take_profit,
                1 if signal.has_divergence else 0,
                signal.divergence_type,
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
                    symbol, timestamp, side, price, quantity,
                    value_usd, category, is_aggressive
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order.symbol,
                order.timestamp,
                order.side.value,
                order.price,
                order.quantity,
                order.value_usd,
                order.category.value,
                1 if order.is_aggressive else 0
            ))
            
            conn.commit()
            return cursor.lastrowid
    
    def save_trade(
        self,
        symbol: str,
        timestamp: int,
        price: float,
        quantity: float,
        side: str
    ):
        """Save trade for volume profile analysis"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO trades (symbol, timestamp, price, quantity, side, value_usd)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol, timestamp, price, quantity, side, price * quantity))
            
            conn.commit()
    
    def save_liquidation(
        self,
        symbol: str,
        timestamp: int,
        side: str,
        price: float,
        quantity: float
    ):
        """Save liquidation event"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO liquidations (symbol, timestamp, side, price, quantity, value_usd)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (symbol, timestamp, side, price, quantity, price * quantity))
            
            conn.commit()
    
    def save_market_snapshot(
        self,
        symbol: str,
        price: float,
        volume_24h: float = None,
        open_interest: float = None,
        funding_rate: float = None,
        long_short_ratio: float = None
    ):
        """Save market state snapshot"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO market_snapshots 
                (symbol, timestamp, price, volume_24h, open_interest, funding_rate, long_short_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                int(time.time() * 1000),
                price,
                volume_24h,
                open_interest,
                funding_rate,
                long_short_ratio
            ))
            
            conn.commit()
    
    def get_signals(
        self,
        symbol: str = None,
        min_score: int = None,
        tier: str = None,
        limit: int = 100,
        start_time: int = None,
        end_time: int = None
    ) -> List[Dict]:
        """Query signals with filters"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM signals WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if min_score:
                query += " AND score >= ?"
                params.append(min_score)
            
            if tier:
                query += " AND tier = ?"
                params.append(tier)
            
            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)
            
            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_whale_activity(
        self,
        symbol: str = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get whale activity summary"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = int(time.time() * 1000) - (hours * 3600 * 1000)
            
            if symbol:
                cursor.execute("""
                    SELECT 
                        side,
                        category,
                        COUNT(*) as count,
                        SUM(value_usd) as total_value
                    FROM whale_orders
                    WHERE symbol = ? AND timestamp > ?
                    GROUP BY side, category
                """, (symbol, cutoff))
            else:
                cursor.execute("""
                    SELECT 
                        side,
                        category,
                        COUNT(*) as count,
                        SUM(value_usd) as total_value
                    FROM whale_orders
                    WHERE timestamp > ?
                    GROUP BY side, category
                """, (cutoff,))
            
            results = cursor.fetchall()
            
            summary = {
                'buy_volume': 0,
                'sell_volume': 0,
                'buy_count': 0,
                'sell_count': 0,
                'by_category': {}
            }
            
            for row in results:
                side = row['side']
                category = row['category']
                count = row['count']
                value = row['total_value']
                
                if side == 'BUY':
                    summary['buy_volume'] += value
                    summary['buy_count'] += count
                else:
                    summary['sell_volume'] += value
                    summary['sell_count'] += count
                
                if category not in summary['by_category']:
                    summary['by_category'][category] = {'buy': 0, 'sell': 0}
                
                summary['by_category'][category][side.lower()] += value
            
            return summary
    
    def get_liquidation_stats(
        self,
        symbol: str = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get liquidation statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = int(time.time() * 1000) - (hours * 3600 * 1000)
            
            if symbol:
                cursor.execute("""
                    SELECT 
                        side,
                        COUNT(*) as count,
                        SUM(value_usd) as total_value,
                        AVG(value_usd) as avg_value
                    FROM liquidations
                    WHERE symbol = ? AND timestamp > ?
                    GROUP BY side
                """, (symbol, cutoff))
            else:
                cursor.execute("""
                    SELECT 
                        side,
                        COUNT(*) as count,
                        SUM(value_usd) as total_value,
                        AVG(value_usd) as avg_value
                    FROM liquidations
                    WHERE timestamp > ?
                    GROUP BY side
                """, (cutoff,))
            
            results = cursor.fetchall()
            
            stats = {
                'long_liquidations': 0,
                'short_liquidations': 0,
                'long_volume': 0,
                'short_volume': 0
            }
            
            for row in results:
                if row['side'] == 'LONG':
                    stats['long_liquidations'] = row['count']
                    stats['long_volume'] = row['total_value']
                else:
                    stats['short_liquidations'] = row['count']
                    stats['short_volume'] = row['total_value']
            
            return stats
    
    def get_signal_win_rate(self, min_score: int = 70, days: int = 7) -> Dict[str, Any]:
        """Calculate signal win rate from historical data"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = int(time.time() * 1000) - (days * 24 * 3600 * 1000)
            
            cursor.execute("""
                SELECT 
                    s.tier,
                    COUNT(*) as total,
                    SUM(CASE WHEN p.hit_tp = 1 THEN 1 ELSE 0 END) as wins,
                    AVG(p.max_profit_pct) as avg_max_profit,
                    AVG(p.max_loss_pct) as avg_max_loss
                FROM signals s
                LEFT JOIN signal_performance p ON s.id = p.signal_id
                WHERE s.score >= ? AND s.timestamp > ?
                GROUP BY s.tier
            """, (min_score, cutoff))
            
            results = cursor.fetchall()
            
            stats = {}
            for row in results:
                tier = row['tier']
                total = row['total']
                wins = row['wins'] or 0
                
                stats[tier] = {
                    'total_signals': total,
                    'winning': wins,
                    'win_rate': (wins / total * 100) if total > 0 else 0,
                    'avg_max_profit': row['avg_max_profit'],
                    'avg_max_loss': row['avg_max_loss']
                }
            
            return stats
    
    def update_signal_performance(
        self,
        signal_id: int,
        outcome: str,
        max_profit_pct: float,
        max_loss_pct: float,
        final_pct: float,
        duration_seconds: int,
        hit_tp: bool,
        hit_sl: bool
    ):
        """Update signal performance after trade completes"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO signal_performance
                (signal_id, outcome, max_profit_pct, max_loss_pct, final_pct, 
                 duration_seconds, hit_tp, hit_sl)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, outcome, max_profit_pct, max_loss_pct,
                final_pct, duration_seconds, 1 if hit_tp else 0, 1 if hit_sl else 0
            ))
            
            conn.commit()
    
    def cleanup_old_data(self, days: int = 30):
        """Remove data older than specified days"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cutoff = int(time.time() * 1000) - (days * 24 * 3600 * 1000)
            
            cursor.execute("DELETE FROM trades WHERE timestamp < ?", (cutoff,))
            cursor.execute("DELETE FROM market_snapshots WHERE timestamp < ?", (cutoff,))
            
            conn.commit()
            logger.info(f"Cleaned up data older than {days} days")
    
    def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            tables = ['signals', 'whale_orders', 'liquidations', 'trades', 'market_snapshots']
            
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            
            return stats

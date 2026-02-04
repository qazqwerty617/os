"""
MEXC Pump Monitor - Self-Learning Engine
Optimized signal learning and performance optimization
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Trade result for learning"""
    signal_id: str
    symbol: str
    timestamp: int
    
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    signal_score: int
    signal_quality: str
    
    rsi: float
    volume_ratio: float
    price_change_pct: float
    ema_extension_pct: float
    whale_pressure: int
    funding_rate: float
    
    outcome: str  # 'tp1', 'tp2', 'sl', 'breakeven', 'timeout'
    exit_price: float = 0
    profit_pct: float = 0
    duration_minutes: int = 0
    is_win: bool = False
    
    def __post_init__(self):
        if self.exit_price > 0 and self.entry_price > 0:
            self.profit_pct = ((self.entry_price - self.exit_price) / self.entry_price) * 100
            self.is_win = self.profit_pct > 0


@dataclass
class LearningStats:
    """Learning statistics"""
    total_signals: int = 0
    total_wins: int = 0
    total_losses: int = 0
    win_rate: float = 0
    avg_profit_pct: float = 0
    avg_loss_pct: float = 0
    expectancy: float = 0
    profit_factor: float = 0
    
    best_rsi_range: Tuple[float, float] = (80, 95)
    best_volume_ratio: float = 5.0
    best_extension_range: Tuple[float, float] = (7, 15)
    optimal_min_score: int = 70
    optimal_sl_multiplier: float = 1.0
    optimal_tp_multiplier: float = 1.0


class SelfLearningEngine:
    """
    Optimized self-learning engine
    
    Features:
    - Analyzes win rate by parameters
    - Finds optimal RSI, Volume, Extension ranges
    - Adjusts signal thresholds
    - Improves SL/TP levels
    """
    
    DEFAULT_ADJUSTMENTS = {
        'min_score_threshold': 65,
        'rsi_weight': 1.0,
        'volume_weight': 1.0,
        'extension_weight': 1.0,
        'sl_adjustment': 1.0,
        'tp_adjustment': 1.0,
        'skip_low_rsi': 70,
        'skip_low_volume': 2.0,
    }
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or "./learning_data")
        self.data_dir.mkdir(exist_ok=True)
        
        self.outcomes: List[TradeOutcome] = []
        self.max_outcomes = 5000
        
        self.stats = LearningStats()
        self.feature_analysis: Dict[str, Dict] = {}
        self.adjustments = self.DEFAULT_ADJUSTMENTS.copy()
        self.pending_signals: Dict[str, dict] = {}
        
        self._load_data()
    
    def _load_data(self):
        """Load historical data"""
        outcomes_file = self.data_dir / "outcomes.json"
        adjustments_file = self.data_dir / "adjustments.json"
        
        try:
            if outcomes_file.exists():
                with open(outcomes_file, 'r') as f:
                    self.outcomes = [TradeOutcome(**o) for o in json.load(f)]
                logger.info(f"Loaded {len(self.outcomes)} historical outcomes")
        except Exception as e:
            logger.error(f"Failed to load outcomes: {e}")
        
        try:
            if adjustments_file.exists():
                with open(adjustments_file, 'r') as f:
                    self.adjustments.update(json.load(f))
                logger.info("Loaded learned adjustments")
        except Exception as e:
            logger.error(f"Failed to load adjustments: {e}")
    
    def _save_data(self):
        """Save data"""
        try:
            with open(self.data_dir / "outcomes.json", 'w') as f:
                json.dump([asdict(o) for o in self.outcomes], f, indent=2)
            
            with open(self.data_dir / "adjustments.json", 'w') as f:
                json.dump(self.adjustments, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save learning data: {e}")
    
    def track_signal(self, signal: dict) -> str:
        """Start tracking a signal"""
        signal_id = f"{signal.get('symbol')}_{int(time.time()*1000)}"
        
        self.pending_signals[signal_id] = {
            'signal': signal,
            'timestamp': int(time.time() * 1000),
            'status': 'pending'
        }
        
        # Cleanup old pending signals (>24h)
        cutoff = int(time.time() * 1000) - 86400000
        self.pending_signals = {
            k: v for k, v in self.pending_signals.items()
            if v['timestamp'] > cutoff
        }
        
        return signal_id
    
    def record_outcome(self, signal_id: str, outcome: str, exit_price: float):
        """Record trade outcome"""
        pending = self.pending_signals.pop(signal_id, None)
        if not pending:
            logger.warning(f"Unknown signal_id: {signal_id}")
            return
        
        signal = pending['signal']
        duration = (int(time.time() * 1000) - pending['timestamp']) // 60000
        
        trade_outcome = TradeOutcome(
            signal_id=signal_id,
            symbol=signal.get('symbol', ''),
            timestamp=pending['timestamp'],
            entry_price=signal.get('entry_price', signal.get('price', 0)),
            stop_loss=signal.get('stop_loss', 0),
            take_profit_1=signal.get('take_profit_1', 0),
            take_profit_2=signal.get('take_profit_2', 0),
            signal_score=signal.get('final_score', signal.get('score', 0)),
            signal_quality=signal.get('quality', 'B'),
            rsi=signal.get('rsi', 50),
            volume_ratio=signal.get('volume_ratio', 1),
            price_change_pct=signal.get('price_change_pct', 0),
            ema_extension_pct=signal.get('ema_extension_pct', 0),
            whale_pressure=signal.get('whale_pressure', 50),
            funding_rate=signal.get('funding_rate', 0),
            outcome=outcome,
            exit_price=exit_price,
            duration_minutes=duration
        )
        
        self.outcomes.append(trade_outcome)
        if len(self.outcomes) > self.max_outcomes:
            self.outcomes = self.outcomes[-self.max_outcomes:]
        
        logger.info(f"Recorded: {signal_id} -> {outcome} ({trade_outcome.profit_pct:.2f}%)")
        
        if len(self.outcomes) % 10 == 0:
            asyncio.create_task(self._relearn())
    
    async def _relearn(self):
        """Relearn from data"""
        if len(self.outcomes) < 20:
            return
        
        logger.info("🧠 Starting self-learning analysis...")
        
        try:
            self._calculate_stats()
            self._analyze_features()
            self._update_adjustments()
            self._save_data()
            logger.info(f"Learning complete. Win rate: {self.stats.win_rate:.1%}")
        except Exception as e:
            logger.error(f"Learning error: {e}")
    
    def _calculate_stats(self):
        """Calculate overall statistics"""
        if not self.outcomes:
            return
        
        wins = [o for o in self.outcomes if o.is_win]
        losses = [o for o in self.outcomes if not o.is_win]
        
        s = self.stats
        s.total_signals = len(self.outcomes)
        s.total_wins = len(wins)
        s.total_losses = len(losses)
        
        if s.total_signals > 0:
            s.win_rate = s.total_wins / s.total_signals
        
        if wins:
            s.avg_profit_pct = sum(o.profit_pct for o in wins) / len(wins)
        
        if losses:
            s.avg_loss_pct = sum(abs(o.profit_pct) for o in losses) / len(losses)
        
        if s.total_signals > 0:
            s.expectancy = (s.win_rate * s.avg_profit_pct) - ((1 - s.win_rate) * s.avg_loss_pct)
        
        gross_profit = sum(o.profit_pct for o in wins) if wins else 0
        gross_loss = abs(sum(o.profit_pct for o in losses)) if losses else 1
        s.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    def _analyze_features(self):
        """Analyze feature effectiveness"""
        if len(self.outcomes) < 20:
            return
        
        # Helper to find best bucket
        def find_best_bucket(outcomes, getter, bucket_size=5) -> Tuple[int, float]:
            buckets = defaultdict(list)
            for o in outcomes:
                bucket = int(getter(o) // bucket_size) * bucket_size
                buckets[bucket].append(o)
            
            best_wr, best_bucket = 0, 50
            for bucket, items in buckets.items():
                if len(items) >= 3:
                    wr = sum(1 for o in items if o.is_win) / len(items)
                    if wr > best_wr:
                        best_wr, best_bucket = wr, bucket
            return best_bucket, best_wr
        
        # RSI analysis
        best_rsi, _ = find_best_bucket(self.outcomes, lambda o: o.rsi, 5)
        self.stats.best_rsi_range = (best_rsi, best_rsi + 10)
        
        # Volume ratio analysis
        best_vol, _ = find_best_bucket(self.outcomes, lambda o: o.volume_ratio, 1)
        self.stats.best_volume_ratio = max(2.0, float(best_vol))
        
        # Score analysis - find minimum profitable score
        score_buckets = defaultdict(list)
        for o in self.outcomes:
            bucket = int(o.signal_score // 10) * 10
            score_buckets[bucket].append(o)
        
        for score in sorted(score_buckets.keys()):
            items = score_buckets[score]
            if len(items) >= 3:
                wr = sum(1 for o in items if o.is_win) / len(items)
                if wr >= 0.5:
                    self.stats.optimal_min_score = score
                    break
        
        self.feature_analysis = {
            'best_rsi': best_rsi,
            'best_volume': best_vol,
            'best_score': self.stats.optimal_min_score
        }
    
    def _update_adjustments(self):
        """Update adjustments based on analysis"""
        if self.stats.total_signals < 20:
            return
        
        a = self.adjustments
        s = self.stats
        
        a['min_score_threshold'] = s.optimal_min_score
        a['skip_low_rsi'] = s.best_rsi_range[0]
        a['skip_low_volume'] = max(2.0, s.best_volume_ratio * 0.8)
        
        # Adjust SL based on win rate
        if s.win_rate < 0.4:
            a['sl_adjustment'] = max(0.7, a['sl_adjustment'] - 0.05)
        elif s.win_rate > 0.6:
            a['sl_adjustment'] = min(1.2, a['sl_adjustment'] + 0.02)
        
        # Adjust weights based on best ranges
        if s.best_rsi_range[0] >= 85:
            a['rsi_weight'] = 1.2
        if s.best_volume_ratio >= 7:
            a['volume_weight'] = 1.2
        
        logger.info(f"Updated adjustments: {a}")
    
    def should_take_signal(self, signal: dict) -> Tuple[bool, str]:
        """Check if signal should be taken based on learning"""
        score = signal.get('final_score', signal.get('score', 0))
        rsi = signal.get('rsi', 50)
        volume_ratio = signal.get('volume_ratio', 1)
        a = self.adjustments
        
        if score < a['min_score_threshold']:
            return False, f"Score {score} below {a['min_score_threshold']}"
        
        if rsi < a['skip_low_rsi']:
            return False, f"RSI {rsi} below optimal"
        
        if volume_ratio < a['skip_low_volume']:
            return False, f"Volume ratio {volume_ratio} below threshold"
        
        return True, "Signal passes filters"
    
    def adjust_levels(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        is_short: bool = True
    ) -> Tuple[float, float]:
        """Adjust SL/TP based on learning"""
        sl_mult = self.adjustments.get('sl_adjustment', 1.0)
        tp_mult = self.adjustments.get('tp_adjustment', 1.0)
        
        if is_short:
            sl_distance = stop_loss - entry
            tp_distance = entry - take_profit
            return entry + (sl_distance * sl_mult), entry - (tp_distance * tp_mult)
        else:
            sl_distance = entry - stop_loss
            tp_distance = take_profit - entry
            return entry - (sl_distance * sl_mult), entry + (tp_distance * tp_mult)
    
    def get_stats(self) -> Dict:
        """Get learning statistics"""
        s = self.stats
        return {
            'total_signals': s.total_signals,
            'win_rate': f"{s.win_rate:.1%}",
            'expectancy': f"{s.expectancy:.2f}%",
            'profit_factor': f"{s.profit_factor:.2f}",
            'optimal_rsi': s.best_rsi_range,
            'optimal_volume': s.best_volume_ratio,
            'optimal_min_score': s.optimal_min_score,
            'adjustments': self.adjustments,
            'pending_signals': len(self.pending_signals)
        }
    
    def get_feature_report(self) -> str:
        """Get feature report"""
        s = self.stats
        a = self.adjustments
        return f"""
🧠 <b>SELF-LEARNING REPORT</b>

📊 <b>Overall Stats:</b>
├ Total Signals: {s.total_signals}
├ Win Rate: {s.win_rate:.1%}
├ Profit Factor: {s.profit_factor:.2f}
└ Expectancy: {s.expectancy:.2f}%

🎯 <b>Optimal Parameters:</b>
├ RSI Range: {s.best_rsi_range}
├ Volume Ratio: >{s.best_volume_ratio:.1f}x
└ Min Score: {s.optimal_min_score}

⚙️ <b>Active Adjustments:</b>
├ SL Multiplier: {a.get('sl_adjustment', 1.0):.2f}x
├ TP Multiplier: {a.get('tp_adjustment', 1.0):.2f}x
└ Skip Low RSI: <{a.get('skip_low_rsi', 70)}
"""

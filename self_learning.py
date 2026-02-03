"""
MEXC Pump Monitor - Self-Learning Engine
Обучение на собственных сигналах для улучшения точности
"""

import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TradeOutcome:
    """Результат сделки для обучения"""
    signal_id: str
    symbol: str
    timestamp: int
    
    # Signal parameters
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    signal_score: int
    signal_quality: str
    
    # Features at signal time
    rsi: float
    volume_ratio: float
    price_change_pct: float
    ema_extension_pct: float
    whale_pressure: int
    funding_rate: float
    
    # Outcome
    outcome: str  # 'tp1', 'tp2', 'sl', 'breakeven', 'timeout'
    exit_price: float = 0
    profit_pct: float = 0
    duration_minutes: int = 0
    
    # Calculated after outcome
    is_win: bool = False
    
    def __post_init__(self):
        if self.exit_price > 0 and self.entry_price > 0:
            self.profit_pct = ((self.entry_price - self.exit_price) / self.entry_price) * 100
            self.is_win = self.profit_pct > 0


@dataclass
class LearningStats:
    """Статистика обучения"""
    total_signals: int = 0
    total_wins: int = 0
    total_losses: int = 0
    win_rate: float = 0
    avg_profit_pct: float = 0
    avg_loss_pct: float = 0
    expectancy: float = 0
    profit_factor: float = 0
    
    # By feature ranges
    best_rsi_range: Tuple[float, float] = (80, 95)
    best_volume_ratio: float = 5.0
    best_extension_range: Tuple[float, float] = (7, 15)
    
    # Optimal parameters
    optimal_min_score: int = 70
    optimal_sl_multiplier: float = 1.0
    optimal_tp_multiplier: float = 1.0


class SelfLearningEngine:
    """
    🧠 Self-Learning Engine
    
    Обучается на результатах сигналов:
    - Анализирует win rate по различным параметрам
    - Находит оптимальные диапазоны RSI, Volume, Extension
    - Корректирует пороги сигналов
    - Улучшает SL/TP уровни
    """
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or "./learning_data")
        self.data_dir.mkdir(exist_ok=True)
        
        # Trade outcomes history
        self.outcomes: List[TradeOutcome] = []
        self.max_outcomes = 5000
        
        # Learning stats
        self.stats = LearningStats()
        
        # Feature analysis
        self.feature_analysis: Dict[str, Dict] = {}
        
        # Learned adjustments
        self.adjustments = {
            'min_score_threshold': 65,
            'rsi_weight': 1.0,
            'volume_weight': 1.0,
            'extension_weight': 1.0,
            'sl_adjustment': 1.0,  # Multiplier for SL distance
            'tp_adjustment': 1.0,  # Multiplier for TP distance
            'skip_low_rsi': 70,
            'skip_low_volume': 2.0,
        }
        
        # Signal tracking for outcome matching
        self.pending_signals: Dict[str, dict] = {}
        
        # Load historical data
        self._load_data()
    
    def _load_data(self):
        """Загрузить исторические данные"""
        outcomes_file = self.data_dir / "outcomes.json"
        adjustments_file = self.data_dir / "adjustments.json"
        
        try:
            if outcomes_file.exists():
                with open(outcomes_file, 'r') as f:
                    data = json.load(f)
                    self.outcomes = [TradeOutcome(**o) for o in data]
                logger.info(f"Loaded {len(self.outcomes)} historical outcomes")
        except Exception as e:
            logger.error(f"Failed to load outcomes: {e}")
        
        try:
            if adjustments_file.exists():
                with open(adjustments_file, 'r') as f:
                    self.adjustments = json.load(f)
                logger.info(f"Loaded learned adjustments")
        except Exception as e:
            logger.error(f"Failed to load adjustments: {e}")
    
    def _save_data(self):
        """Сохранить данные"""
        try:
            outcomes_file = self.data_dir / "outcomes.json"
            with open(outcomes_file, 'w') as f:
                json.dump([asdict(o) for o in self.outcomes], f, indent=2)
            
            adjustments_file = self.data_dir / "adjustments.json"
            with open(adjustments_file, 'w') as f:
                json.dump(self.adjustments, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save learning data: {e}")
    
    def track_signal(self, signal: dict) -> str:
        """
        Начать отслеживание сигнала
        
        Returns:
            signal_id для последующего matching
        """
        signal_id = f"{signal.get('symbol')}_{int(time.time()*1000)}"
        
        self.pending_signals[signal_id] = {
            'signal': signal,
            'timestamp': int(time.time() * 1000),
            'status': 'pending'
        }
        
        # Cleanup old pending signals (>24h)
        cutoff = int(time.time() * 1000) - (24 * 60 * 60 * 1000)
        self.pending_signals = {
            k: v for k, v in self.pending_signals.items()
            if v['timestamp'] > cutoff
        }
        
        return signal_id
    
    def record_outcome(
        self,
        signal_id: str,
        outcome: str,  # 'tp1', 'tp2', 'sl', 'breakeven', 'timeout'
        exit_price: float
    ):
        """
        Записать результат сделки
        """
        if signal_id not in self.pending_signals:
            logger.warning(f"Unknown signal_id: {signal_id}")
            return
        
        pending = self.pending_signals.pop(signal_id)
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
        
        logger.info(f"Recorded outcome: {signal_id} -> {outcome} ({trade_outcome.profit_pct:.2f}%)")
        
        # Relearn if we have enough new data
        if len(self.outcomes) % 10 == 0:
            asyncio.create_task(self._relearn())
    
    async def _relearn(self):
        """Переобучение на новых данных"""
        if len(self.outcomes) < 20:
            return
        
        logger.info("🧠 Starting self-learning analysis...")
        
        try:
            # Calculate overall stats
            self._calculate_stats()
            
            # Analyze features
            self._analyze_features()
            
            # Update adjustments
            self._update_adjustments()
            
            # Save data
            self._save_data()
            
            logger.info(f"Learning complete. Win rate: {self.stats.win_rate:.1%}")
            
        except Exception as e:
            logger.error(f"Learning error: {e}")
    
    def _calculate_stats(self):
        """Рассчитать общую статистику"""
        if not self.outcomes:
            return
        
        wins = [o for o in self.outcomes if o.is_win]
        losses = [o for o in self.outcomes if not o.is_win]
        
        self.stats.total_signals = len(self.outcomes)
        self.stats.total_wins = len(wins)
        self.stats.total_losses = len(losses)
        
        if self.stats.total_signals > 0:
            self.stats.win_rate = self.stats.total_wins / self.stats.total_signals
        
        if wins:
            self.stats.avg_profit_pct = sum(o.profit_pct for o in wins) / len(wins)
        
        if losses:
            self.stats.avg_loss_pct = sum(abs(o.profit_pct) for o in losses) / len(losses)
        
        # Expectancy = (Win% * Avg Win) - (Loss% * Avg Loss)
        if self.stats.total_signals > 0:
            self.stats.expectancy = (
                (self.stats.win_rate * self.stats.avg_profit_pct) -
                ((1 - self.stats.win_rate) * self.stats.avg_loss_pct)
            )
        
        # Profit factor = Gross Profit / Gross Loss
        gross_profit = sum(o.profit_pct for o in wins) if wins else 0
        gross_loss = sum(abs(o.profit_pct) for o in losses) if losses else 1
        self.stats.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
    
    def _analyze_features(self):
        """Анализ эффективности по фичам"""
        if len(self.outcomes) < 20:
            return
        
        # RSI analysis
        rsi_buckets = defaultdict(list)
        for o in self.outcomes:
            bucket = int(o.rsi // 5) * 5  # Group by 5
            rsi_buckets[bucket].append(o)
        
        best_rsi_wr = 0
        best_rsi_bucket = 80
        for bucket, outcomes in rsi_buckets.items():
            if len(outcomes) >= 3:
                wr = sum(1 for o in outcomes if o.is_win) / len(outcomes)
                if wr > best_rsi_wr:
                    best_rsi_wr = wr
                    best_rsi_bucket = bucket
        
        self.stats.best_rsi_range = (best_rsi_bucket, best_rsi_bucket + 10)
        
        # Volume ratio analysis
        vol_buckets = defaultdict(list)
        for o in self.outcomes:
            bucket = int(o.volume_ratio)  # Group by 1x
            vol_buckets[bucket].append(o)
        
        best_vol_wr = 0
        best_vol = 5
        for bucket, outcomes in vol_buckets.items():
            if len(outcomes) >= 3:
                wr = sum(1 for o in outcomes if o.is_win) / len(outcomes)
                if wr > best_vol_wr:
                    best_vol_wr = wr
                    best_vol = bucket
        
        self.stats.best_volume_ratio = max(2.0, float(best_vol))
        
        # Score analysis
        score_buckets = defaultdict(list)
        for o in self.outcomes:
            bucket = int(o.signal_score // 10) * 10
            score_buckets[bucket].append(o)
        
        # Find minimum profitable score
        for score in sorted(score_buckets.keys()):
            outcomes = score_buckets[score]
            if len(outcomes) >= 3:
                wr = sum(1 for o in outcomes if o.is_win) / len(outcomes)
                if wr >= 0.5:
                    self.stats.optimal_min_score = score
                    break
        
        self.feature_analysis = {
            'rsi_buckets': {k: len(v) for k, v in rsi_buckets.items()},
            'volume_buckets': {k: len(v) for k, v in vol_buckets.items()},
            'score_buckets': {k: len(v) for k, v in score_buckets.items()},
            'best_rsi': best_rsi_bucket,
            'best_volume': best_vol,
            'best_score': self.stats.optimal_min_score
        }
    
    def _update_adjustments(self):
        """Обновить корректировки на основе анализа"""
        if self.stats.total_signals < 20:
            return
        
        # Adjust minimum score threshold
        self.adjustments['min_score_threshold'] = self.stats.optimal_min_score
        
        # Adjust skip thresholds based on best ranges
        self.adjustments['skip_low_rsi'] = self.stats.best_rsi_range[0]
        self.adjustments['skip_low_volume'] = max(2.0, self.stats.best_volume_ratio * 0.8)
        
        # Adjust SL/TP based on win rate
        if self.stats.win_rate < 0.4:
            # Tighten SL
            self.adjustments['sl_adjustment'] = max(0.7, self.adjustments['sl_adjustment'] - 0.05)
        elif self.stats.win_rate > 0.6:
            # Can widen SL slightly
            self.adjustments['sl_adjustment'] = min(1.2, self.adjustments['sl_adjustment'] + 0.02)
        
        # Adjust feature weights based on correlation with wins
        # This is simplified - real implementation would use correlation analysis
        if self.stats.best_rsi_range[0] >= 85:
            self.adjustments['rsi_weight'] = 1.2
        
        if self.stats.best_volume_ratio >= 7:
            self.adjustments['volume_weight'] = 1.2
        
        logger.info(f"Updated adjustments: {self.adjustments}")
    
    def should_take_signal(self, signal: dict) -> Tuple[bool, str]:
        """
        Проверить, стоит ли брать сигнал на основе обучения
        
        Returns:
            (should_take, reason)
        """
        score = signal.get('final_score', signal.get('score', 0))
        rsi = signal.get('rsi', 50)
        volume_ratio = signal.get('volume_ratio', 1)
        
        # Check minimum score
        if score < self.adjustments['min_score_threshold']:
            return False, f"Score {score} below threshold {self.adjustments['min_score_threshold']}"
        
        # Check RSI
        if rsi < self.adjustments['skip_low_rsi']:
            return False, f"RSI {rsi} below optimal range"
        
        # Check volume
        if volume_ratio < self.adjustments['skip_low_volume']:
            return False, f"Volume ratio {volume_ratio} below threshold"
        
        return True, "Signal passes all learned filters"
    
    def adjust_levels(
        self,
        entry: float,
        stop_loss: float,
        take_profit: float,
        is_short: bool = True
    ) -> Tuple[float, float]:
        """
        Скорректировать SL/TP на основе обучения
        
        Returns:
            (adjusted_sl, adjusted_tp)
        """
        sl_mult = self.adjustments.get('sl_adjustment', 1.0)
        tp_mult = self.adjustments.get('tp_adjustment', 1.0)
        
        if is_short:
            sl_distance = stop_loss - entry
            tp_distance = entry - take_profit
            
            adj_sl = entry + (sl_distance * sl_mult)
            adj_tp = entry - (tp_distance * tp_mult)
        else:
            sl_distance = entry - stop_loss
            tp_distance = take_profit - entry
            
            adj_sl = entry - (sl_distance * sl_mult)
            adj_tp = entry + (tp_distance * tp_mult)
        
        return adj_sl, adj_tp
    
    def get_stats(self) -> Dict:
        """Получить статистику обучения"""
        return {
            'total_signals': self.stats.total_signals,
            'win_rate': f"{self.stats.win_rate:.1%}",
            'expectancy': f"{self.stats.expectancy:.2f}%",
            'profit_factor': f"{self.stats.profit_factor:.2f}",
            'avg_profit': f"{self.stats.avg_profit_pct:.2f}%",
            'avg_loss': f"{self.stats.avg_loss_pct:.2f}%",
            'optimal_rsi': self.stats.best_rsi_range,
            'optimal_volume': self.stats.best_volume_ratio,
            'optimal_min_score': self.stats.optimal_min_score,
            'adjustments': self.adjustments,
            'pending_signals': len(self.pending_signals)
        }
    
    def get_feature_report(self) -> str:
        """Получить отчёт по фичам"""
        return f"""
🧠 <b>SELF-LEARNING REPORT</b>

📊 <b>Overall Stats:</b>
├ Total Signals: {self.stats.total_signals}
├ Win Rate: {self.stats.win_rate:.1%}
├ Profit Factor: {self.stats.profit_factor:.2f}
└ Expectancy: {self.stats.expectancy:.2f}%

🎯 <b>Optimal Parameters:</b>
├ RSI Range: {self.stats.best_rsi_range}
├ Volume Ratio: >{self.stats.best_volume_ratio:.1f}x
└ Min Score: {self.stats.optimal_min_score}

⚙️ <b>Active Adjustments:</b>
├ SL Multiplier: {self.adjustments.get('sl_adjustment', 1.0):.2f}x
├ TP Multiplier: {self.adjustments.get('tp_adjustment', 1.0):.2f}x
└ Skip Low RSI: <{self.adjustments.get('skip_low_rsi', 70)}
"""

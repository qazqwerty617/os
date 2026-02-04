"""
MEXC Pump Monitor - Market Regime Detector
Optimized market condition identification
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime types"""
    STRONG_BULL = "STRONG_BULL"
    BULL = "BULL"
    WEAK_BULL = "WEAK_BULL"
    RANGING = "RANGING"
    WEAK_BEAR = "WEAK_BEAR"
    BEAR = "BEAR"
    STRONG_BEAR = "STRONG_BEAR"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    CRASH = "CRASH"


class VolatilityLevel(Enum):
    """Volatility levels"""
    VERY_LOW = "VERY_LOW"
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


# Volatility thresholds
VOLATILITY_THRESHOLDS = [
    (80, VolatilityLevel.EXTREME),
    (60, VolatilityLevel.HIGH),
    (30, VolatilityLevel.NORMAL),
    (15, VolatilityLevel.LOW),
    (0, VolatilityLevel.VERY_LOW),
]

# Strategy recommendations
REGIME_STRATEGIES = {
    MarketRegime.STRONG_BULL: ("LONG_BIAS", False),
    MarketRegime.BULL: ("LONG_BIAS", False),
    MarketRegime.WEAK_BULL: ("NEUTRAL", False),
    MarketRegime.RANGING: ("RANGE_TRADE", False),
    MarketRegime.WEAK_BEAR: ("NEUTRAL", False),
    MarketRegime.BEAR: ("SHORT_BIAS", False),
    MarketRegime.STRONG_BEAR: ("SHORT_BIAS", False),
    MarketRegime.HIGH_VOLATILITY: ("REDUCE_SIZE", True),
    MarketRegime.CRASH: ("NO_TRADE", True)
}

# Favorable regimes for shorts
SHORT_FAVORABLE_REGIMES = {
    MarketRegime.BEAR,
    MarketRegime.STRONG_BEAR,
    MarketRegime.WEAK_BEAR,
    MarketRegime.HIGH_VOLATILITY
}


@dataclass
class RegimeAnalysis:
    """Complete regime analysis"""
    timestamp: int
    regime: MarketRegime
    regime_strength: int
    
    btc_trend: str
    btc_trend_strength: float
    alt_trend: str
    alt_trend_strength: float
    
    volatility: VolatilityLevel
    volatility_index: float
    
    advancing_pct: float
    declining_pct: float
    new_highs: int
    new_lows: int
    
    volume_trend: str
    btc_dominance_trend: str
    alt_season_index: float
    
    risk_level: str
    recommended_strategy: str
    avoid_trading: bool
    
    def to_dict(self) -> Dict:
        return {
            'regime': self.regime.value,
            'regime_strength': self.regime_strength,
            'btc_trend': self.btc_trend,
            'volatility': self.volatility.value,
            'volatility_index': self.volatility_index,
            'advancing_pct': self.advancing_pct,
            'alt_season_index': self.alt_season_index,
            'risk_level': self.risk_level,
            'recommended_strategy': self.recommended_strategy,
            'avoid_trading': self.avoid_trading
        }


class MarketRegimeDetector:
    """Optimized market regime detector"""
    
    def __init__(self):
        self.btc_prices: deque = deque(maxlen=500)
        self.eth_prices: deque = deque(maxlen=500)
        self.symbol_changes: Dict[str, float] = {}
        self.volumes: Dict[str, deque] = {}
        self.regime_history: deque = deque(maxlen=100)
        self.current_analysis: Optional[RegimeAnalysis] = None
        
        self.stats = {
            'analyses_performed': 0,
            'regime_changes': 0
        }
    
    def record_price(self, symbol: str, price: float, volume: float = 0):
        """Record price data"""
        data = {'price': price, 'timestamp': int(time.time() * 1000)}
        
        if symbol == 'BTC_USDT':
            self.btc_prices.append(data)
        elif symbol == 'ETH_USDT':
            self.eth_prices.append(data)
        
        if volume > 0:
            if symbol not in self.volumes:
                self.volumes[symbol] = deque(maxlen=100)
            self.volumes[symbol].append(volume)
    
    def record_change(self, symbol: str, change_pct: float):
        """Record 24h price change"""
        self.symbol_changes[symbol] = change_pct
    
    def analyze(self) -> RegimeAnalysis:
        """Perform full market regime analysis"""
        btc_trend, btc_strength = self._analyze_trend(list(self.btc_prices))
        alt_trend, alt_strength = self._analyze_alt_trend()
        volatility, vol_index = self._analyze_volatility()
        advancing, declining = self._analyze_breadth()
        volume_trend = self._analyze_volume_trend()
        alt_season = self._calculate_alt_season_index()
        
        regime = self._determine_regime(btc_trend, btc_strength, volatility, vol_index, advancing)
        regime_strength = self._calculate_regime_strength(regime, btc_strength, vol_index)
        risk_level = self._assess_risk(regime, volatility, vol_index)
        strategy, avoid = REGIME_STRATEGIES.get(regime, ("NEUTRAL", False))
        
        analysis = RegimeAnalysis(
            timestamp=int(time.time() * 1000),
            regime=regime,
            regime_strength=regime_strength,
            btc_trend=btc_trend,
            btc_trend_strength=btc_strength,
            alt_trend=alt_trend,
            alt_trend_strength=alt_strength,
            volatility=volatility,
            volatility_index=vol_index,
            advancing_pct=advancing,
            declining_pct=declining,
            new_highs=0,
            new_lows=0,
            volume_trend=volume_trend,
            btc_dominance_trend="STABLE",
            alt_season_index=alt_season,
            risk_level=risk_level,
            recommended_strategy=strategy,
            avoid_trading=avoid
        )
        
        if self.current_analysis and self.current_analysis.regime != regime:
            self.stats['regime_changes'] += 1
            logger.info(f"🔄 Regime: {self.current_analysis.regime.value} → {regime.value}")
        
        self.current_analysis = analysis
        self.regime_history.append(analysis)
        self.stats['analyses_performed'] += 1
        
        return analysis
    
    def _analyze_trend(self, prices: List[Dict]) -> Tuple[str, float]:
        """Analyze price trend"""
        if len(prices) < 20:
            return "SIDEWAYS", 0
        
        recent = [p['price'] for p in prices[-10:]]
        older = [p['price'] for p in prices[-30:-10]]
        
        if not older:
            return "SIDEWAYS", 0
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        change_pct = ((recent_avg - older_avg) / older_avg) * 100
        
        if change_pct > 5:
            return "UP", min(100, change_pct * 5)
        elif change_pct < -5:
            return "DOWN", min(100, abs(change_pct) * 5)
        return "SIDEWAYS", abs(change_pct) * 5
    
    def _analyze_alt_trend(self) -> Tuple[str, float]:
        """Analyze altcoin trend"""
        changes = [c for s, c in self.symbol_changes.items() if 'BTC' not in s]
        if not changes:
            return "SIDEWAYS", 0
        
        avg_change = sum(changes) / len(changes)
        
        if avg_change > 3:
            return "UP", min(100, avg_change * 10)
        elif avg_change < -3:
            return "DOWN", min(100, abs(avg_change) * 10)
        return "SIDEWAYS", abs(avg_change) * 10
    
    def _analyze_volatility(self) -> Tuple[VolatilityLevel, float]:
        """Analyze market volatility"""
        if len(self.btc_prices) < 20:
            return VolatilityLevel.NORMAL, 50
        
        prices = [p['price'] for p in list(self.btc_prices)[-50:]]
        returns = [(prices[i] - prices[i-1]) / prices[i-1] * 100 for i in range(1, len(prices))]
        
        if len(returns) <= 1:
            return VolatilityLevel.NORMAL, 50
        
        vol = statistics.stdev(returns)
        vol_index = min(100, vol * 20)
        
        level = VolatilityLevel.NORMAL
        for threshold, lvl in VOLATILITY_THRESHOLDS:
            if vol_index > threshold:
                level = lvl
                break
        
        return level, vol_index
    
    def _analyze_breadth(self) -> Tuple[float, float]:
        """Analyze market breadth"""
        if not self.symbol_changes:
            return 50, 50
        
        advancing = len([c for c in self.symbol_changes.values() if c > 0])
        declining = len([c for c in self.symbol_changes.values() if c < 0])
        total = advancing + declining
        
        if total == 0:
            return 50, 50
        
        return (advancing / total) * 100, (declining / total) * 100
    
    def _analyze_volume_trend(self) -> str:
        """Analyze volume trend"""
        if not self.volumes:
            return "STABLE"
        
        total_recent, total_older = 0, 0
        
        for vols in self.volumes.values():
            vol_list = list(vols)
            if len(vol_list) >= 20:
                total_recent += sum(vol_list[-10:])
                total_older += sum(vol_list[-20:-10])
        
        if total_older == 0:
            return "STABLE"
        
        change = (total_recent - total_older) / total_older * 100
        
        if change > 20:
            return "INCREASING"
        elif change < -20:
            return "DECREASING"
        return "STABLE"
    
    def _calculate_alt_season_index(self) -> float:
        """Calculate alt season index (0-100)"""
        if not self.symbol_changes:
            return 50
        
        btc_change = self.symbol_changes.get('BTC_USDT', 0)
        alt_changes = [c for s, c in self.symbol_changes.items() if 'BTC' not in s]
        
        if not alt_changes:
            return 50
        
        outperformers = len([c for c in alt_changes if c > btc_change])
        return (outperformers / len(alt_changes)) * 100
    
    def _determine_regime(
        self,
        btc_trend: str,
        btc_strength: float,
        volatility: VolatilityLevel,
        vol_index: float,
        advancing_pct: float
    ) -> MarketRegime:
        """Determine market regime"""
        if volatility == VolatilityLevel.EXTREME:
            if btc_trend == "DOWN" and btc_strength > 70:
                return MarketRegime.CRASH
            return MarketRegime.HIGH_VOLATILITY
        
        if btc_trend == "UP":
            if btc_strength > 70 and advancing_pct > 70:
                return MarketRegime.STRONG_BULL
            elif btc_strength > 40:
                return MarketRegime.BULL
            return MarketRegime.WEAK_BULL
        
        if btc_trend == "DOWN":
            if btc_strength > 70 and advancing_pct < 30:
                return MarketRegime.STRONG_BEAR
            elif btc_strength > 40:
                return MarketRegime.BEAR
            return MarketRegime.WEAK_BEAR
        
        return MarketRegime.RANGING
    
    def _calculate_regime_strength(
        self,
        regime: MarketRegime,
        trend_strength: float,
        vol_index: float
    ) -> int:
        """Calculate regime strength (0-100)"""
        strong_regimes = {MarketRegime.STRONG_BULL, MarketRegime.STRONG_BEAR, MarketRegime.CRASH}
        normal_regimes = {MarketRegime.BULL, MarketRegime.BEAR}
        
        if regime in strong_regimes:
            return min(100, int(trend_strength * 1.2))
        elif regime in normal_regimes:
            return int(trend_strength)
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return int(vol_index)
        return max(0, 50 - int(trend_strength))
    
    def _assess_risk(
        self,
        regime: MarketRegime,
        volatility: VolatilityLevel,
        vol_index: float
    ) -> str:
        """Assess trading risk"""
        if regime in (MarketRegime.CRASH, MarketRegime.HIGH_VOLATILITY):
            return "EXTREME"
        if volatility in (VolatilityLevel.EXTREME, VolatilityLevel.HIGH):
            return "HIGH"
        if regime in (MarketRegime.STRONG_BEAR, MarketRegime.STRONG_BULL):
            return "MEDIUM"
        if regime == MarketRegime.RANGING:
            return "LOW"
        return "MEDIUM"
    
    def get_regime(self) -> MarketRegime:
        """Get current regime"""
        return self.current_analysis.regime if self.current_analysis else MarketRegime.RANGING
    
    def is_favorable_for_shorts(self) -> bool:
        """Check if conditions favor short trades"""
        if not self.current_analysis:
            return True
        return self.current_analysis.regime in SHORT_FAVORABLE_REGIMES
    
    def get_regime_summary(self) -> str:
        """Get regime summary"""
        if not self.current_analysis:
            return "Unknown"
        
        a = self.current_analysis
        return f"""
Market Regime: {a.regime.value}
Strength: {a.regime_strength}/100
Volatility: {a.volatility.value} ({a.volatility_index:.1f})
Advancing: {a.advancing_pct:.1f}%
Alt Season: {a.alt_season_index:.1f}
Risk: {a.risk_level}
Strategy: {a.recommended_strategy}
"""

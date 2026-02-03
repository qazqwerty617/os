"""
MEXC Pump Monitor - Market Regime Detector
Identifies market conditions: Bull, Bear, Ranging, High Volatility
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
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


@dataclass
class RegimeAnalysis:
    """Complete regime analysis"""
    timestamp: int
    
    # Overall market
    regime: MarketRegime
    regime_strength: int  # 0-100
    
    # Trend
    btc_trend: str  # "UP", "DOWN", "SIDEWAYS"
    btc_trend_strength: float
    alt_trend: str
    alt_trend_strength: float
    
    # Volatility
    volatility: VolatilityLevel
    volatility_index: float
    
    # Breadth
    advancing_pct: float  # % of coins up
    declining_pct: float
    new_highs: int
    new_lows: int
    
    # Volume
    volume_trend: str  # "INCREASING", "DECREASING", "STABLE"
    
    # Correlation
    btc_dominance_trend: str
    alt_season_index: float  # 0-100, >75 = alt season
    
    # Risk
    risk_level: str  # "LOW", "MEDIUM", "HIGH", "EXTREME"
    
    # Recommendations
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
    """
    Detects current market regime using multiple indicators
    """
    
    def __init__(self):
        # Price history
        self.btc_prices: deque = deque(maxlen=500)
        self.eth_prices: deque = deque(maxlen=500)
        
        # Market breadth
        self.symbol_changes: Dict[str, float] = {}
        
        # Volumes
        self.volumes: Dict[str, deque] = {}
        
        # Historical regimes
        self.regime_history: deque = deque(maxlen=100)
        
        # Current analysis
        self.current_analysis: Optional[RegimeAnalysis] = None
        
        # Stats
        self.stats = {
            'analyses_performed': 0,
            'regime_changes': 0
        }
    
    def record_price(self, symbol: str, price: float, volume: float = 0):
        """Record price data"""
        if symbol == 'BTC_USDT':
            self.btc_prices.append({
                'price': price,
                'timestamp': int(time.time() * 1000)
            })
        elif symbol == 'ETH_USDT':
            self.eth_prices.append({
                'price': price,
                'timestamp': int(time.time() * 1000)
            })
        
        if volume > 0:
            if symbol not in self.volumes:
                self.volumes[symbol] = deque(maxlen=100)
            self.volumes[symbol].append(volume)
    
    def record_change(self, symbol: str, change_pct: float):
        """Record 24h price change"""
        self.symbol_changes[symbol] = change_pct
    
    def analyze(self) -> RegimeAnalysis:
        """Perform full market regime analysis"""
        # BTC trend
        btc_trend, btc_strength = self._analyze_trend(list(self.btc_prices))
        
        # Alt trend (using all symbols)
        alt_trend, alt_strength = self._analyze_alt_trend()
        
        # Volatility
        volatility, vol_index = self._analyze_volatility()
        
        # Breadth
        advancing, declining = self._analyze_breadth()
        
        # Volume trend
        volume_trend = self._analyze_volume_trend()
        
        # Alt season index
        alt_season = self._calculate_alt_season_index()
        
        # Determine regime
        regime = self._determine_regime(
            btc_trend, btc_strength,
            volatility, vol_index,
            advancing
        )
        
        # Calculate regime strength
        regime_strength = self._calculate_regime_strength(regime, btc_strength, vol_index)
        
        # Risk assessment
        risk_level = self._assess_risk(regime, volatility, vol_index)
        
        # Recommendations
        strategy, avoid = self._get_recommendations(regime, risk_level)
        
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
            new_highs=0,  # Would need ATH data
            new_lows=0,
            volume_trend=volume_trend,
            btc_dominance_trend="STABLE",  # Would need dominance data
            alt_season_index=alt_season,
            risk_level=risk_level,
            recommended_strategy=strategy,
            avoid_trading=avoid
        )
        
        # Check for regime change
        if self.current_analysis and self.current_analysis.regime != regime:
            self.stats['regime_changes'] += 1
            logger.info(f"🔄 Regime change: {self.current_analysis.regime.value} → {regime.value}")
        
        self.current_analysis = analysis
        self.regime_history.append(analysis)
        self.stats['analyses_performed'] += 1
        
        return analysis
    
    def _analyze_trend(self, prices: List[Dict]) -> Tuple[str, float]:
        """Analyze price trend"""
        if len(prices) < 20:
            return "SIDEWAYS", 0
        
        # Compare recent vs older prices
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
        else:
            return "SIDEWAYS", abs(change_pct) * 5
    
    def _analyze_alt_trend(self) -> Tuple[str, float]:
        """Analyze altcoin trend"""
        if not self.symbol_changes:
            return "SIDEWAYS", 0
        
        changes = [c for s, c in self.symbol_changes.items() if 'BTC' not in s]
        
        if not changes:
            return "SIDEWAYS", 0
        
        avg_change = sum(changes) / len(changes)
        
        if avg_change > 3:
            return "UP", min(100, avg_change * 10)
        elif avg_change < -3:
            return "DOWN", min(100, abs(avg_change) * 10)
        else:
            return "SIDEWAYS", abs(avg_change) * 10
    
    def _analyze_volatility(self) -> Tuple[VolatilityLevel, float]:
        """Analyze market volatility"""
        if len(self.btc_prices) < 20:
            return VolatilityLevel.NORMAL, 50
        
        prices = [p['price'] for p in list(self.btc_prices)[-50:]]
        
        # Calculate returns
        returns = [(prices[i] - prices[i-1]) / prices[i-1] * 100 for i in range(1, len(prices))]
        
        if not returns:
            return VolatilityLevel.NORMAL, 50
        
        # Standard deviation of returns
        vol = statistics.stdev(returns) if len(returns) > 1 else 0
        
        # Convert to index (0-100)
        vol_index = min(100, vol * 20)
        
        if vol_index > 80:
            level = VolatilityLevel.EXTREME
        elif vol_index > 60:
            level = VolatilityLevel.HIGH
        elif vol_index > 30:
            level = VolatilityLevel.NORMAL
        elif vol_index > 15:
            level = VolatilityLevel.LOW
        else:
            level = VolatilityLevel.VERY_LOW
        
        return level, vol_index
    
    def _analyze_breadth(self) -> Tuple[float, float]:
        """Analyze market breadth (advancing vs declining)"""
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
        
        # Aggregate all volumes
        total_recent = 0
        total_older = 0
        
        for symbol, vols in self.volumes.items():
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
        else:
            return "STABLE"
    
    def _calculate_alt_season_index(self) -> float:
        """Calculate alt season index (0-100)"""
        if not self.symbol_changes:
            return 50
        
        # Get BTC performance
        btc_change = self.symbol_changes.get('BTC_USDT', 0)
        
        # Get alt performance
        alt_changes = [c for s, c in self.symbol_changes.items() if 'BTC' not in s]
        
        if not alt_changes:
            return 50
        
        # Count alts outperforming BTC
        outperformers = len([c for c in alt_changes if c > btc_change])
        outperform_pct = outperformers / len(alt_changes) * 100
        
        return outperform_pct
    
    def _determine_regime(
        self,
        btc_trend: str,
        btc_strength: float,
        volatility: VolatilityLevel,
        vol_index: float,
        advancing_pct: float
    ) -> MarketRegime:
        """Determine market regime"""
        # High volatility overrides
        if volatility == VolatilityLevel.EXTREME:
            if btc_trend == "DOWN" and btc_strength > 70:
                return MarketRegime.CRASH
            return MarketRegime.HIGH_VOLATILITY
        
        # Bull regimes
        if btc_trend == "UP":
            if btc_strength > 70 and advancing_pct > 70:
                return MarketRegime.STRONG_BULL
            elif btc_strength > 40:
                return MarketRegime.BULL
            else:
                return MarketRegime.WEAK_BULL
        
        # Bear regimes
        elif btc_trend == "DOWN":
            if btc_strength > 70 and advancing_pct < 30:
                return MarketRegime.STRONG_BEAR
            elif btc_strength > 40:
                return MarketRegime.BEAR
            else:
                return MarketRegime.WEAK_BEAR
        
        # Ranging
        return MarketRegime.RANGING
    
    def _calculate_regime_strength(
        self,
        regime: MarketRegime,
        trend_strength: float,
        vol_index: float
    ) -> int:
        """Calculate regime strength (0-100)"""
        if regime in [MarketRegime.STRONG_BULL, MarketRegime.STRONG_BEAR, MarketRegime.CRASH]:
            return min(100, int(trend_strength * 1.2))
        elif regime in [MarketRegime.BULL, MarketRegime.BEAR]:
            return int(trend_strength)
        elif regime == MarketRegime.HIGH_VOLATILITY:
            return int(vol_index)
        else:
            return max(0, 50 - int(trend_strength))
    
    def _assess_risk(
        self,
        regime: MarketRegime,
        volatility: VolatilityLevel,
        vol_index: float
    ) -> str:
        """Assess trading risk"""
        if regime in [MarketRegime.CRASH, MarketRegime.HIGH_VOLATILITY]:
            return "EXTREME"
        
        if volatility in [VolatilityLevel.EXTREME, VolatilityLevel.HIGH]:
            return "HIGH"
        
        if regime in [MarketRegime.STRONG_BEAR, MarketRegime.STRONG_BULL]:
            return "MEDIUM"
        
        if regime == MarketRegime.RANGING:
            return "LOW"
        
        return "MEDIUM"
    
    def _get_recommendations(
        self,
        regime: MarketRegime,
        risk_level: str
    ) -> Tuple[str, bool]:
        """Get trading recommendations"""
        strategies = {
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
        
        return strategies.get(regime, ("NEUTRAL", False))
    
    def get_regime(self) -> MarketRegime:
        """Get current regime"""
        if self.current_analysis:
            return self.current_analysis.regime
        return MarketRegime.RANGING
    
    def is_favorable_for_shorts(self) -> bool:
        """Check if conditions favor short trades"""
        if not self.current_analysis:
            return True
        
        favorable = [
            MarketRegime.BEAR,
            MarketRegime.STRONG_BEAR,
            MarketRegime.WEAK_BEAR,
            MarketRegime.HIGH_VOLATILITY
        ]
        
        return self.current_analysis.regime in favorable
    
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

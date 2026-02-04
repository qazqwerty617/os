"""
MEXC Pump Monitor - Liquidity Analyzer
Анализ ликвидности перед входом в мемкоины
"""

import time
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LiquidityReport:
    """Отчет о ликвидности"""
    symbol: str
    timestamp: int
    
    # Orderbook данные
    bid_liquidity_usd: float  # Ликвидность на покупку
    ask_liquidity_usd: float  # Ликвидность на продажу
    spread_pct: float  # Спред в %
    
    # Глубина стакана
    depth_5pct_bid: float  # Глубина 5% на бидах
    depth_5pct_ask: float  # Глубина 5% на асках
    
    # Оценка
    liquidity_score: int  # 0-100
    risk_level: str  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
    can_enter: bool
    recommended_size_pct: float  # Рекомендуемый размер позиции в %
    warnings: List[str]
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'bid_liquidity': self.bid_liquidity_usd,
            'ask_liquidity': self.ask_liquidity_usd,
            'spread': self.spread_pct,
            'liquidity_score': self.liquidity_score,
            'risk_level': self.risk_level,
            'can_enter': self.can_enter,
            'recommended_size': self.recommended_size_pct,
            'warnings': self.warnings
        }


class LiquidityAnalyzer:
    """
    Анализатор ликвидности для мемкоинов
    Проверяет возможность безопасного входа/выхода
    """
    
    def __init__(self):
        # Пороги для оценки
        self.min_liquidity_usd = 10_000  # Минимум $10K ликвидности
        self.max_spread_pct = 2.0  # Максимальный спред 2%
        self.min_depth_5pct = 5_000  # Минимум $5K на глубине 5%
        
        # Кэш для orderbook данных
        self.orderbook_cache: Dict[str, dict] = {}
        self.cache_ttl = 2.0  # 2 секунды
        
        self.stats = {
            'analyses_performed': 0,
            'low_liquidity_warnings': 0,
            'high_spread_warnings': 0
        }
    
    async def analyze_liquidity(
        self,
        symbol: str,
        client=None,
        target_size_usd: float = 1000
    ) -> Optional[LiquidityReport]:
        """
        Проанализировать ликвидность для символа
        
        Args:
            symbol: Торговая пара
            client: MEXC клиент (опционально)
            target_size_usd: Целевой размер позиции
        
        Returns:
            LiquidityReport или None
        """
        # Попытка получить orderbook (если доступен)
        orderbook = await self._get_orderbook(symbol, client)
        
        if not orderbook:
            # Если orderbook недоступен, используем оценку на основе объема
            return self._estimate_liquidity(symbol, target_size_usd)
        
        # Анализ реального orderbook
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return self._estimate_liquidity(symbol, target_size_usd)
        
        # Рассчитать ликвидность
        bid_liquidity = sum(price * qty for price, qty in bids[:20])  # Топ 20 уровней
        ask_liquidity = sum(price * qty for price, qty in asks[:20])
        
        # Спред
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        mid_price = (best_bid + best_ask) / 2
        spread_pct = ((best_ask - best_bid) / mid_price * 100) if mid_price > 0 else 0
        
        # Глубина 5%
        depth_5pct_bid = self._calculate_depth(bids, mid_price * 0.95)
        depth_5pct_ask = self._calculate_depth(asks, mid_price * 1.05)
        
        # Оценка
        score = self._calculate_score(bid_liquidity, ask_liquidity, spread_pct, depth_5pct_bid, depth_5pct_ask)
        risk_level = self._determine_risk(score, spread_pct, bid_liquidity, ask_liquidity)
        can_enter = score >= 50 and spread_pct < self.max_spread_pct
        
        # Рекомендуемый размер позиции (меньше при низкой ликвидности)
        if score >= 80:
            recommended_size = 1.0  # 100% от целевого
        elif score >= 60:
            recommended_size = 0.7  # 70%
        elif score >= 40:
            recommended_size = 0.5  # 50%
        else:
            recommended_size = 0.3  # 30%
        
        # Предупреждения
        warnings = []
        if bid_liquidity < self.min_liquidity_usd:
            warnings.append(f"Low bid liquidity: ${bid_liquidity:,.0f}")
            self.stats['low_liquidity_warnings'] += 1
        if ask_liquidity < self.min_liquidity_usd:
            warnings.append(f"Low ask liquidity: ${ask_liquidity:,.0f}")
        if spread_pct > self.max_spread_pct:
            warnings.append(f"High spread: {spread_pct:.2f}%")
            self.stats['high_spread_warnings'] += 1
        if depth_5pct_bid < self.min_depth_5pct:
            warnings.append(f"Shallow orderbook depth")
        
        report = LiquidityReport(
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bid_liquidity_usd=bid_liquidity,
            ask_liquidity_usd=ask_liquidity,
            spread_pct=spread_pct,
            depth_5pct_bid=depth_5pct_bid,
            depth_5pct_ask=depth_5pct_ask,
            liquidity_score=score,
            risk_level=risk_level,
            can_enter=can_enter,
            recommended_size_pct=recommended_size,
            warnings=warnings
        )
        
        self.stats['analyses_performed'] += 1
        return report
    
    def _calculate_depth(self, orders: List, target_price: float) -> float:
        """Рассчитать глубину до целевой цены"""
        depth = 0.0
        for price, qty in orders:
            if (target_price > 0 and price <= target_price) or (target_price < 0 and price >= abs(target_price)):
                depth += price * qty
            else:
                break
        return depth
    
    def _calculate_score(
        self,
        bid_liquidity: float,
        ask_liquidity: float,
        spread_pct: float,
        depth_bid: float,
        depth_ask: float
    ) -> int:
        """Рассчитать score ликвидности 0-100"""
        score = 0
        
        # Ликвидность на бидах (40%)
        if bid_liquidity >= 100_000:
            score += 40
        elif bid_liquidity >= 50_000:
            score += 30
        elif bid_liquidity >= 20_000:
            score += 20
        elif bid_liquidity >= 10_000:
            score += 10
        
        # Ликвидность на асках (30%)
        if ask_liquidity >= 100_000:
            score += 30
        elif ask_liquidity >= 50_000:
            score += 22
        elif ask_liquidity >= 20_000:
            score += 15
        elif ask_liquidity >= 10_000:
            score += 8
        
        # Спред (20%)
        if spread_pct < 0.5:
            score += 20
        elif spread_pct < 1.0:
            score += 15
        elif spread_pct < 2.0:
            score += 10
        elif spread_pct < 3.0:
            score += 5
        
        # Глубина (10%)
        avg_depth = (depth_bid + depth_ask) / 2
        if avg_depth >= 20_000:
            score += 10
        elif avg_depth >= 10_000:
            score += 7
        elif avg_depth >= 5_000:
            score += 5
        
        return min(100, score)
    
    def _determine_risk(
        self,
        score: int,
        spread_pct: float,
        bid_liquidity: float,
        ask_liquidity: float
    ) -> str:
        """Определить уровень риска"""
        if score >= 80 and spread_pct < 1.0:
            return 'LOW'
        elif score >= 60 and spread_pct < 2.0:
            return 'MEDIUM'
        elif score >= 40:
            return 'HIGH'
        else:
            return 'CRITICAL'
    
    def _estimate_liquidity(self, symbol: str, target_size: float) -> LiquidityReport:
        """Оценка ликвидности без orderbook (на основе объема)"""
        # Консервативная оценка
        return LiquidityReport(
            symbol=symbol,
            timestamp=int(time.time() * 1000),
            bid_liquidity_usd=target_size * 2,  # Оценка
            ask_liquidity_usd=target_size * 2,
            spread_pct=1.0,  # Предполагаемый спред
            depth_5pct_bid=target_size,
            depth_5pct_ask=target_size,
            liquidity_score=60,  # Средний score
            risk_level='MEDIUM',
            can_enter=True,
            recommended_size_pct=0.7,
            warnings=["Liquidity estimated - orderbook not available"]
        )
    
    async def _get_orderbook(self, symbol: str, client) -> Optional[Dict]:
        """Получить orderbook (если доступен)"""
        if not client:
            return None
        
        try:
            # Попытка получить orderbook через клиент
            if hasattr(client, 'get_orderbook'):
                orderbook = await client.get_orderbook(symbol, depth=20)
                return orderbook
        except Exception as e:
            logger.debug(f"Orderbook fetch failed for {symbol}: {e}")
        
        return None
    
    def get_stats(self) -> Dict:
        """Статистика"""
        return self.stats

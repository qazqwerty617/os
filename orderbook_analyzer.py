"""
MEXC Pump Monitor - Order Book Analyzer
Анализ плотности ордеров для умных уровней
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    """Уровень в order book"""
    price: float
    quantity: float
    side: str  # 'bid' or 'ask'
    liquidity_usd: float  # Ликвидность в USD


@dataclass
class LiquidityCluster:
    """Кластер ликвидности (скопление ордеров)"""
    price_low: float
    price_high: float
    total_liquidity: float
    order_count: int
    is_support: bool  # True если поддержка (биды), False если сопротивление (аски)
    strength: float  # 0-100


class OrderBookAnalyzer:
    """
    Анализатор order book для определения уровней ликвидности
    Используется для умных стопов и тейков
    """
    
    def __init__(self):
        self.orderbook_cache: Dict[str, Dict] = {}
        self.cache_ttl = 2.0  # 2 секунды
        
    async def get_orderbook(self, symbol: str, client, depth: int = 20) -> Optional[Dict]:
        """
        Получить order book
        
        Args:
            symbol: Торговая пара
            client: MEXC клиент
            depth: Глубина стакана
        
        Returns:
            {'bids': [(price, qty), ...], 'asks': [(price, qty), ...]}
        """
        # Проверить кэш
        cached = self.orderbook_cache.get(symbol)
        if cached and (time.time() - cached.get('timestamp', 0)) < self.cache_ttl:
            return cached.get('data')
        
        # Запросить order book
        try:
            if hasattr(client, 'get_orderbook'):
                orderbook = await client.get_orderbook(symbol, depth=depth)
                if orderbook:
                    self.orderbook_cache[symbol] = {
                        'data': orderbook,
                        'timestamp': time.time()
                    }
                    return orderbook
        except Exception as e:
            logger.debug(f"Orderbook fetch failed for {symbol}: {e}")
        
        return None
    
    def find_liquidity_clusters(
        self,
        orderbook: Dict,
        current_price: float,
        cluster_size_pct: float = 0.5  # Размер кластера в %
    ) -> List[LiquidityCluster]:
        """
        Найти кластеры ликвидности в order book
        
        Args:
            orderbook: {'bids': [(price, qty), ...], 'asks': [(price, qty), ...]}
            current_price: Текущая цена
            cluster_size_pct: Размер кластера для группировки
        
        Returns:
            Список кластеров ликвидности
        """
        clusters = []
        
        if not orderbook:
            return clusters
        
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        # Анализ бидов (поддержки)
        bid_clusters = self._find_clusters_in_side(bids, current_price, cluster_size_pct, True)
        clusters.extend(bid_clusters)
        
        # Анализ асков (сопротивления)
        ask_clusters = self._find_clusters_in_side(asks, current_price, cluster_size_pct, False)
        clusters.extend(ask_clusters)
        
        # Сортировать по силе
        clusters.sort(key=lambda x: x.strength, reverse=True)
        
        return clusters
    
    def _find_clusters_in_side(
        self,
        orders: List[Tuple[float, float]],
        current_price: float,
        cluster_size_pct: float,
        is_bids: bool
    ) -> List[LiquidityCluster]:
        """Найти кластеры на одной стороне стакана"""
        if not orders:
            return []
        
        clusters = []
        cluster_size = current_price * (cluster_size_pct / 100)
        
        i = 0
        while i < len(orders):
            price, qty = orders[i]
            cluster_start = price
            cluster_end = price
            total_liquidity = price * qty
            order_count = 1
            
            # Группировать близкие ордера
            j = i + 1
            while j < len(orders):
                next_price, next_qty = orders[j]
                
                # Проверить расстояние
                if is_bids:
                    distance = cluster_start - next_price
                else:
                    distance = next_price - cluster_end
                
                if distance <= cluster_size:
                    cluster_end = next_price
                    total_liquidity += next_price * next_qty
                    order_count += 1
                    j += 1
                else:
                    break
            
            # Рассчитать силу кластера
            strength = min(100, (total_liquidity / 10000) * 10)  # Упрощенная формула
            
            if strength >= 30:  # Только значимые кластеры
                clusters.append(LiquidityCluster(
                    price_low=min(cluster_start, cluster_end),
                    price_high=max(cluster_start, cluster_end),
                    total_liquidity=total_liquidity,
                    order_count=order_count,
                    is_support=is_bids,
                    strength=strength
                ))
            
            i = j
        
        return clusters
    
    def get_nearest_liquidity_level(
        self,
        clusters: List[LiquidityCluster],
        target_price: float,
        side: str = 'SHORT'
    ) -> Optional[LiquidityCluster]:
        """
        Найти ближайший уровень ликвидности
        
        Args:
            clusters: Список кластеров
            target_price: Целевая цена
            side: 'SHORT' или 'LONG'
        
        Returns:
            Ближайший кластер
        """
        if not clusters:
            return None
        
        relevant_clusters = []
        
        if side == 'SHORT':
            # Для шорта ищем поддержки ниже (биды)
            for cluster in clusters:
                if cluster.is_support and cluster.price_high < target_price:
                    distance = (target_price - cluster.price_high) / target_price * 100
                    if distance < 10:  # В пределах 10%
                        relevant_clusters.append((cluster, distance))
        else:  # LONG
            # Для лонга ищем сопротивления выше (аски)
            for cluster in clusters:
                if not cluster.is_support and cluster.price_low > target_price:
                    distance = (cluster.price_low - target_price) / target_price * 100
                    if distance < 10:
                        relevant_clusters.append((cluster, distance))
        
        if not relevant_clusters:
            return None
        
        # Выбрать ближайший и самый сильный
        relevant_clusters.sort(key=lambda x: (x[1], -x[0].strength))
        return relevant_clusters[0][0]

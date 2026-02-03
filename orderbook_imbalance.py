"""
MEXC Pump Monitor - Order Book Imbalance Analyzer
Анализ дисбаланса ордербука для определения давления покупателей/продавцов
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class ImbalanceSignal(Enum):
    """Сигналы дисбаланса"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class OrderBookLevel:
    """Уровень ордербука"""
    price: float
    quantity: float
    total_usd: float
    cumulative_usd: float = 0


@dataclass
class OrderBookSnapshot:
    """Снапшот ордербука"""
    symbol: str
    timestamp: int
    
    # Bids and asks
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    
    # Aggregated metrics
    total_bid_volume: float = 0
    total_ask_volume: float = 0
    bid_ask_ratio: float = 1.0
    
    # Imbalance metrics
    imbalance_pct: float = 0  # -100 to +100
    imbalance_signal: ImbalanceSignal = ImbalanceSignal.NEUTRAL
    
    # Walls
    bid_wall_price: float = 0
    bid_wall_size: float = 0
    ask_wall_price: float = 0
    ask_wall_size: float = 0
    
    # Depth
    depth_1pct_bid: float = 0  # Total bid volume within 1%
    depth_1pct_ask: float = 0
    depth_5pct_bid: float = 0
    depth_5pct_ask: float = 0


@dataclass
class ImbalanceAlert:
    """Алерт о дисбалансе"""
    symbol: str
    timestamp: int
    signal: ImbalanceSignal
    imbalance_pct: float
    bid_volume: float
    ask_volume: float
    message: str


class OrderBookImbalance:
    """
    📊 Order Book Imbalance Analyzer
    
    Анализирует:
    - Соотношение bid/ask объёмов
    - Стены покупок/продаж
    - Глубину ордербука
    - Давление на цену
    
    Генерирует сигналы:
    - STRONG_BUY: Сильное давление покупателей
    - STRONG_SELL: Сильное давление продавцов
    """
    
    # Thresholds
    STRONG_IMBALANCE_PCT = 40  # >40% imbalance = strong signal
    MODERATE_IMBALANCE_PCT = 20  # >20% = moderate signal
    WALL_MULTIPLIER = 5  # Wall = X times average level size
    
    def __init__(self, telegram=None, mexc_client=None):
        self.telegram = telegram
        self.client = mexc_client
        
        # Snapshots cache
        self.snapshots: Dict[str, OrderBookSnapshot] = {}
        
        # Historical imbalances
        self.history: Dict[str, List[float]] = defaultdict(list)
        self.max_history = 100
        
        # Alerts
        self.alerts: List[ImbalanceAlert] = []
        self.max_alerts = 200
        
        # Stats
        self.stats = {
            'snapshots_analyzed': 0,
            'alerts_generated': 0,
            'symbols_tracked': 0
        }
        
        self._running = False
    
    async def start(self):
        """Запустить анализатор"""
        self._running = True
        asyncio.create_task(self._monitor_loop())
        logger.info("📊 Order Book Imbalance analyzer started")
    
    async def stop(self):
        """Остановить анализатор"""
        self._running = False
    
    async def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self._running:
            try:
                # Analyze tracked symbols periodically
                for symbol in list(self.snapshots.keys()):
                    await self.fetch_and_analyze(symbol)
                    await asyncio.sleep(0.5)  # Rate limit
                
                await asyncio.sleep(30)  # Update every 30s
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Order book monitor error: {e}")
                await asyncio.sleep(10)
    
    async def fetch_and_analyze(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """
        Получить и проанализировать ордербук
        """
        if not self.client:
            return None
        
        try:
            # Fetch order book from MEXC
            depth = await self.client.get_order_book(symbol, limit=50)
            if not depth:
                return None
            
            return self.analyze_orderbook(symbol, depth)
            
        except Exception as e:
            logger.error(f"Failed to fetch order book for {symbol}: {e}")
            return None
    
    def analyze_orderbook(
        self,
        symbol: str,
        depth: dict,
        mid_price: float = None
    ) -> OrderBookSnapshot:
        """
        Анализировать ордербук
        
        Args:
            symbol: Символ
            depth: Данные ордербука {'bids': [[price, qty], ...], 'asks': [...]}
            mid_price: Средняя цена (если None - вычисляется)
        
        Returns:
            OrderBookSnapshot
        """
        timestamp = int(time.time() * 1000)
        
        # Parse bids and asks
        bids = []
        asks = []
        
        for item in depth.get('bids', []):
            price = float(item[0])
            qty = float(item[1])
            bids.append(OrderBookLevel(
                price=price,
                quantity=qty,
                total_usd=price * qty
            ))
        
        for item in depth.get('asks', []):
            price = float(item[0])
            qty = float(item[1])
            asks.append(OrderBookLevel(
                price=price,
                quantity=qty,
                total_usd=price * qty
            ))
        
        if not bids or not asks:
            return OrderBookSnapshot(symbol=symbol, timestamp=timestamp)
        
        # Sort: bids descending, asks ascending
        bids.sort(key=lambda x: x.price, reverse=True)
        asks.sort(key=lambda x: x.price)
        
        # Calculate mid price
        if mid_price is None:
            mid_price = (bids[0].price + asks[0].price) / 2
        
        # Calculate cumulative volumes
        cumulative = 0
        for level in bids:
            cumulative += level.total_usd
            level.cumulative_usd = cumulative
        
        cumulative = 0
        for level in asks:
            cumulative += level.total_usd
            level.cumulative_usd = cumulative
        
        # Total volumes
        total_bid = sum(l.total_usd for l in bids)
        total_ask = sum(l.total_usd for l in asks)
        
        # Bid/Ask ratio
        ratio = total_bid / total_ask if total_ask > 0 else 1
        
        # Imbalance percentage: (bids - asks) / (bids + asks) * 100
        total = total_bid + total_ask
        imbalance_pct = ((total_bid - total_ask) / total * 100) if total > 0 else 0
        
        # Determine signal
        signal = self._determine_signal(imbalance_pct)
        
        # Find walls (unusually large orders)
        avg_bid_size = total_bid / len(bids) if bids else 0
        avg_ask_size = total_ask / len(asks) if asks else 0
        
        bid_wall = max(bids, key=lambda x: x.total_usd) if bids else None
        ask_wall = max(asks, key=lambda x: x.total_usd) if asks else None
        
        bid_wall_price = bid_wall.price if bid_wall and bid_wall.total_usd > avg_bid_size * self.WALL_MULTIPLIER else 0
        bid_wall_size = bid_wall.total_usd if bid_wall_price else 0
        
        ask_wall_price = ask_wall.price if ask_wall and ask_wall.total_usd > avg_ask_size * self.WALL_MULTIPLIER else 0
        ask_wall_size = ask_wall.total_usd if ask_wall_price else 0
        
        # Depth within price ranges
        depth_1pct_bid = sum(
            l.total_usd for l in bids 
            if l.price >= mid_price * 0.99
        )
        depth_1pct_ask = sum(
            l.total_usd for l in asks 
            if l.price <= mid_price * 1.01
        )
        depth_5pct_bid = sum(
            l.total_usd for l in bids 
            if l.price >= mid_price * 0.95
        )
        depth_5pct_ask = sum(
            l.total_usd for l in asks 
            if l.price <= mid_price * 1.05
        )
        
        snapshot = OrderBookSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            bids=bids,
            asks=asks,
            total_bid_volume=total_bid,
            total_ask_volume=total_ask,
            bid_ask_ratio=round(ratio, 3),
            imbalance_pct=round(imbalance_pct, 2),
            imbalance_signal=signal,
            bid_wall_price=bid_wall_price,
            bid_wall_size=bid_wall_size,
            ask_wall_price=ask_wall_price,
            ask_wall_size=ask_wall_size,
            depth_1pct_bid=depth_1pct_bid,
            depth_1pct_ask=depth_1pct_ask,
            depth_5pct_bid=depth_5pct_bid,
            depth_5pct_ask=depth_5pct_ask
        )
        
        # Store snapshot
        self.snapshots[symbol] = snapshot
        self.stats['snapshots_analyzed'] += 1
        self.stats['symbols_tracked'] = len(self.snapshots)
        
        # Store history
        self.history[symbol].append(imbalance_pct)
        if len(self.history[symbol]) > self.max_history:
            self.history[symbol] = self.history[symbol][-self.max_history:]
        
        # Generate alert if strong imbalance
        if abs(imbalance_pct) >= self.STRONG_IMBALANCE_PCT:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._generate_alert(snapshot))
            except RuntimeError:
                pass  # No running loop, skip alert
        
        return snapshot
    
    def _determine_signal(self, imbalance_pct: float) -> ImbalanceSignal:
        """Определить сигнал по дисбалансу"""
        if imbalance_pct >= self.STRONG_IMBALANCE_PCT:
            return ImbalanceSignal.STRONG_BUY
        elif imbalance_pct >= self.MODERATE_IMBALANCE_PCT:
            return ImbalanceSignal.BUY
        elif imbalance_pct <= -self.STRONG_IMBALANCE_PCT:
            return ImbalanceSignal.STRONG_SELL
        elif imbalance_pct <= -self.MODERATE_IMBALANCE_PCT:
            return ImbalanceSignal.SELL
        else:
            return ImbalanceSignal.NEUTRAL
    
    async def _generate_alert(self, snapshot: OrderBookSnapshot):
        """Генерировать алерт"""
        signal = snapshot.imbalance_signal
        
        if signal == ImbalanceSignal.STRONG_BUY:
            emoji = "🟢🟢"
            action = "STRONG BUY PRESSURE"
        elif signal == ImbalanceSignal.STRONG_SELL:
            emoji = "🔴🔴"
            action = "STRONG SELL PRESSURE"
        else:
            return
        
        message = f"""
{emoji} <b>ORDER BOOK IMBALANCE</b>

📊 <b>{snapshot.symbol}</b>
💹 {action}

Imbalance: {snapshot.imbalance_pct:+.1f}%
Bid Volume: ${snapshot.total_bid_volume:,.0f}
Ask Volume: ${snapshot.total_ask_volume:,.0f}
Ratio: {snapshot.bid_ask_ratio:.2f}

{"🧱 Bid Wall: $" + f"{snapshot.bid_wall_size:,.0f} @ ${snapshot.bid_wall_price:.6f}" if snapshot.bid_wall_price else ""}
{"🧱 Ask Wall: $" + f"{snapshot.ask_wall_size:,.0f} @ ${snapshot.ask_wall_price:.6f}" if snapshot.ask_wall_price else ""}
"""
        
        alert = ImbalanceAlert(
            symbol=snapshot.symbol,
            timestamp=snapshot.timestamp,
            signal=signal,
            imbalance_pct=snapshot.imbalance_pct,
            bid_volume=snapshot.total_bid_volume,
            ask_volume=snapshot.total_ask_volume,
            message=message
        )
        
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        self.stats['alerts_generated'] += 1
        
        if self.telegram:
            await self.telegram.send_message(message)
    
    def get_snapshot(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """Получить последний снапшот"""
        return self.snapshots.get(symbol)
    
    def get_imbalance_trend(self, symbol: str) -> Optional[str]:
        """
        Получить тренд дисбаланса
        
        Returns:
            'improving', 'worsening', 'stable', or None
        """
        history = self.history.get(symbol, [])
        if len(history) < 5:
            return None
        
        recent = history[-5:]
        older = history[-10:-5] if len(history) >= 10 else history[:5]
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        
        diff = recent_avg - older_avg
        
        if diff > 5:
            return 'improving'  # More buy pressure
        elif diff < -5:
            return 'worsening'  # More sell pressure
        else:
            return 'stable'
    
    def analyze_for_trading(self, symbol: str) -> Dict:
        """
        Анализ для торгового решения
        
        Returns:
            Dict с рекомендацией
        """
        snapshot = self.snapshots.get(symbol)
        if not snapshot:
            return {
                'recommendation': 'no_data',
                'confidence': 0,
                'reason': 'No order book data'
            }
        
        signal = snapshot.imbalance_signal
        
        # For SHORT signals:
        if signal == ImbalanceSignal.STRONG_SELL:
            return {
                'recommendation': 'confirm_short',
                'confidence': 0.8,
                'reason': f'Strong sell pressure ({snapshot.imbalance_pct:.1f}%)',
                'imbalance': snapshot.imbalance_pct
            }
        elif signal == ImbalanceSignal.STRONG_BUY:
            return {
                'recommendation': 'avoid_short',
                'confidence': 0.7,
                'reason': f'Strong buy pressure ({snapshot.imbalance_pct:.1f}%)',
                'imbalance': snapshot.imbalance_pct
            }
        elif signal == ImbalanceSignal.SELL:
            return {
                'recommendation': 'weak_confirm',
                'confidence': 0.6,
                'reason': 'Moderate sell pressure',
                'imbalance': snapshot.imbalance_pct
            }
        else:
            return {
                'recommendation': 'neutral',
                'confidence': 0.5,
                'reason': 'No significant imbalance',
                'imbalance': snapshot.imbalance_pct
            }
    
    def track_symbol(self, symbol: str):
        """Добавить символ для отслеживания"""
        if symbol not in self.snapshots:
            self.snapshots[symbol] = OrderBookSnapshot(
                symbol=symbol,
                timestamp=int(time.time() * 1000)
            )
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return self.stats

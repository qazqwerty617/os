"""
MEXC Pump Monitor - Whale Wallet Tracker
Отслеживание активности крупных кошельков и smart money
"""

import asyncio
import aiohttp
import ssl
import logging
import time
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class WalletTransaction:
    """Транзакция кошелька"""
    wallet: str
    timestamp: int
    token: str
    action: str  # 'buy', 'sell', 'transfer_in', 'transfer_out'
    amount: float
    value_usd: float
    price: float
    tx_hash: str = ""


@dataclass
class TrackedWallet:
    """Отслеживаемый кошелёк"""
    address: str
    label: str  # "Whale", "Smart Money", "Market Maker", etc.
    chain: str  # "ETH", "BSC", "SOL"
    
    # Statistics
    total_trades: int = 0
    win_rate: float = 0
    avg_profit_pct: float = 0
    total_volume_usd: float = 0
    
    # Recent activity
    last_activity: int = 0
    recent_buys: List[str] = field(default_factory=list)  # Token symbols
    recent_sells: List[str] = field(default_factory=list)
    
    # Tags
    tags: Set[str] = field(default_factory=set)


@dataclass
class WhaleAlert:
    """Алерт об активности кита"""
    wallet: str
    wallet_label: str
    token: str
    action: str
    amount: float
    value_usd: float
    timestamp: int
    importance: str  # 'low', 'medium', 'high', 'critical'
    message: str


class WhaleWalletTracker:
    """
    🐋 Whale Wallet Tracker
    
    Отслеживает:
    - Известные кошельки китов
    - Smart Money движения
    - Крупные переводы
    - Накопление/распределение
    """
    
    # Known whale addresses (examples - add real ones)
    KNOWN_WHALES = {
        # Ethereum
        "0x28C6c06298d514Db089934071355E5743bf21d60": ("Binance Hot Wallet", "exchange"),
        "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549": ("Binance Cold", "exchange"),
        "0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503": ("Binance", "exchange"),
        
        # Smart Money examples
        "0x1234...": ("Smart Money #1", "smart_money"),
        "0x5678...": ("Whale Trader", "whale"),
    }
    
    # Thresholds
    MIN_ALERT_VALUE_USD = 100_000  # Minimum value for alert
    LARGE_TX_VALUE_USD = 500_000
    WHALE_TX_VALUE_USD = 1_000_000
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        
        # Tracked wallets
        self.wallets: Dict[str, TrackedWallet] = {}
        
        # Transaction history
        self.transactions: List[WalletTransaction] = []
        self.max_transactions = 10000
        
        # Token accumulation tracking
        self.token_flows: Dict[str, Dict] = defaultdict(lambda: {
            'buy_volume': 0,
            'sell_volume': 0,
            'net_flow': 0,
            'whale_buys': 0,
            'whale_sells': 0,
            'last_activity': 0
        })
        
        # Alerts
        self.alerts: List[WhaleAlert] = []
        self.max_alerts = 500
        
        # Callbacks
        self._callbacks: List = []
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.stats = {
            'transactions_tracked': 0,
            'alerts_generated': 0,
            'wallets_monitored': 0
        }
        
        self._running = False
    
    async def start(self):
        """Запустить трекер"""
        self._running = True
        
        # Initialize known whales
        for addr, (label, tag) in self.KNOWN_WHALES.items():
            self.wallets[addr.lower()] = TrackedWallet(
                address=addr.lower(),
                label=label,
                chain="ETH",
                tags={tag}
            )
        
        self.stats['wallets_monitored'] = len(self.wallets)
        
        # Start monitoring loop
        asyncio.create_task(self._monitor_loop())
        
        logger.info(f"🐋 Whale Tracker started - monitoring {len(self.wallets)} wallets")
    
    async def stop(self):
        """Остановить трекер"""
        self._running = False
        if self._session:
            await self._session.close()
    
    def on_whale_activity(self, callback):
        """Зарегистрировать callback"""
        self._callbacks.append(callback)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get HTTP session"""
        if self._session is None or self._session.closed:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_ctx)
            )
        return self._session
    
    async def _monitor_loop(self):
        """Основной цикл мониторинга"""
        while self._running:
            try:
                # Check whale activity
                await self._check_whale_transfers()
                
                # Sleep between checks
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Whale monitor error: {e}")
                await asyncio.sleep(30)
    
    async def _check_whale_transfers(self):
        """Проверить последние переводы китов"""
        # This would integrate with blockchain APIs like:
        # - Etherscan API
        # - BSCScan API  
        # - Whale Alert API
        # - Arkham Intelligence
        
        # For now, simulate whale activity detection
        pass
    
    async def track_transaction(
        self,
        wallet: str,
        token: str,
        action: str,
        amount: float,
        value_usd: float,
        price: float,
        tx_hash: str = ""
    ):
        """
        Записать транзакцию кошелька
        
        Args:
            wallet: Адрес кошелька
            token: Символ токена
            action: buy/sell/transfer_in/transfer_out
            amount: Количество токенов
            value_usd: Стоимость в USD
            price: Цена токена
            tx_hash: Hash транзакции
        """
        wallet_lower = wallet.lower()
        timestamp = int(time.time() * 1000)
        
        tx = WalletTransaction(
            wallet=wallet_lower,
            timestamp=timestamp,
            token=token.upper(),
            action=action,
            amount=amount,
            value_usd=value_usd,
            price=price,
            tx_hash=tx_hash
        )
        
        # Store transaction
        self.transactions.append(tx)
        if len(self.transactions) > self.max_transactions:
            self.transactions = self.transactions[-self.max_transactions:]
        
        self.stats['transactions_tracked'] += 1
        
        # Update wallet stats
        if wallet_lower in self.wallets:
            w = self.wallets[wallet_lower]
            w.total_trades += 1
            w.total_volume_usd += value_usd
            w.last_activity = timestamp
            
            if action in ['buy', 'transfer_in']:
                w.recent_buys.append(token)
                if len(w.recent_buys) > 20:
                    w.recent_buys = w.recent_buys[-20:]
            else:
                w.recent_sells.append(token)
                if len(w.recent_sells) > 20:
                    w.recent_sells = w.recent_sells[-20:]
        
        # Update token flows
        flow = self.token_flows[token]
        flow['last_activity'] = timestamp
        
        if action in ['buy', 'transfer_in']:
            flow['buy_volume'] += value_usd
            flow['net_flow'] += value_usd
            if value_usd >= self.LARGE_TX_VALUE_USD:
                flow['whale_buys'] += 1
        else:
            flow['sell_volume'] += value_usd
            flow['net_flow'] -= value_usd
            if value_usd >= self.LARGE_TX_VALUE_USD:
                flow['whale_sells'] += 1
        
        # Generate alert if significant
        if value_usd >= self.MIN_ALERT_VALUE_USD:
            await self._generate_alert(tx)
    
    async def _generate_alert(self, tx: WalletTransaction):
        """Сгенерировать алерт"""
        # Determine importance
        if tx.value_usd >= self.WHALE_TX_VALUE_USD:
            importance = 'critical'
            emoji = '🚨'
        elif tx.value_usd >= self.LARGE_TX_VALUE_USD:
            importance = 'high'
            emoji = '🐋'
        elif tx.value_usd >= 250_000:
            importance = 'medium'
            emoji = '🔔'
        else:
            importance = 'low'
            emoji = '📊'
        
        # Get wallet label
        wallet_info = self.wallets.get(tx.wallet)
        wallet_label = wallet_info.label if wallet_info else "Unknown Whale"
        
        # Create message
        action_emoji = '🟢' if tx.action in ['buy', 'transfer_in'] else '🔴'
        action_text = tx.action.upper()
        
        message = f"""
{emoji} <b>WHALE ALERT</b> {emoji}

{action_emoji} <b>{action_text}</b>: {tx.token}
💰 Amount: ${tx.value_usd:,.0f}
📍 Price: ${tx.price:.6f}
👛 Wallet: {wallet_label}
⏰ Time: {datetime.fromtimestamp(tx.timestamp/1000).strftime('%H:%M:%S')}
"""
        
        alert = WhaleAlert(
            wallet=tx.wallet,
            wallet_label=wallet_label,
            token=tx.token,
            action=tx.action,
            amount=tx.amount,
            value_usd=tx.value_usd,
            timestamp=tx.timestamp,
            importance=importance,
            message=message
        )
        
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        self.stats['alerts_generated'] += 1
        
        # Send Telegram notification for high importance
        if importance in ['high', 'critical'] and self.telegram:
            try:
                await self.telegram.send_message(message)
            except Exception as e:
                logger.error(f"Failed to send whale alert: {e}")
        
        # Notify callbacks
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Whale callback error: {e}")
    
    def add_wallet(
        self,
        address: str,
        label: str,
        chain: str = "ETH",
        tags: Set[str] = None
    ):
        """Добавить кошелёк для отслеживания"""
        addr_lower = address.lower()
        self.wallets[addr_lower] = TrackedWallet(
            address=addr_lower,
            label=label,
            chain=chain,
            tags=tags or set()
        )
        self.stats['wallets_monitored'] = len(self.wallets)
        logger.info(f"Added wallet: {label} ({address[:10]}...)")
    
    def get_token_flows(self, token: str) -> Dict:
        """Получить потоки по токену"""
        return self.token_flows.get(token.upper(), {})
    
    def get_whale_buys(self, limit: int = 20) -> List[str]:
        """Получить токены которые покупают киты"""
        flows = sorted(
            self.token_flows.items(),
            key=lambda x: x[1].get('whale_buys', 0),
            reverse=True
        )
        return [token for token, _ in flows[:limit] if flows]
    
    def get_whale_sells(self, limit: int = 20) -> List[str]:
        """Получить токены которые продают киты"""
        flows = sorted(
            self.token_flows.items(),
            key=lambda x: x[1].get('whale_sells', 0),
            reverse=True
        )
        return [token for token, _ in flows[:limit] if flows]
    
    def get_net_accumulation(self, limit: int = 20) -> List[tuple]:
        """Получить токены с наибольшим чистым накоплением"""
        flows = sorted(
            self.token_flows.items(),
            key=lambda x: x[1].get('net_flow', 0),
            reverse=True
        )
        return [(token, data['net_flow']) for token, data in flows[:limit]]
    
    def get_recent_alerts(self, limit: int = 50) -> List[WhaleAlert]:
        """Получить последние алерты"""
        return self.alerts[-limit:]
    
    def get_wallet_info(self, address: str) -> Optional[TrackedWallet]:
        """Получить информацию о кошельке"""
        return self.wallets.get(address.lower())
    
    def get_stats(self) -> Dict:
        """Получить статистику"""
        return {
            **self.stats,
            'total_alerts': len(self.alerts),
            'tokens_tracked': len(self.token_flows)
        }

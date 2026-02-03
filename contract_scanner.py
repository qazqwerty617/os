"""
MEXC Pump Monitor - Smart Contract Scanner
Проверка токенов на скам/rug pull
"""

import asyncio
import logging
import ssl
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import aiohttp

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Уровень риска токена"""
    SAFE = "🟢 SAFE"
    LOW_RISK = "🟡 LOW RISK"
    MEDIUM_RISK = "🟠 MEDIUM RISK"
    HIGH_RISK = "🔴 HIGH RISK"
    SCAM = "☠️ SCAM"


@dataclass
class ContractAnalysis:
    """Результат анализа контракта"""
    token_address: str
    token_name: str
    token_symbol: str
    chain: str
    
    # Безопасность
    risk_level: RiskLevel = RiskLevel.MEDIUM_RISK
    risk_score: int = 50  # 0-100 (0 = скам, 100 = безопасно)
    
    # Проверки
    is_verified: bool = False
    is_proxy: bool = False
    has_mint_function: bool = False
    has_blacklist: bool = False
    has_pause: bool = False
    has_hidden_owner: bool = False
    can_take_back_ownership: bool = False
    is_honeypot: bool = False
    
    # Налоги
    buy_tax: float = 0
    sell_tax: float = 0
    
    # Ликвидность
    liquidity_locked: bool = False
    liquidity_amount: float = 0
    lp_holders: int = 0
    
    # Владельцы
    owner_balance_pct: float = 0
    top_holders_pct: float = 0
    holders_count: int = 0
    
    # Красные флаги
    red_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Источник данных
    data_source: str = ""


class ContractScanner:
    """
    🔐 Smart Contract Security Scanner
    
    Проверяет токены на:
    - Honeypot (невозможность продать)
    - Высокие налоги
    - Mint функции
    - Blacklist
    - Незаблокированная ликвидность
    - Концентрация у владельцев
    """
    
    def __init__(self, telegram=None):
        self.telegram = telegram
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Кэш проверок
        self.cache: Dict[str, ContractAnalysis] = {}
        self.cache_ttl = 3600  # 1 час
        
        # API endpoints
        self.apis = {
            'goplus': 'https://api.gopluslabs.io/api/v1/token_security',
            'honeypot': 'https://api.honeypot.is/v2/IsHoneypot',
        }
        
    async def start(self):
        """Запуск"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)
        logger.info("🔐 Contract Scanner started")
        
    async def stop(self):
        """Остановка"""
        if self._session:
            await self._session.close()
    
    async def scan_token(
        self, 
        address: str, 
        chain: str = 'eth'
    ) -> ContractAnalysis:
        """
        Полное сканирование токена
        
        Args:
            address: Адрес контракта
            chain: Сеть (eth, bsc, polygon, etc.)
        """
        # Проверка кэша
        cache_key = f"{chain}:{address.lower()}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        analysis = ContractAnalysis(
            token_address=address,
            token_name="Unknown",
            token_symbol="???",
            chain=chain
        )
        
        try:
            # GoPlus Security API
            goplus_data = await self._fetch_goplus(address, chain)
            if goplus_data:
                analysis = self._parse_goplus(analysis, goplus_data)
            
            # Honeypot check
            honeypot_data = await self._check_honeypot(address, chain)
            if honeypot_data:
                analysis = self._parse_honeypot(analysis, honeypot_data)
            
            # Рассчитать итоговый риск
            analysis = self._calculate_risk(analysis)
            
            # Кэшировать
            self.cache[cache_key] = analysis
            
        except Exception as e:
            logger.error(f"Error scanning {address}: {e}")
            analysis.red_flags.append(f"Ошибка сканирования: {e}")
            analysis.risk_level = RiskLevel.HIGH_RISK
        
        return analysis
    
    async def _fetch_goplus(self, address: str, chain: str) -> Optional[dict]:
        """Получить данные от GoPlus Security"""
        try:
            # Маппинг сетей
            chain_map = {
                'eth': '1', 'bsc': '56', 'polygon': '137',
                'arbitrum': '42161', 'avalanche': '43114',
                'fantom': '250', 'optimism': '10', 'base': '8453'
            }
            chain_id = chain_map.get(chain.lower(), '1')
            
            url = f"{self.apis['goplus']}/{chain_id}"
            params = {'contract_addresses': address}
            
            async with self._session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('code') == 1:
                        return data.get('result', {}).get(address.lower(), {})
        except Exception as e:
            logger.debug(f"GoPlus API error: {e}")
        
        return None
    
    async def _check_honeypot(self, address: str, chain: str) -> Optional[dict]:
        """Проверка на honeypot"""
        try:
            # Honeypot.is API
            chain_map = {'eth': 1, 'bsc': 56}
            chain_id = chain_map.get(chain.lower(), 1)
            
            params = {'address': address, 'chainId': chain_id}
            
            async with self._session.get(
                self.apis['honeypot'], 
                params=params
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug(f"Honeypot API error: {e}")
        
        return None
    
    def _parse_goplus(self, analysis: ContractAnalysis, data: dict) -> ContractAnalysis:
        """Парсинг данных GoPlus"""
        
        # Базовая инфо
        analysis.token_name = data.get('token_name', analysis.token_name)
        analysis.token_symbol = data.get('token_symbol', analysis.token_symbol)
        analysis.data_source = "GoPlus Security"
        
        # Проверки безопасности
        analysis.is_proxy = data.get('is_proxy') == '1'
        analysis.has_mint_function = data.get('is_mintable') == '1'
        analysis.has_blacklist = data.get('is_blacklisted') == '1'
        analysis.has_pause = data.get('can_take_back_ownership') == '1'
        analysis.has_hidden_owner = data.get('hidden_owner') == '1'
        analysis.can_take_back_ownership = data.get('can_take_back_ownership') == '1'
        analysis.is_honeypot = data.get('is_honeypot') == '1'
        
        # Налоги
        try:
            analysis.buy_tax = float(data.get('buy_tax', 0) or 0) * 100
            analysis.sell_tax = float(data.get('sell_tax', 0) or 0) * 100
        except:
            pass
        
        # Владельцы
        try:
            analysis.holders_count = int(data.get('holder_count', 0) or 0)
            analysis.owner_balance_pct = float(data.get('owner_percent', 0) or 0) * 100
            
            # Топ холдеры
            top_holders = data.get('holders', [])
            if top_holders:
                analysis.top_holders_pct = sum(
                    float(h.get('percent', 0) or 0) * 100 
                    for h in top_holders[:10]
                )
        except:
            pass
        
        # Ликвидность
        try:
            lp_holders = data.get('lp_holders', [])
            if lp_holders:
                analysis.lp_holders = len(lp_holders)
                # Проверка на locked LP
                for lp in lp_holders:
                    if lp.get('is_locked') == 1:
                        analysis.liquidity_locked = True
                        break
        except:
            pass
        
        # Красные флаги
        if analysis.is_honeypot:
            analysis.red_flags.append("☠️ HONEYPOT - невозможно продать!")
        if analysis.has_mint_function:
            analysis.red_flags.append("⚠️ Mint функция - могут выпустить новые токены")
        if analysis.has_blacklist:
            analysis.red_flags.append("⚠️ Blacklist - могут заблокировать кошелёк")
        if analysis.can_take_back_ownership:
            analysis.red_flags.append("⚠️ Могут вернуть ownership")
        if analysis.has_hidden_owner:
            analysis.red_flags.append("⚠️ Скрытый владелец")
        if analysis.sell_tax > 10:
            analysis.red_flags.append(f"⚠️ Высокий налог на продажу: {analysis.sell_tax:.1f}%")
        if analysis.owner_balance_pct > 50:
            analysis.red_flags.append(f"⚠️ Владелец держит {analysis.owner_balance_pct:.1f}%")
        if not analysis.liquidity_locked:
            analysis.warnings.append("⚡ Ликвидность НЕ заблокирована")
        if analysis.holders_count < 100:
            analysis.warnings.append(f"⚡ Мало холдеров: {analysis.holders_count}")
        
        return analysis
    
    def _parse_honeypot(self, analysis: ContractAnalysis, data: dict) -> ContractAnalysis:
        """Парсинг данных Honeypot.is"""
        
        honeypot_result = data.get('honeypotResult', {})
        
        if honeypot_result.get('isHoneypot'):
            analysis.is_honeypot = True
            analysis.red_flags.append("☠️ HONEYPOT CONFIRMED!")
        
        # Симуляция сделки
        simulation = data.get('simulationResult', {})
        if simulation:
            try:
                analysis.buy_tax = float(simulation.get('buyTax', 0) or 0)
                analysis.sell_tax = float(simulation.get('sellTax', 0) or 0)
            except:
                pass
        
        return analysis
    
    def _calculate_risk(self, analysis: ContractAnalysis) -> ContractAnalysis:
        """Рассчитать итоговый риск"""
        score = 100
        
        # Критические проблемы
        if analysis.is_honeypot:
            score = 0
            analysis.risk_level = RiskLevel.SCAM
            return analysis
        
        # Вычитаем очки за проблемы
        if analysis.has_mint_function:
            score -= 20
        if analysis.has_blacklist:
            score -= 15
        if analysis.can_take_back_ownership:
            score -= 20
        if analysis.has_hidden_owner:
            score -= 15
        if not analysis.liquidity_locked:
            score -= 10
        if analysis.sell_tax > 10:
            score -= min(30, analysis.sell_tax)
        if analysis.owner_balance_pct > 30:
            score -= min(20, analysis.owner_balance_pct / 3)
        if analysis.holders_count < 100:
            score -= 10
        
        analysis.risk_score = max(0, min(100, int(score)))
        
        # Определить уровень
        if score >= 80:
            analysis.risk_level = RiskLevel.SAFE
        elif score >= 60:
            analysis.risk_level = RiskLevel.LOW_RISK
        elif score >= 40:
            analysis.risk_level = RiskLevel.MEDIUM_RISK
        elif score >= 20:
            analysis.risk_level = RiskLevel.HIGH_RISK
        else:
            analysis.risk_level = RiskLevel.SCAM
        
        return analysis
    
    def format_analysis_message(self, analysis: ContractAnalysis) -> str:
        """Форматировать сообщение для Telegram"""
        
        # Бар безопасности
        filled = analysis.risk_score // 10
        empty = 10 - filled
        safety_bar = '🟢' * filled + '⚪' * empty
        
        msg = f"""
🔐 <b>SMART CONTRACT SCAN</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>{analysis.token_name}</b> (${analysis.token_symbol})
🔗 Chain: {analysis.chain.upper()}
📝 <code>{analysis.token_address[:20]}...</code>

{analysis.risk_level.value}
Safety Score: {safety_bar} {analysis.risk_score}/100

📋 <b>ПРОВЕРКИ:</b>
├ Honeypot: {'❌ ДА!' if analysis.is_honeypot else '✅ Нет'}
├ Mint: {'⚠️ Есть' if analysis.has_mint_function else '✅ Нет'}
├ Blacklist: {'⚠️ Есть' if analysis.has_blacklist else '✅ Нет'}
├ LP Locked: {'✅ Да' if analysis.liquidity_locked else '⚠️ Нет'}
└ Holders: {analysis.holders_count:,}

💸 <b>НАЛОГИ:</b>
├ Buy: {analysis.buy_tax:.1f}%
└ Sell: {analysis.sell_tax:.1f}%

👥 <b>РАСПРЕДЕЛЕНИЕ:</b>
├ Owner: {analysis.owner_balance_pct:.1f}%
└ Top 10: {analysis.top_holders_pct:.1f}%
"""
        
        if analysis.red_flags:
            msg += "\n🚨 <b>КРАСНЫЕ ФЛАГИ:</b>\n"
            for flag in analysis.red_flags[:5]:
                msg += f"├ {flag}\n"
        
        if analysis.warnings:
            msg += "\n⚡ <b>ПРЕДУПРЕЖДЕНИЯ:</b>\n"
            for warn in analysis.warnings[:3]:
                msg += f"├ {warn}\n"
        
        msg += f"\n📡 <i>Источник: {analysis.data_source}</i>"
        
        return msg
    
    async def scan_and_alert(self, address: str, chain: str = 'eth'):
        """Сканировать и отправить алерт"""
        analysis = await self.scan_token(address, chain)
        msg = self.format_analysis_message(analysis)
        
        if self.telegram:
            await self.telegram.send_message(msg)
        else:
            logger.info(f"Contract scan:\n{msg}")
        
        return analysis

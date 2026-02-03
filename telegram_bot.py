"""
MEXC Pump Monitor - Telegram Bot Notifications
Rich formatted alerts with signal details
"""

import asyncio
import logging
import aiohttp
from typing import Optional
from datetime import datetime

from config import config

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Telegram notification system
    Sends formatted pump signals to chat
    """
    
    def __init__(self):
        self.config = config.telegram
        self.enabled = False
        self.bot_token = self.config.bot_token
        self.chat_id = self.config.chat_id
        self._session: Optional[aiohttp.ClientSession] = None
        
        if self.bot_token and self.chat_id:
            self.enabled = True
            logger.info(f"✅ Telegram notifier initialized (chat: {self.chat_id})")
        else:
            logger.warning("Telegram not configured - add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self._session is None or self._session.closed:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session
    
    async def send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """Send message to configured chat"""
        if not self.enabled:
            logger.debug(f"TG disabled, would send: {text[:100]}...")
            return False
        
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            data = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            async with session.post(url, json=data) as response:
                result = await response.json()
                
                if result.get('ok'):
                    return True
                else:
                    logger.error(f"Telegram API error: {result.get('description')}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_photo(
        self, 
        photo_bytes: bytes, 
        caption: str = '', 
        parse_mode: str = 'HTML'
    ) -> bool:
        """
        📊 Send photo/chart to Telegram
        
        Args:
            photo_bytes: PNG image as bytes
            caption: Optional caption text
            parse_mode: HTML or Markdown
        
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            
            import aiohttp
            form = aiohttp.FormData()
            form.add_field('chat_id', str(self.chat_id))
            form.add_field('photo', photo_bytes, filename='chart.png', content_type='image/png')
            if caption:
                form.add_field('caption', caption)
                form.add_field('parse_mode', parse_mode)
            
            async with session.post(url, data=form) as response:
                result = await response.json()
                
                if result.get('ok'):
                    logger.debug("Chart sent to Telegram")
                    return True
                else:
                    logger.error(f"Telegram photo error: {result.get('description')}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to send Telegram photo: {e}")
            return False
    
    async def send_signal_with_chart(
        self,
        signal_text: str,
        prices: list,
        signal_data: dict
    ) -> bool:
        """
        🔥 Отправить сигнал с графиком
        """
        try:
            from chart_generator import ChartGenerator
            
            chart_gen = ChartGenerator()
            chart_bytes = chart_gen.generate_signal_chart(
                symbol=signal_data.get('symbol', 'UNKNOWN'),
                prices=prices,
                signal_data=signal_data
            )
            
            if chart_bytes:
                # Send chart first
                await self.send_photo(chart_bytes, caption=signal_text)
            else:
                # Fallback to text only
                await self.send_message(signal_text)
            
            return True
            
        except ImportError:
            # matplotlib not available
            return await self.send_message(signal_text)
        except Exception as e:
            logger.error(f"Chart signal failed: {e}")
            return await self.send_message(signal_text)
    
    async def send_startup_message(self, symbols_count: int = 0) -> bool:
        """Send startup notification"""
        msg = f"""
🚀 <b>MEXC PUMP MONITOR ЗАПУЩЕН!</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ <b>Статус:</b> Активен
📊 <b>Символов:</b> {symbols_count}
🧠 <b>AI Prediction:</b> ON
📰 <b>News Parser:</b> ON
📱 <b>Dashboard:</b> http://localhost:8081/mobile

🔔 Уведомления:
├ 🔥 Пампы (15-50%+)
├ 🆕 Новые листинги
├ 📊 SHORT сигналы
└ 📰 Важные новости

<i>Удачного трейдинга! 💰</i>
"""
        return await self.send_message(msg)

    
    def _get_tier_emoji(self, tier: str) -> str:
        """Get emoji for pump tier"""
        tier_emojis = {
            'MEGA': '🔥🔥🔥',
            'MASSIVE': '🔥🔥',
            'STRONG': '🔥',
            'EARLY': '👀'
        }
        return tier_emojis.get(tier, '📊')
    
    def _get_score_bar(self, score: int) -> str:
        """Generate visual score bar"""
        filled = score // 10
        empty = 10 - filled
        return '▓' * filled + '░' * empty
    
    async def send_pump_signal(self, signal) -> bool:
        """
        Send formatted pump signal alert
        
        Args:
            signal: PumpSignal object
        """
        if not self.enabled:
            logger.info(f"PUMP SIGNAL: {signal.symbol} +{signal.price_change_pct:.1f}% Score: {signal.score}")
            return False
        
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
        
        emoji = self._get_tier_emoji(tier)
        score_bar = self._get_score_bar(signal.score)
        
        # Format RSI
        rsi_emoji = '🔴' if signal.rsi > 70 else '🟡' if signal.rsi > 50 else '🟢'
        
        # Format signal message
        message = f"""
{emoji} <b>{tier} ПАМП ОБНАРУЖЕН</b> {emoji}

📊 <b>{signal.symbol}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 <b>Цена:</b> ${signal.current_price:.6f}
📈 <b>Рост:</b> <b>+{signal.price_change_pct:.1f}%</b>
⏱ <b>За время:</b> {signal.time_window_minutes} мин
🔥 <b>Скорость:</b> {signal.price_change_pct / max(signal.time_window_minutes, 1):.1f}% в минуту

📊 <b>Скор сигнала:</b> {signal.score}/100
{score_bar}

📉 <b>RSI:</b> {rsi_emoji} {signal.rsi:.1f}
📊 <b>Объём:</b> {signal.volume_ratio:.1f}x от среднего

⚠️ <b>Качество:</b> {signal.tier}
💡 Рост за {signal.time_window_minutes} мин = агрессивный памп
"""
        
        return await self.send_message(message)
    
    async def send_short_signal(
        self,
        symbol: str,
        entry: float,
        stop_loss: float,
        take_profit: float,
        score: int,
        rsi: float = 0,
        reason: str = ""
    ) -> bool:
        """Send short signal alert"""
        
        risk = abs(stop_loss - entry) / entry * 100
        reward = abs(entry - take_profit) / entry * 100
        rr = reward / risk if risk > 0 else 0
        
        # Build detailed reasoning
        reasons = []
        if rsi > 70:
            reasons.append(f"📉 RSI {rsi:.0f} = перекуплен (>70)")
        if rsi > 80:
            reasons.append("🔴 Критическая перекупленность!")
        reasons.append("📈 После пампа всегда откат")
        reasons.append("🐋 Киты начинают фиксировать прибыль")
        if reason:
            reasons.append(f"💡 {reason}")
        
        reasons_text = "\n".join(reasons)
        
        msg = f"""
🔴🔴🔴 <b>ШОРТ СИГНАЛ</b> 🔴🔴🔴
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>{symbol}</b>

💰 <b>Точка входа:</b> ${entry:.6f}
🛑 <b>Стоп-лосс:</b> ${stop_loss:.6f} (-{risk:.1f}%)
🎯 <b>Тейк-профит:</b> ${take_profit:.6f} (+{reward:.1f}%)

📊 <b>Риск/Прибыль:</b> 1:{rr:.1f}
💪 <b>Скор:</b> {score}/100

<b>📋 ПОЧЕМУ ШОРТ?</b>
{reasons_text}

⚠️ <b>Логика:</b> Памп достиг пика, ожидаем откат на фиксации прибыли крупными игроками
"""
        return await self.send_message(msg)
    
    async def send_new_listing(self, symbol: str, details: dict = None) -> bool:
        """Send new listing alert"""
        details = details or {}
        
        price = details.get('price', 0)
        # Рекомендованный объём входа (1-3% от депозита, но минимум $20-50)
        recommended_volume = details.get('recommended_volume', 50)
        max_leverage = details.get('max_leverage', 20)
        
        msg = f"""
🆕🆕🆕 <b>НОВЫЙ ЛИСТИНГ!</b> 🆕🆕🆕
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>{symbol}</b>

⏰ <b>Время листинга:</b> {datetime.now().strftime('%H:%M:%S')}
💰 <b>Начальная цена:</b> ${price if price else 'Ожидаем...'}
📊 <b>Макс. леверидж:</b> {max_leverage}x

💵 <b>РЕКОМЕНДУЕМЫЙ ОБЪЁМ ВХОДА:</b>
├ Минимум: $20-30
├ Оптимально: ${recommended_volume}
├ Максимум: 2-3% от депозита
└ Леверидж: 5-10x (НЕ БОЛЬШЕ!)

⚠️ <b>ПРАВИЛА ЛИСТИНГА:</b>
1️⃣ Жди 3-5 минут после старта
2️⃣ Смотри объём - должен расти
3️⃣ Не входи на первой свече!
4️⃣ Стоп-лосс ОБЯЗАТЕЛЕН (-10-15%)

🔥 Первые минуты = максимальная волатильность!
"""
        return await self.send_message(msg)
    
    async def close(self):
        """Close session"""
        if self._session and not self._session.closed:
            await self._session.close()

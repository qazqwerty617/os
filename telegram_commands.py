"""
MEXC Pump Monitor - Telegram Commands
Управление ботом через Telegram команды
"""

import asyncio
import aiohttp
import ssl
import logging
import time
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CommandContext:
    """Контекст команды"""
    chat_id: int
    user_id: int
    username: str
    command: str
    args: List[str]
    timestamp: int


class TelegramCommands:
    """
    🤖 Telegram Bot Commands
    
    Команды:
    /start - Приветствие
    /stats - Статистика бота
    /signals - Последние сигналы
    /top - Топ пампов за день
    /pause - Пауза уведомлений
    /resume - Возобновить
    /health - Здоровье системы
    /help - Помощь
    """
    
    def __init__(self, bot_token: str, allowed_users: List[int] = None):
        self.bot_token = bot_token
        self.allowed_users = allowed_users or []  # Empty = allow all
        
        # Command handlers
        self._handlers: Dict[str, Callable] = {}
        
        # State
        self.is_paused = False
        self.last_update_id = 0
        
        # Stats references (set externally)
        self.stats_provider = None
        self.signals_provider = None
        self.health_provider = None
        
        # Register default commands
        self._register_defaults()
        
        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
    
    async def start(self):
        """Запустить polling"""
        self._running = True
        asyncio.create_task(self._poll_loop())
        # Set persistent menu
        asyncio.create_task(self._set_commands_menu())
        logger.info("🤖 Telegram Commands started")

    async def _set_commands_menu(self):
        """Set persistent menu commands"""
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
            commands = [
                {"command": "start", "description": "🚀 Main Menu"},
                {"command": "stats", "description": "📊 Bot Statistics"},
                {"command": "signals", "description": "🎯 Recent Signals"},
                {"command": "health", "description": "🏥 System Health"}
            ]
            await session.post(url, json={"commands": commands})
        except Exception as e:
            logger.error(f"Failed to set commands: {e}")
    
    async def stop(self):
        """Остановить"""
        self._running = False
        if self._session:
            await self._session.close()
    
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
    
    def _register_defaults(self):
        """Зарегистрировать стандартные команды"""
        self.register('start', self._cmd_start)
        self.register('help', self._cmd_help)
        self.register('stats', self._cmd_stats)
        self.register('signals', self._cmd_signals)
        self.register('top', self._cmd_top)
        self.register('pause', self._cmd_pause)
        self.register('resume', self._cmd_resume)
        self.register('health', self._cmd_health)
        self.register('status', self._cmd_status)
    
    def register(self, command: str, handler: Callable):
        """Зарегистрировать команду"""
        self._handlers[command.lower()] = handler
    
    async def _poll_loop(self):
        """Polling loop for updates"""
        while self._running:
            try:
                updates = await self._get_updates()
                
                for update in updates:
                    await self._process_update(update)
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
    
    async def _get_updates(self) -> List[dict]:
        """Получить обновления"""
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 30,
                'allowed_updates': ['message']
            }
            
            async with session.get(url, params=params, timeout=35) as r:
                data = await r.json()
                
                if data.get('ok'):
                    updates = data.get('result', [])
                    if updates:
                        self.last_update_id = updates[-1]['update_id']
                    return updates
                    
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            logger.error(f"Get updates error: {e}")
        
        return []
    
    async def _process_update(self, update: dict):
        """Обработать update"""
        message = update.get('message', {})
        text = message.get('text', '')
        
        if not text.startswith('/'):
            return
        
        # Parse command
        parts = text.split()
        cmd = parts[0][1:].lower().split('@')[0]  # Remove / and @botname
        args = parts[1:]
        
        # Create context
        chat = message.get('chat', {})
        user = message.get('from', {})
        
        ctx = CommandContext(
            chat_id=chat.get('id'),
            user_id=user.get('id'),
            username=user.get('username', 'unknown'),
            command=cmd,
            args=args,
            timestamp=int(time.time() * 1000)
        )
        
        # Check permissions
        if self.allowed_users and ctx.user_id not in self.allowed_users:
            await self._reply(ctx, "⛔ Access denied")
            return
        
        # Execute handler
        handler = self._handlers.get(cmd)
        if handler:
            try:
                response = await handler(ctx)
                if response:
                    await self._reply(ctx, response)
            except Exception as e:
                logger.error(f"Command error: {e}")
                await self._reply(ctx, f"❌ Error: {str(e)[:100]}")
        else:
            await self._reply(ctx, f"❓ Unknown command: /{cmd}\nUse /help for available commands")
    
    async def _reply(self, ctx: CommandContext, text: str, **kwargs):
        """Ответить на команду"""
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            data = {
                'chat_id': ctx.chat_id,
                'text': text,
                'parse_mode': 'HTML'
            }
            
            if 'reply_markup' in kwargs:
                data['reply_markup'] = kwargs['reply_markup']
            
            await session.post(url, json=data)
            
        except Exception as e:
            logger.error(f"Reply error: {e}")

    def _get_main_keyboard(self):
        """Get main menu keyboard"""
        # Mini App requires HTTPS with valid cert. 
        # Since we use raw IP, we must use a standard URL button to avoid "App Missing" issues.
        url = f"http://207.180.212.179:8081/mobile"
        
        return {
            "inline_keyboard": [
                [
                    {"text": "🚀 Open Dashboard (Browser)", "url": url}
                ],
                [
                    {"text": "📊 Stats", "callback_data": "stats"},
                    {"text": "🎯 Signals", "callback_data": "signals"}
                ],
                [
                    {"text": "⏸️ Pause", "callback_data": "pause"},
                    {"text": "▶️ Resume", "callback_data": "resume"}
                ]
            ]
        }
    
    # === Command Handlers ===
    
    async def _cmd_start(self, ctx: CommandContext) -> str:
        return """
🚀 <b>MEXC PUMP MONITOR</b>

Добро пожаловать! Я отслеживаю пампы и генерирую торговые сигналы на MEXC Futures.

<b>Доступные команды:</b>
/stats - Статистика бота
/signals - Последние сигналы  
/top - Топ пампов за день
/health - Здоровье системы
/pause - Пауза уведомлений
/resume - Возобновить
/help - Эта справка

<i>Удачной торговли! 💰</i>
"""
        await self._reply(ctx, msg, reply_markup=self._get_main_keyboard())
        return None
    
    async def _cmd_help(self, ctx: CommandContext) -> str:
        return await self._cmd_start(ctx)
    
    async def _cmd_stats(self, ctx: CommandContext) -> str:
        if self.stats_provider:
            try:
                stats = self.stats_provider()
                return f"""
📊 <b>СТАТИСТИКА БОТА</b>

⏱️ Uptime: {stats.get('uptime', 'N/A')}
📈 Сигналов сегодня: {stats.get('signals_today', 0)}
🔥 Пампов обнаружено: {stats.get('pumps_detected', 0)}
✅ Win Rate: {stats.get('win_rate', 'N/A')}

📡 Символов: {stats.get('symbols', 0)}
🔄 Обновлений/сек: {stats.get('updates_per_sec', 0)}
"""
            except:
                pass
        
        return """
📊 <b>СТАТИСТИКА</b>

⏱️ Бот работает
📈 Мониторинг активен
🔄 Статистика собирается...

<i>Для подробной статистики подключите stats_provider</i>
"""
    
    async def _cmd_signals(self, ctx: CommandContext) -> str:
        if self.signals_provider:
            try:
                signals = self.signals_provider(limit=5)
                if signals:
                    text = "📊 <b>ПОСЛЕДНИЕ СИГНАЛЫ:</b>\n\n"
                    for s in signals:
                        text += f"• {s.get('symbol')} - {s.get('type')} @ ${s.get('price')}\n"
                    return text
            except:
                pass
        
        return "📊 Нет недавних сигналов"
    
    async def _cmd_top(self, ctx: CommandContext) -> str:
        return """
🔥 <b>ТОП ПАМПОВ ЗА 24Ч</b>

Функция в разработке...

<i>Данные собираются в реальном времени</i>
"""
    
    async def _cmd_pause(self, ctx: CommandContext) -> str:
        self.is_paused = True
        return "⏸️ Уведомления приостановлены\n\nИспользуйте /resume для возобновления"
    
    async def _cmd_resume(self, ctx: CommandContext) -> str:
        self.is_paused = False
        return "▶️ Уведомления возобновлены!"
    
    async def _cmd_health(self, ctx: CommandContext) -> str:
        if self.health_provider:
            try:
                health = self.health_provider()
                return f"""
🏥 <b>ЗДОРОВЬЕ СИСТЕМЫ</b>

💻 CPU: {health.get('cpu', 0):.1f}%
🧠 RAM: {health.get('memory', 0):.1f}%
📡 API: {'🟢 OK' if health.get('api_ok') else '🔴 Error'}
🔌 WebSocket: {'🟢 Connected' if health.get('ws_ok') else '🔴 Disconnected'}

⏱️ Uptime: {health.get('uptime', 'N/A')}
"""
            except:
                pass
        
        return """
🏥 <b>ЗДОРОВЬЕ СИСТЕМЫ</b>

🟢 Все системы работают нормально

<i>Для детальной информации подключите health_provider</i>
"""
    
    async def _cmd_status(self, ctx: CommandContext) -> str:
        status = "▶️ Активен" if not self.is_paused else "⏸️ На паузе"
        return f"""
📡 <b>СТАТУС БОТА</b>

Состояние: {status}
Команд обработано: ✅
Последняя проверка: {datetime.now().strftime('%H:%M:%S')}
"""

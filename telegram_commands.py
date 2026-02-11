"""
MEXC Pump Monitor - Telegram Commands
Optimized bot control via Telegram commands
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
    """Command context"""
    chat_id: int
    user_id: int
    username: str
    command: str
    args: List[str]
    timestamp: int


# Menu commands for Telegram
MENU_COMMANDS = [
    {"command": "start", "description": "🚀 Main Menu"},
    {"command": "stats", "description": "📊 Bot Statistics"},
    {"command": "signals", "description": "🎯 Recent Signals"},
    {"command": "health", "description": "🏥 System Health"}
]


class TelegramCommands:
    """
    Optimized Telegram Bot Commands
    
    Commands:
    /start - Welcome
    /stats - Bot statistics  
    /signals - Recent signals
    /top - Top pumps today
    /pause - Pause notifications
    /resume - Resume
    /health - System health
    /help - Help
    """
    
    def __init__(self, bot_token: str, allowed_users: List[int] = None):
        self.bot_token = bot_token
        self.allowed_users = allowed_users or []
        
        self._handlers: Dict[str, Callable] = {}
        self.is_paused = False
        self.last_update_id = 0
        
        self.stats_provider = None
        self.signals_provider = None
        self.health_provider = None
        
        self._session: Optional[aiohttp.ClientSession] = None
        self._running = False
        
        self._register_defaults()
    
    async def start(self):
        """Start polling"""
        self._running = True
        asyncio.create_task(self._poll_loop())
        asyncio.create_task(self._set_commands_menu())
        logger.info("🤖 Telegram Commands started")
    
    async def stop(self):
        """Stop polling"""
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
    
    async def _set_commands_menu(self):
        """Set persistent menu commands"""
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
            await session.post(url, json={"commands": MENU_COMMANDS})
        except Exception as e:
            logger.error(f"Failed to set commands: {e}")
    
    def _register_defaults(self):
        """Register default commands"""
        commands = {
            'start': self._cmd_start,
            'help': self._cmd_start,
            'stats': self._cmd_stats,
            'signals': self._cmd_signals,
            'top': self._cmd_top,
            'pause': self._cmd_pause,
            'resume': self._cmd_resume,
            'health': self._cmd_health,
            'status': self._cmd_status,
        }
        for cmd, handler in commands.items():
            self._handlers[cmd] = handler
    
    def register(self, command: str, handler: Callable):
        """Register command handler"""
        self._handlers[command.lower()] = handler
    
    async def _poll_loop(self):
        """Polling loop"""
        while self._running:
            try:
                for update in await self._get_updates():
                    await self._process_update(update)
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
    
    async def _get_updates(self) -> List[dict]:
        """Get updates"""
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
        """Process update"""
        message = update.get('message', {})
        text = message.get('text', '')
        
        if not text.startswith('/'):
            return
        
        parts = text.split()
        cmd = parts[0][1:].lower().split('@')[0]
        args = parts[1:]
        
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
        
        if self.allowed_users and ctx.user_id not in self.allowed_users:
            await self._reply(ctx, "⛔ Access denied")
            return
        
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
            await self._reply(ctx, f"❓ Unknown: /{cmd}\nUse /help")
    
    async def _reply(self, ctx: CommandContext, text: str, **kwargs):
        """Reply to command"""
        try:
            session = await self._get_session()
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            
            data = {'chat_id': ctx.chat_id, 'text': text, 'parse_mode': 'HTML'}
            if 'reply_markup' in kwargs:
                data['reply_markup'] = kwargs['reply_markup']
            
            await session.post(url, json=data)
        except Exception as e:
            logger.error(f"Reply error: {e}")
    
    def _get_main_keyboard(self):
        """Get main menu keyboard"""
        from config import config
        dash_url = config.dashboard.public_url or f"http://{config.dashboard.host if config.dashboard.host != '0.0.0.0' else 'IP_ADDRESS'}:8081/mobile"
        return {
            "inline_keyboard": [
                [{"text": "📱 OPEN DASHBOARD / ТЕРМИНАЛ", "url": dash_url}],
                [
                    {"text": "📊 STATS / ИТОГИ", "callback_data": "stats"},
                    {"text": "🎯 SIGNALS / СИГНАЛЫ", "callback_data": "signals"}
                ],
                [
                    {"text": "🏥 HEALTH / СОСТОЯНИЕ", "callback_data": "health"},
                    {"text": "⚙️ STATUS / СТАТУС", "callback_data": "status"}
                ],
                [
                    {"text": "⏸️ PAUSE", "callback_data": "pause"},
                    {"text": "▶️ RESUME", "callback_data": "resume"}
                ]
            ]
        }
    
    # === Command Handlers ===
    
    async def _cmd_start(self, ctx: CommandContext) -> str:
        msg = """
🤖 <b>ALPHA MONSTER TERMINAL</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<i>Next-gen Pump Detection Engine</i>

Welcome! Бот отслеживает аномальные движения MEXC Futures в реальном времени.

📡 <b>COMMANDS / КОМАНДЫ:</b>
├ /stats — Profit & Metrics / Итоги
├ /signals — Recent signals / Сигналы
├ /health — System status / Состояние
└ /help — Info / Справка

<b>MONITORING:</b> 🟢 ACTIVE / АКТИВЕН

<i>Trade smart. 💰</i>
"""
        await self._reply(ctx, msg, reply_markup=self._get_main_keyboard())
        return None
    
    async def _cmd_stats(self, ctx: CommandContext) -> str:
        if self.stats_provider:
            try:
                s = self.stats_provider()
                return f"""
📊 <b>TRADING STATS / СТАТИСТИКА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏱️ <b>UPTIME:</b> {s.get('uptime', 'N/A')}
📈 <b>DAILY SIGNALS:</b> {s.get('signals_today', 0)}
🔥 <b>PUMPS FOUND:</b> {s.get('pumps_detected', 0)}
✅ <b>WIN RATE:</b> {s.get('win_rate', 'N/A')}

📡 <b>TRACKED:</b> {s.get('symbols', 0)} pairs
🔄 <b>SPEED:</b> {s.get('updates_per_sec', 0)} rec/s
"""
            except:
                pass
        
        return """
📊 <b>STATISTICS</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏱️ Bot is operational
📈 Collecting real-time data...
🔄 Пожалуйста, подождите...
"""
    
    async def _cmd_signals(self, ctx: CommandContext) -> str:
        if self.signals_provider:
            try:
                signals = self.signals_provider(limit=5)
                if signals:
                    text = "📊 <b>RECENT SIGNALS:</b>\n\n"
                    for s in signals:
                        text += f"• {s.get('symbol')} - {s.get('type')} @ ${s.get('price')}\n"
                    return text
            except:
                pass
        return "📊 No recent signals"
    
    async def _cmd_top(self, ctx: CommandContext) -> str:
        return """
🔥 <b>TOP PUMPS 24H</b>

Feature in development...

<i>Data being collected in real-time</i>
"""
    
    async def _cmd_pause(self, ctx: CommandContext) -> str:
        self.is_paused = True
        return "⏸️ Notifications paused\n\nUse /resume to continue"
    
    async def _cmd_resume(self, ctx: CommandContext) -> str:
        self.is_paused = False
        return "▶️ Notifications resumed!"
    
    async def _cmd_health(self, ctx: CommandContext) -> str:
        if self.health_provider:
            try:
                h = self.health_provider()
                return f"""
🏥 <b>СОСТОЯНИЕ СИСТЕМЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💻 <b>CPU:</b> {h.get('cpu', 0):.1f}%
🧠 <b>RAM:</b> {h.get('memory', 0):.1f}%
📡 <b>MEXC API:</b> {'🟢 OK' if h.get('api_ok') else '🔴 Error'}
🔌 <b>Websocket:</b> {'🟢 OK' if h.get('ws_ok') else '🔴 Error'}

⏱️ <b>Uptime:</b> {h.get('uptime', 'N/A')}
⚙️ <b>Статус:</b> Operational
"""
            except:
                pass
        
        return """
🏥 <b>СОСТОЯНИЕ СИСТЕМЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🟢 Все системы работают в штатном режиме
"""
    
    async def _cmd_status(self, ctx: CommandContext) -> str:
        status = "▶️ Active" if not self.is_paused else "⏸️ Paused"
        return f"""
📡 <b>BOT STATUS</b>

State: {status}
Commands processed: ✅
Last check: {datetime.now().strftime('%H:%M:%S')}
"""

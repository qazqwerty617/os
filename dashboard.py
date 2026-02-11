"""
MEXC Pump Monitor - Premium Real-time Web Dashboard
FastAPI + WebSocket + Glassmorphism UI
"""

import asyncio
import json
import time
import logging
import psutil
from typing import Dict, List, Set
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from config import config

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manage WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
    
    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        data = json.dumps(message)
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.add(connection)
        self.active_connections -= disconnected


# Create FastAPI app
app = FastAPI(title="MEXC Pump Monitor", version="2.0.0")
manager = ConnectionManager()

# Component references
detector = None
market_analyzer = None
mtf_analyzer = None
health_monitor = None
whale_detector = None
news_bot = None
signal_engine = None
perf_tracker = None
_start_time = time.time()


def set_components(pump_detector, mkt_analyzer, mtf_anlz,
                   health_mon=None, whale_det=None, news=None,
                   sig_engine=None, perf=None):
    """Set component references for the dashboard"""
    global detector, market_analyzer, mtf_analyzer
    global health_monitor, whale_detector, news_bot, signal_engine, perf_tracker
    detector = pump_detector
    market_analyzer = mkt_analyzer
    mtf_analyzer = mtf_anlz
    health_monitor = health_mon
    whale_detector = whale_det
    news_bot = news
    signal_engine = sig_engine
    perf_tracker = perf


@app.get("/", response_class=HTMLResponse)
async def root():
    return get_dashboard_html()


@app.get("/api/stats")
async def get_stats():
    if detector:
        return detector.get_stats()
    return {}


@app.get("/api/signals")
async def get_signals(limit: int = 50):
    if detector:
        signals = detector.get_signal_history(limit)
        return [s.to_dict() for s in signals]
    return []


@app.get("/api/active")
async def get_active():
    if detector:
        signals = detector.get_active_signals()
        return [s.to_dict() for s in signals]
    return []


@app.get("/api/funding")
async def get_extreme_funding():
    if market_analyzer:
        extreme = market_analyzer.get_extreme_funding_symbols()
        return [
            {'symbol': s, 'funding_rate': f.funding_rate, 'predicted': f.predicted_rate}
            for s, f in extreme[:20]
        ]
    return []


@app.get("/api/oi")
async def get_oi_changes():
    if market_analyzer:
        high_oi = market_analyzer.get_high_oi_change_symbols()
        return [
            {'symbol': s, 'oi_change_1h': o.oi_change_1h, 'oi_change_24h': o.oi_change_24h}
            for s, o in high_oi[:20]
        ]
    return []


@app.get("/api/health")
async def get_health():
    """System health metrics"""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    uptime = int(time.time() - _start_time)
    
    result = {
        'cpu': cpu,
        'ram_percent': mem.percent,
        'ram_used_mb': round(mem.used / 1024 / 1024),
        'ram_total_mb': round(mem.total / 1024 / 1024),
        'uptime_seconds': uptime,
        'uptime_str': str(timedelta(seconds=uptime)),
        'ws_clients': len(manager.active_connections),
        'api_ok': True,
        'ws_ok': True
    }
    
    if health_monitor:
        try:
            h = health_monitor.get_health_status()
            result['api_ok'] = h.get('api_ok', True)
            result['ws_ok'] = h.get('ws_ok', True)
        except:
            pass
    
    return result


@app.get("/api/whales")
async def get_whales():
    """Recent whale activity"""
    if whale_detector:
        try:
            orders = whale_detector.get_recent_whale_orders(20)
            return [{
                'symbol': o.symbol,
                'side': o.side.value,
                'value_usd': round(o.value_usd, 2),
                'category': o.category.value,
                'timestamp': o.timestamp,
                'price': o.price
            } for o in orders]
        except:
            pass
    return []


@app.get("/api/news")
async def get_news():
    """Recent news"""
    if news_bot:
        try:
            items = news_bot.get_recent_news(15)
            return [{
                'title': n.title,
                'source': n.source.value,
                'sentiment': n.sentiment.value,
                'importance': n.importance,
                'tokens': n.mentioned_tokens[:3],
                'timestamp': n.timestamp,
                'url': n.url
            } for n in items]
        except:
            pass
    return []


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcast_signal(signal):
    await manager.broadcast({
        "type": "signal",
        "data": signal.to_dict()
    })


async def broadcast_update():
    if not detector:
        return
    stats = detector.get_stats()
    active = [s.to_dict() for s in detector.get_active_signals()]
    await manager.broadcast({
        "type": "update",
        "stats": stats,
        "active_signals": active,
        "timestamp": time.time()
    })


def get_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MEXC Pump Monitor — Command Center</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-0: #06080d;
            --bg-1: #0c1019;
            --bg-2: #131926;
            --bg-3: #1a2236;
            --bg-glass: rgba(16, 22, 36, 0.65);
            --border: rgba(255,255,255,0.06);
            --border-glow: rgba(99, 140, 255, 0.15);
            --text-1: #f0f4ff;
            --text-2: #8899bb;
            --text-3: #556688;
            --green: #00e676;
            --green-dim: rgba(0,230,118,0.12);
            --red: #ff3d57;
            --red-dim: rgba(255,61,87,0.12);
            --orange: #ffab00;
            --orange-dim: rgba(255,171,0,0.12);
            --blue: #448aff;
            --blue-dim: rgba(68,138,255,0.12);
            --purple: #b388ff;
            --purple-dim: rgba(179,136,255,0.12);
            --cyan: #18ffff;
            --gradient-brand: linear-gradient(135deg, #ff3d57, #ff8a00, #ffab00);
            --gradient-card: linear-gradient(165deg, rgba(25,35,60,0.7), rgba(12,16,25,0.9));
            --shadow-card: 0 8px 32px rgba(0,0,0,0.4);
            --shadow-glow-green: 0 0 20px rgba(0,230,118,0.15);
            --shadow-glow-red: 0 0 20px rgba(255,61,87,0.15);
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Inter', -apple-system, sans-serif;
            background: var(--bg-0);
            color: var(--text-1);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* === ANIMATED BACKGROUND === */
        body::before {
            content: '';
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background:
                radial-gradient(ellipse 600px 400px at 15% 20%, rgba(68,138,255,0.06) 0%, transparent 70%),
                radial-gradient(ellipse 500px 350px at 85% 70%, rgba(255,61,87,0.05) 0%, transparent 70%),
                radial-gradient(ellipse 400px 300px at 50% 50%, rgba(179,136,255,0.03) 0%, transparent 70%);
            pointer-events: none;
            z-index: 0;
            animation: bgShift 20s ease-in-out infinite alternate;
        }
        @keyframes bgShift {
            0% { transform: translate(0,0) scale(1); }
            100% { transform: translate(-20px, 10px) scale(1.05); }
        }

        /* === HEADER === */
        .header {
            position: sticky; top: 0; z-index: 100;
            background: rgba(6,8,13,0.85);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border-bottom: 1px solid var(--border);
            padding: 0 2rem;
            height: 64px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .logo {
            display: flex; align-items: center; gap: 12px;
            font-size: 1.25rem; font-weight: 800;
            letter-spacing: -0.5px;
        }
        .logo-icon {
            width: 36px; height: 36px;
            border-radius: 10px;
            background: var(--gradient-brand);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.1rem;
            box-shadow: 0 4px 15px rgba(255,61,87,0.3);
        }
        .logo-text {
            background: var(--gradient-brand);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .logo-sub {
            font-size: 0.7rem; font-weight: 500;
            color: var(--text-3);
            letter-spacing: 2px;
            text-transform: uppercase;
        }

        .header-right {
            display: flex; align-items: center; gap: 1.5rem;
        }
        .live-badge {
            display: flex; align-items: center; gap: 6px;
            background: var(--green-dim);
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 0.75rem; font-weight: 600;
            color: var(--green);
            border: 1px solid rgba(0,230,118,0.15);
        }
        .live-dot {
            width: 7px; height: 7px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%,100% { box-shadow: 0 0 0 0 rgba(0,230,118,0.5); }
            50% { box-shadow: 0 0 0 6px rgba(0,230,118,0); }
        }
        .ws-badge {
            font-size: 0.75rem; font-weight: 500;
            color: var(--text-3);
        }
        .ws-badge.connected { color: var(--green); }
        .ws-badge.disconnected { color: var(--red); }
        .clock {
            font-size: 0.8rem; font-weight: 500;
            color: var(--text-2);
            font-variant-numeric: tabular-nums;
        }

        /* === LAYOUT === */
        .main {
            position: relative; z-index: 1;
            max-width: 1600px;
            margin: 0 auto;
            padding: 1.5rem 2rem 3rem;
        }

        /* === STAT CARDS ROW === */
        .stats-row {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        @media (max-width: 1200px) { .stats-row { grid-template-columns: repeat(3, 1fr); } }
        @media (max-width: 768px) { .stats-row { grid-template-columns: repeat(2, 1fr); } }

        .stat-card {
            background: var(--gradient-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }
        .stat-card:hover {
            border-color: var(--border-glow);
            transform: translateY(-2px);
            box-shadow: var(--shadow-card);
        }
        .stat-card::after {
            content: '';
            position: absolute; top: 0; left: 0; right: 0;
            height: 2px;
            border-radius: 16px 16px 0 0;
        }
        .stat-card.accent-green::after { background: var(--green); }
        .stat-card.accent-red::after { background: var(--red); }
        .stat-card.accent-orange::after { background: var(--orange); }
        .stat-card.accent-blue::after { background: var(--blue); }
        .stat-card.accent-purple::after { background: var(--purple); }

        .stat-label {
            font-size: 0.72rem; font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: var(--text-3);
            margin-bottom: 0.5rem;
        }
        .stat-value {
            font-size: 2rem; font-weight: 800;
            letter-spacing: -1px;
            font-variant-numeric: tabular-nums;
            line-height: 1.1;
        }
        .stat-value.green { color: var(--green); }
        .stat-value.red { color: var(--red); }
        .stat-value.orange { color: var(--orange); }
        .stat-value.blue { color: var(--blue); }
        .stat-value.purple { color: var(--purple); }

        .stat-sub {
            font-size: 0.72rem; font-weight: 500;
            color: var(--text-3);
            margin-top: 4px;
        }

        /* === PANELS GRID === */
        .panels {
            display: grid;
            grid-template-columns: 1fr 380px;
            gap: 1.5rem;
        }
        @media (max-width: 1100px) { .panels { grid-template-columns: 1fr; } }

        /* === GLASS PANEL === */
        .panel {
            background: var(--gradient-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
        }
        .panel-head {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .panel-title {
            font-size: 0.85rem; font-weight: 700;
            display: flex; align-items: center; gap: 8px;
        }
        .panel-badge {
            font-size: 0.65rem; font-weight: 700;
            background: var(--blue-dim);
            color: var(--blue);
            padding: 2px 8px;
            border-radius: 10px;
        }

        /* === SIGNAL ROW === */
        .signal-list { max-height: 560px; overflow-y: auto; }
        .signal-list::-webkit-scrollbar { width: 4px; }
        .signal-list::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 4px; }

        .signal-row {
            display: grid;
            grid-template-columns: 140px 90px 70px 70px 90px 1fr;
            gap: 0.75rem;
            align-items: center;
            padding: 0.85rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.82rem;
            transition: background 0.15s;
        }
        .signal-row:hover { background: rgba(255,255,255,0.02); }

        .signal-row.tier-mega {
            border-left: 3px solid var(--red);
            animation: megaGlow 3s infinite;
        }
        .signal-row.tier-massive { border-left: 3px solid var(--orange); }
        .signal-row.tier-strong { border-left: 3px solid var(--blue); }
        .signal-row.tier-early { border-left: 3px solid var(--text-3); }

        @keyframes megaGlow {
            0%,100% { background: rgba(255,61,87,0.03); }
            50% { background: rgba(255,61,87,0.08); }
        }

        .sym-name {
            font-weight: 700; font-size: 0.9rem;
        }
        .sym-pair {
            font-size: 0.65rem; color: var(--text-3); font-weight: 500;
        }
        .pct-up { color: var(--green); font-weight: 700; }
        .pct-dn { color: var(--red); font-weight: 700; }

        .score-pill {
            display: inline-flex; align-items: center; justify-content: center;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 0.72rem; font-weight: 700;
        }
        .score-s { background: var(--green-dim); color: var(--green); }
        .score-a { background: var(--blue-dim); color: var(--blue); }
        .score-b { background: var(--orange-dim); color: var(--orange); }
        .score-c { background: rgba(255,255,255,0.06); color: var(--text-3); }

        .time-ago {
            color: var(--text-3); font-size: 0.72rem;
            text-align: right;
            font-variant-numeric: tabular-nums;
        }

        .empty-state {
            padding: 3rem; text-align: center; color: var(--text-3);
            font-size: 0.85rem;
        }
        .empty-state .spinner {
            display: inline-block;
            width: 24px; height: 24px;
            border: 2px solid var(--border);
            border-top-color: var(--blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 0.75rem;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* === RIGHT SIDEBAR === */
        .sidebar { display: flex; flex-direction: column; gap: 1.5rem; }

        /* System Health Gauges */
        .gauge-row {
            display: flex; gap: 1rem;
            padding: 1.25rem 1.5rem;
        }
        .gauge {
            flex: 1; text-align: center;
        }
        .gauge-ring {
            position: relative;
            width: 80px; height: 80px;
            margin: 0 auto 8px;
        }
        .gauge-ring svg { transform: rotate(-90deg); }
        .gauge-ring circle {
            fill: none;
            stroke-width: 5;
        }
        .gauge-bg { stroke: var(--bg-3); }
        .gauge-fill {
            stroke-linecap: round;
            transition: stroke-dashoffset 1s ease, stroke 0.5s;
        }
        .gauge-val {
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
            font-size: 1.1rem; font-weight: 800;
            font-variant-numeric: tabular-nums;
        }
        .gauge-label {
            font-size: 0.65rem; font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-3);
        }

        /* Component status */
        .comp-status {
            padding: 0 1.5rem 1.25rem;
            display: flex; flex-direction: column; gap: 8px;
        }
        .comp-row {
            display: flex; justify-content: space-between; align-items: center;
            font-size: 0.78rem;
        }
        .comp-name { color: var(--text-2); }
        .comp-ok { color: var(--green); font-weight: 600; }
        .comp-err { color: var(--red); font-weight: 600; }

        /* Whale & News items */
        .feed-item {
            padding: 0.8rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.78rem;
            transition: background 0.15s;
        }
        .feed-item:hover { background: rgba(255,255,255,0.02); }
        .feed-title { font-weight: 600; margin-bottom: 3px; line-height: 1.4; }
        .feed-meta {
            display: flex; gap: 0.75rem; align-items: center;
            color: var(--text-3); font-size: 0.68rem;
        }
        .feed-badge {
            padding: 1px 6px; border-radius: 4px;
            font-size: 0.6rem; font-weight: 700;
            text-transform: uppercase;
        }
        .feed-badge.buy { background: var(--green-dim); color: var(--green); }
        .feed-badge.sell { background: var(--red-dim); color: var(--red); }
        .feed-badge.bullish { background: var(--green-dim); color: var(--green); }
        .feed-badge.bearish { background: var(--red-dim); color: var(--red); }
        .feed-badge.neutral { background: rgba(255,255,255,0.06); color: var(--text-3); }

        .feed-list { max-height: 280px; overflow-y: auto; }
        .feed-list::-webkit-scrollbar { width: 3px; }
        .feed-list::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 3px; }

        /* New signal animation */
        @keyframes slideIn {
            from { transform: translateX(-20px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .signal-row.new { animation: slideIn 0.4s ease; }

        /* Uptime bar */
        .uptime-bar {
            padding: 0.6rem 1.5rem;
            border-top: 1px solid var(--border);
            display: flex; justify-content: space-between; align-items: center;
            font-size: 0.72rem; color: var(--text-3);
        }
        .uptime-val { color: var(--text-2); font-weight: 600; font-variant-numeric: tabular-nums; }
    </style>
</head>
<body>
    <!-- HEADER -->
    <header class="header">
        <div class="logo">
            <div class="logo-icon">🔥</div>
            <div>
                <div class="logo-text">PUMP MONITOR</div>
                <div class="logo-sub">Command Center v2.0</div>
            </div>
        </div>
        <div class="header-right">
            <div class="live-badge"><div class="live-dot"></div> LIVE</div>
            <div class="ws-badge" id="wsStatus">● Connecting...</div>
            <div class="clock" id="clock">--:--:--</div>
        </div>
    </header>

    <!-- MAIN -->
    <main class="main">
        <!-- STAT CARDS -->
        <div class="stats-row">
            <div class="stat-card accent-green">
                <div class="stat-label">Активные сигналы</div>
                <div class="stat-value green" id="statActive">0</div>
                <div class="stat-sub">прямо сейчас</div>
            </div>
            <div class="stat-card accent-red">
                <div class="stat-label">Пампов найдено</div>
                <div class="stat-value red" id="statPumps">0</div>
                <div class="stat-sub">за сессию</div>
            </div>
            <div class="stat-card accent-orange">
                <div class="stat-label">Всего сигналов</div>
                <div class="stat-value orange" id="statSignals">0</div>
                <div class="stat-sub">за сессию</div>
            </div>
            <div class="stat-card accent-blue">
                <div class="stat-label">Отслеживается</div>
                <div class="stat-value blue" id="statSymbols">0</div>
                <div class="stat-sub">торговых пар</div>
            </div>
            <div class="stat-card accent-purple">
                <div class="stat-label">WS Клиенты</div>
                <div class="stat-value purple" id="statClients">0</div>
                <div class="stat-sub">подключены</div>
            </div>
        </div>

        <!-- PANELS -->
        <div class="panels">
            <!-- LEFT: Signals -->
            <div class="panel">
                <div class="panel-head">
                    <div class="panel-title">🎯 Сигналы <span class="panel-badge" id="sigCount">0</span></div>
                </div>
                <div class="signal-list" id="signalList">
                    <div class="empty-state">
                        <div class="spinner"></div>
                        <div>Сканирование рынка...</div>
                    </div>
                </div>
            </div>

            <!-- RIGHT: Sidebar -->
            <div class="sidebar">
                <!-- System Health -->
                <div class="panel">
                    <div class="panel-head">
                        <div class="panel-title">💻 Система</div>
                    </div>
                    <div class="gauge-row">
                        <div class="gauge">
                            <div class="gauge-ring">
                                <svg viewBox="0 0 80 80">
                                    <circle class="gauge-bg" cx="40" cy="40" r="34"/>
                                    <circle class="gauge-fill" id="cpuRing" cx="40" cy="40" r="34"
                                        stroke-dasharray="213.6" stroke-dashoffset="213.6" stroke="var(--green)"/>
                                </svg>
                                <div class="gauge-val" id="cpuVal">0%</div>
                            </div>
                            <div class="gauge-label">CPU</div>
                        </div>
                        <div class="gauge">
                            <div class="gauge-ring">
                                <svg viewBox="0 0 80 80">
                                    <circle class="gauge-bg" cx="40" cy="40" r="34"/>
                                    <circle class="gauge-fill" id="ramRing" cx="40" cy="40" r="34"
                                        stroke-dasharray="213.6" stroke-dashoffset="213.6" stroke="var(--blue)"/>
                                </svg>
                                <div class="gauge-val" id="ramVal">0%</div>
                            </div>
                            <div class="gauge-label">RAM</div>
                        </div>
                    </div>
                    <div class="comp-status">
                        <div class="comp-row">
                            <span class="comp-name">MEXC API</span>
                            <span class="comp-ok" id="compApi">● Online</span>
                        </div>
                        <div class="comp-row">
                            <span class="comp-name">WebSocket</span>
                            <span class="comp-ok" id="compWs">● Online</span>
                        </div>
                        <div class="comp-row">
                            <span class="comp-name">RAM Used</span>
                            <span class="comp-name" id="ramUsed" style="color:var(--text-2);font-weight:600">-- MB</span>
                        </div>
                    </div>
                    <div class="uptime-bar">
                        <span>Uptime</span>
                        <span class="uptime-val" id="uptimeVal">--</span>
                    </div>
                </div>

                <!-- Whale Activity -->
                <div class="panel">
                    <div class="panel-head">
                        <div class="panel-title">🐋 Крупные ордера</div>
                    </div>
                    <div class="feed-list" id="whaleList">
                        <div class="empty-state">Ожидание хантинга...</div>
                    </div>
                </div>

                <!-- News Feed -->
                <div class="panel">
                    <div class="panel-head">
                        <div class="panel-title">📰 Новости</div>
                    </div>
                    <div class="feed-list" id="newsList">
                        <div class="empty-state">Загрузка новостей...</div>
                    </div>
                </div>
            </div>
        </div>
    </main>

    <!-- NOTIFICATION SOUND -->
    <audio id="alertSound" preload="auto" src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleqwQJqHEo09p"></audio>

    <script>
    /* ===== STATE ===== */
    let ws, signals = [];

    /* ===== CLOCK ===== */
    function updateClock() {
        const d = new Date();
        document.getElementById('clock').textContent =
            d.toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
    }
    setInterval(updateClock, 1000);
    updateClock();

    /* ===== WEBSOCKET ===== */
    function connectWS() {
        ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onopen = () => {
            document.getElementById('wsStatus').className = 'ws-badge connected';
            document.getElementById('wsStatus').textContent = '● Connected';
        };
        ws.onclose = () => {
            document.getElementById('wsStatus').className = 'ws-badge disconnected';
            document.getElementById('wsStatus').textContent = '● Reconnecting...';
            setTimeout(connectWS, 3000);
        };
        ws.onmessage = (e) => {
            const msg = JSON.parse(e.data);
            if (msg.type === 'signal') {
                signals.unshift(msg.data);
                if (signals.length > 60) signals.pop();
                renderSignals(true);
                playAlert();
            } else if (msg.type === 'update') {
                updateStats(msg.stats);
            }
        };
    }

    /* ===== RENDER SIGNALS ===== */
    function renderSignals(isNew) {
        const el = document.getElementById('signalList');
        document.getElementById('sigCount').textContent = signals.length;

        if (!signals.length) {
            el.innerHTML = '<div class="empty-state"><div class="spinner"></div><div>Сканирование рынка...</div></div>';
            return;
        }

        el.innerHTML = signals.map((s, i) => {
            const pct = s.price_change_pct || 0;
            const tier = pct >= 50 ? 'mega' : pct >= 30 ? 'massive' : pct >= 15 ? 'strong' : 'early';
            const score = s.score || s.final_score || 0;
            const sc = score >= 90 ? 's' : score >= 80 ? 'a' : score >= 70 ? 'b' : 'c';
            const t = new Date(s.timestamp).toLocaleTimeString('ru-RU', {hour:'2-digit',minute:'2-digit',second:'2-digit'});
            const rsi = (s.rsi || 0).toFixed(0);
            const vol = (s.volume_ratio || 0).toFixed(1);
            const sym = (s.symbol || '').replace('_USDT','').replace('USDT','');
            const cls = (isNew && i === 0) ? ' new' : '';

            return `<div class="signal-row tier-${tier}${cls}">
                <div><div class="sym-name">${sym}</div><div class="sym-pair">USDT Perps</div></div>
                <div class="${pct >= 0 ? 'pct-up' : 'pct-dn'}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</div>
                <div style="color:var(--text-2)">RSI ${rsi}</div>
                <div style="color:var(--text-2)">Vol ${vol}x</div>
                <div><span class="score-pill score-${sc}">${score}/100</span></div>
                <div class="time-ago">${t}</div>
            </div>`;
        }).join('');
    }

    /* ===== UPDATE STATS ===== */
    function updateStats(s) {
        if (!s) return;
        document.getElementById('statActive').textContent = s.active_signals || 0;
        document.getElementById('statPumps').textContent = s.pumps_detected || 0;
        document.getElementById('statSignals').textContent = s.signals_generated || 0;
        document.getElementById('statSymbols').textContent = s.symbols_tracked || 0;
    }

    /* ===== UPDATE GAUGES ===== */
    function setGauge(ringId, valId, pct) {
        const circ = 213.6;
        const offset = circ - (circ * pct / 100);
        const ring = document.getElementById(ringId);
        const val = document.getElementById(valId);
        ring.style.strokeDashoffset = offset;
        val.textContent = pct.toFixed(0) + '%';
        // Color by severity
        const color = pct > 90 ? 'var(--red)' : pct > 70 ? 'var(--orange)' : 'var(--green)';
        ring.style.stroke = color;
        val.style.color = color;
    }

    /* ===== FETCH HEALTH ===== */
    async function fetchHealth() {
        try {
            const r = await fetch('/api/health');
            const h = await r.json();
            setGauge('cpuRing', 'cpuVal', h.cpu || 0);
            setGauge('ramRing', 'ramVal', h.ram_percent || 0);
            document.getElementById('uptimeVal').textContent = h.uptime_str || '--';
            document.getElementById('statClients').textContent = h.ws_clients || 0;
            document.getElementById('ramUsed').textContent = (h.ram_used_mb || 0) + ' / ' + (h.ram_total_mb || 0) + ' MB';

            const apiEl = document.getElementById('compApi');
            apiEl.textContent = h.api_ok ? '● Online' : '● Error';
            apiEl.className = h.api_ok ? 'comp-ok' : 'comp-err';

            const wsEl = document.getElementById('compWs');
            wsEl.textContent = h.ws_ok ? '● Online' : '● Error';
            wsEl.className = h.ws_ok ? 'comp-ok' : 'comp-err';
        } catch(e) {}
    }

    /* ===== FETCH WHALES ===== */
    async function fetchWhales() {
        try {
            const r = await fetch('/api/whales');
            const data = await r.json();
            const el = document.getElementById('whaleList');
            if (!data.length) { el.innerHTML = '<div class="empty-state">Нет активности</div>'; return; }

            el.innerHTML = data.slice(0,8).map(w => {
                const sym = w.symbol.replace('_USDT','').replace('USDT','');
                const amt = w.value_usd >= 1000000 ? (w.value_usd/1e6).toFixed(1)+'M' : (w.value_usd/1e3).toFixed(0)+'K';
                const side = w.side === 'BUY' ? 'buy' : 'sell';
                const ago = timeAgo(w.timestamp);
                return `<div class="feed-item">
                    <div class="feed-title"><span class="feed-badge ${side}">${w.side}</span> ${sym} — $${amt}</div>
                    <div class="feed-meta"><span>${w.category}</span><span>${ago}</span></div>
                </div>`;
            }).join('');
        } catch(e) {}
    }

    /* ===== FETCH NEWS ===== */
    async function fetchNews() {
        try {
            const r = await fetch('/api/news');
            const data = await r.json();
            const el = document.getElementById('newsList');
            if (!data.length) { el.innerHTML = '<div class="empty-state">Нет новостей</div>'; return; }

            el.innerHTML = data.slice(0,8).map(n => {
                const sClass = n.sentiment.includes('bullish') ? 'bullish' : n.sentiment.includes('bearish') ? 'bearish' : 'neutral';
                const ago = timeAgo(n.timestamp);
                const tokens = (n.tokens || []).map(t => '#'+t).join(' ');
                return `<div class="feed-item">
                    <div class="feed-title">${n.title.slice(0,80)}${n.title.length>80?'...':''}</div>
                    <div class="feed-meta">
                        <span class="feed-badge ${sClass}">${n.sentiment.replace('very_','')}</span>
                        <span>${n.source}</span>
                        <span>${tokens}</span>
                        <span>${ago}</span>
                    </div>
                </div>`;
            }).join('');
        } catch(e) {}
    }

    /* ===== HELPERS ===== */
    function timeAgo(ts) {
        const diff = (Date.now() - ts) / 1000;
        if (diff < 60) return Math.floor(diff) + 'с';
        if (diff < 3600) return Math.floor(diff/60) + ' мин';
        if (diff < 86400) return Math.floor(diff/3600) + 'ч';
        return Math.floor(diff/86400) + 'д';
    }

    function playAlert() {
        try { document.getElementById('alertSound').play().catch(()=>{}); } catch(e) {}
    }

    /* ===== INIT ===== */
    async function init() {
        connectWS();

        // Load signals
        try {
            const [sr, stR] = await Promise.all([
                fetch('/api/signals?limit=30'),
                fetch('/api/stats')
            ]);
            const sigs = await sr.json();
            const stats = await stR.json();
            sigs.forEach(s => signals.push(s));
            renderSignals(false);
            updateStats(stats);
        } catch(e) {}

        // Initial health + feeds
        fetchHealth();
        fetchWhales();
        fetchNews();

        // Periodic refreshes
        setInterval(fetchHealth, 10000);   // 10s health
        setInterval(fetchWhales, 30000);   // 30s whales
        setInterval(fetchNews, 60000);     // 60s news
        setInterval(async () => {
            try {
                const r = await fetch('/api/stats');
                updateStats(await r.json());
            } catch(e) {}
        }, 15000);
    }

    init();
    </script>
</body>
</html>"""


def run_dashboard(host: str = None, port: int = None):
    """Run the dashboard server"""
    host = host or config.dashboard.host
    port = port or config.dashboard.port
    uvicorn.run(app, host=host, port=port, log_level="info")

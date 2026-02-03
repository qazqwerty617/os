"""
MEXC Pump Monitor - Real-time Web Dashboard
FastAPI + WebSocket for live updates
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Set
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
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
        logger.info(f"Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients"""
        if not self.active_connections:
            return
        
        data = json.dumps(message)
        disconnected = set()
        
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception:
                disconnected.add(connection)
        
        # Remove disconnected clients
        self.active_connections -= disconnected


# Create FastAPI app
app = FastAPI(title="MEXC Pump Monitor", version="1.0.0")
manager = ConnectionManager()

# Store references to detector and analyzer (set by main.py)
detector = None
market_analyzer = None
mtf_analyzer = None


def set_components(pump_detector, mkt_analyzer, mtf_anlz):
    """Set component references for the dashboard"""
    global detector, market_analyzer, mtf_analyzer
    detector = pump_detector
    market_analyzer = mkt_analyzer
    mtf_analyzer = mtf_anlz


@app.get("/", response_class=HTMLResponse)
async def root():
    """Main dashboard page"""
    return get_dashboard_html()


@app.get("/api/stats")
async def get_stats():
    """Get detector statistics"""
    if detector:
        return detector.get_stats()
    return {}


@app.get("/api/signals")
async def get_signals(limit: int = 50):
    """Get recent signals"""
    if detector:
        signals = detector.get_signal_history(limit)
        return [s.to_dict() for s in signals]
    return []


@app.get("/api/active")
async def get_active():
    """Get currently active signals"""
    if detector:
        signals = detector.get_active_signals()
        return [s.to_dict() for s in signals]
    return []


@app.get("/api/funding")
async def get_extreme_funding():
    """Get extreme funding rates"""
    if market_analyzer:
        extreme = market_analyzer.get_extreme_funding_symbols()
        return [
            {'symbol': s, 'funding_rate': f.funding_rate, 'predicted': f.predicted_rate}
            for s, f in extreme[:20]
        ]
    return []


@app.get("/api/oi")
async def get_oi_changes():
    """Get high OI changes"""
    if market_analyzer:
        high_oi = market_analyzer.get_high_oi_change_symbols()
        return [
            {'symbol': s, 'oi_change_1h': o.oi_change_1h, 'oi_change_24h': o.oi_change_24h}
            for s, o in high_oi[:20]
        ]
    return []


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Send ping every 30 seconds
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping", "timestamp": time.time()})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


async def broadcast_signal(signal):
    """Broadcast new signal to all connected clients"""
    await manager.broadcast({
        "type": "signal",
        "data": signal.to_dict()
    })


async def broadcast_update():
    """Broadcast periodic market update"""
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
    """Generate dashboard HTML"""
    return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 MEXC Pump Monitor</title>
    <style>
        :root {
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-tertiary: #21262d;
            --text-primary: #f0f6fc;
            --text-secondary: #8b949e;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-orange: #d29922;
            --accent-blue: #58a6ff;
            --accent-purple: #a371f7;
            --gradient-fire: linear-gradient(135deg, #f85149, #d29922);
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--bg-tertiary);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            font-size: 1.5rem;
            font-weight: 700;
            background: var(--gradient-fire);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .status {
            display: flex;
            gap: 2rem;
            align-items: center;
        }
        
        .status-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .card {
            background: var(--bg-secondary);
            border-radius: 12px;
            padding: 1.5rem;
            border: 1px solid var(--bg-tertiary);
        }
        
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }
        
        .card-title {
            font-size: 1rem;
            color: var(--text-secondary);
        }
        
        .card-value {
            font-size: 2rem;
            font-weight: 700;
        }
        
        .signals-container {
            background: var(--bg-secondary);
            border-radius: 12px;
            border: 1px solid var(--bg-tertiary);
            overflow: hidden;
        }
        
        .signals-header {
            padding: 1rem 1.5rem;
            background: var(--bg-tertiary);
            font-weight: 600;
        }
        
        .signal-item {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--bg-tertiary);
            display: grid;
            grid-template-columns: 1fr 1fr 1fr 1fr 120px;
            gap: 1rem;
            align-items: center;
            transition: background 0.2s;
        }
        
        .signal-item:hover {
            background: var(--bg-tertiary);
        }
        
        .signal-item.mega {
            border-left: 4px solid var(--accent-red);
            animation: glow 2s infinite;
        }
        
        .signal-item.massive {
            border-left: 4px solid var(--accent-orange);
        }
        
        .signal-item.strong {
            border-left: 4px solid var(--accent-blue);
        }
        
        @keyframes glow {
            0%, 100% { box-shadow: 0 0 5px rgba(248, 81, 73, 0.3); }
            50% { box-shadow: 0 0 20px rgba(248, 81, 73, 0.6); }
        }
        
        .symbol {
            font-weight: 600;
            font-size: 1.1rem;
        }
        
        .change-positive {
            color: var(--accent-green);
            font-weight: 600;
        }
        
        .change-negative {
            color: var(--accent-red);
            font-weight: 600;
        }
        
        .score-badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-weight: 600;
            font-size: 0.85rem;
        }
        
        .score-high { background: rgba(63, 185, 80, 0.2); color: var(--accent-green); }
        .score-medium { background: rgba(210, 153, 34, 0.2); color: var(--accent-orange); }
        .score-low { background: rgba(139, 148, 158, 0.2); color: var(--text-secondary); }
        
        .time {
            color: var(--text-secondary);
            font-size: 0.85rem;
        }
        
        .no-signals {
            padding: 3rem;
            text-align: center;
            color: var(--text-secondary);
        }
        
        .ws-status {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
        }
        
        .ws-connected { color: var(--accent-green); }
        .ws-disconnected { color: var(--accent-red); }
    </style>
</head>
<body>
    <header class="header">
        <div class="logo">🔥 MEXC Pump Monitor</div>
        <div class="status">
            <div class="status-item">
                <div class="status-dot"></div>
                <span>Live</span>
            </div>
            <div class="ws-status" id="wsStatus">
                <span>Connecting...</span>
            </div>
        </div>
    </header>
    
    <div class="container">
        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Активные сигналы</span>
                </div>
                <div class="card-value" id="activeCount">0</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Всего за сессию</span>
                </div>
                <div class="card-value" id="totalSignals">0</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Пампов обнаружено</span>
                </div>
                <div class="card-value" id="pumpsDetected">0</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Пар отслеживается</span>
                </div>
                <div class="card-value" id="symbolsTracked">0</div>
            </div>
        </div>
        
        <div class="signals-container">
            <div class="signals-header">🎯 Последние сигналы</div>
            <div id="signalsList">
                <div class="no-signals">
                    Ожидание сигналов...
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let ws;
        const signals = [];
        
        function connectWebSocket() {
            const wsUrl = `ws://${window.location.host}/ws`;
            ws = new WebSocket(wsUrl);
            
            ws.onopen = () => {
                document.getElementById('wsStatus').innerHTML = 
                    '<span class="ws-connected">● Connected</span>';
            };
            
            ws.onclose = () => {
                document.getElementById('wsStatus').innerHTML = 
                    '<span class="ws-disconnected">● Disconnected</span>';
                setTimeout(connectWebSocket, 3000);
            };
            
            ws.onmessage = (event) => {
                const message = JSON.parse(event.data);
                
                if (message.type === 'signal') {
                    addSignal(message.data);
                    playSound();
                } else if (message.type === 'update') {
                    updateStats(message.stats);
                }
            };
        }
        
        function addSignal(signal) {
            signals.unshift(signal);
            if (signals.length > 50) signals.pop();
            renderSignals();
        }
        
        function renderSignals() {
            const container = document.getElementById('signalsList');
            
            if (signals.length === 0) {
                container.innerHTML = '<div class="no-signals">Ожидание сигналов...</div>';
                return;
            }
            
            container.innerHTML = signals.map(signal => {
                const tier = signal.price_change_pct >= 50 ? 'mega' : 
                            signal.price_change_pct >= 30 ? 'massive' : 'strong';
                const scoreClass = signal.score >= 80 ? 'score-high' : 
                                  signal.score >= 60 ? 'score-medium' : 'score-low';
                const time = new Date(signal.timestamp).toLocaleTimeString();
                
                return `
                    <div class="signal-item ${tier}">
                        <div class="symbol">${signal.symbol}</div>
                        <div class="change-positive">+${signal.price_change_pct.toFixed(2)}%</div>
                        <div>RSI: ${signal.rsi.toFixed(1)}</div>
                        <div class="score-badge ${scoreClass}">${signal.score}/100</div>
                        <div class="time">${time}</div>
                    </div>
                `;
            }).join('');
        }
        
        function updateStats(stats) {
            document.getElementById('activeCount').textContent = stats.active_signals || 0;
            document.getElementById('totalSignals').textContent = stats.signals_generated || 0;
            document.getElementById('pumpsDetected').textContent = stats.pumps_detected || 0;
            document.getElementById('symbolsTracked').textContent = stats.symbols_tracked || 0;
        }
        
        function playSound() {
            // Browser notification sound
            try {
                const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleqwQJqHEo09p');
                audio.volume = 0.3;
                audio.play().catch(() => {});
            } catch (e) {}
        }
        
        // Initial data load
        async function loadInitialData() {
            try {
                const [statsRes, signalsRes] = await Promise.all([
                    fetch('/api/stats'),
                    fetch('/api/signals?limit=20')
                ]);
                
                const stats = await statsRes.json();
                const initialSignals = await signalsRes.json();
                
                updateStats(stats);
                initialSignals.forEach(s => signals.push(s));
                renderSignals();
            } catch (e) {
                console.error('Failed to load initial data:', e);
            }
        }
        
        // Start
        loadInitialData();
        connectWebSocket();
        
        // Refresh stats every 30 seconds
        setInterval(async () => {
            try {
                const res = await fetch('/api/stats');
                const stats = await res.json();
                updateStats(stats);
            } catch (e) {}
        }, 30000);
    </script>
</body>
</html>
"""


def run_dashboard(host: str = None, port: int = None):
    """Run the dashboard server"""
    host = host or config.dashboard.host
    port = port or config.dashboard.port
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )

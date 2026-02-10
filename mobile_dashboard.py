"""
MEXC Pump Monitor - Mobile Dashboard
Мобильный веб-дашборд для телефона
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# HTML template for mobile dashboard
MOBILE_DASHBOARD_HTML = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#0a0a0f">
    <title>🚀 Pump Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a25;
            --text-primary: #ffffff;
            --text-secondary: #888899;
            --accent-green: #00ff88;
            --accent-red: #ff4466;
            --accent-yellow: #ffcc00;
            --accent-blue: #4488ff;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            padding: 16px;
            padding-bottom: 100px;
        }
        
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding: 12px 16px;
            background: var(--bg-card);
            border-radius: 16px;
        }
        
        .header h1 {
            font-size: 20px;
            font-weight: 700;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-green);
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-bottom: 20px;
        }
        
        .stat-card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 16px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 4px;
        }
        
        .stat-label {
            font-size: 12px;
            color: var(--text-secondary);
            text-transform: uppercase;
        }
        
        .stat-value.green { color: var(--accent-green); }
        .stat-value.red { color: var(--accent-red); }
        .stat-value.yellow { color: var(--accent-yellow); }
        .stat-value.blue { color: var(--accent-blue); }
        
        .section-title {
            font-size: 14px;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin: 20px 0 12px;
            padding-left: 4px;
        }
        
        .signal-list {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .signal-card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 16px;
            border-left: 4px solid var(--accent-green);
        }
        
        .signal-card.short {
            border-left-color: var(--accent-red);
        }
        
        .signal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }
        
        .signal-symbol {
            font-size: 18px;
            font-weight: 700;
        }
        
        .signal-change {
            font-size: 16px;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 8px;
            background: rgba(0, 255, 136, 0.15);
            color: var(--accent-green);
        }
        
        .signal-change.negative {
            background: rgba(255, 68, 102, 0.15);
            color: var(--accent-red);
        }
        
        .signal-details {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 8px;
        }
        
        .signal-detail {
            text-align: center;
        }
        
        .signal-detail-value {
            font-size: 14px;
            font-weight: 600;
        }
        
        .signal-detail-label {
            font-size: 10px;
            color: var(--text-secondary);
        }
        
        .news-card {
            background: var(--bg-card);
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 12px;
        }
        
        .news-signal {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .news-signal.long {
            background: rgba(0, 255, 136, 0.15);
            color: var(--accent-green);
        }
        
        .news-signal.short {
            background: rgba(255, 68, 102, 0.15);
            color: var(--accent-red);
        }
        
        .news-title {
            font-size: 14px;
            line-height: 1.4;
            margin-bottom: 8px;
        }
        
        .news-meta {
            font-size: 11px;
            color: var(--text-secondary);
        }
        
        .pnl-card {
            background: linear-gradient(135deg, var(--bg-card) 0%, rgba(0, 255, 136, 0.1) 100%);
            border-radius: 20px;
            padding: 24px;
            text-align: center;
            margin-bottom: 20px;
        }
        
        .pnl-card.negative {
            background: linear-gradient(135deg, var(--bg-card) 0%, rgba(255, 68, 102, 0.1) 100%);
        }
        
        .pnl-label {
            font-size: 12px;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 8px;
        }
        
        .pnl-value {
            font-size: 42px;
            font-weight: 700;
            color: var(--accent-green);
        }
        
        .pnl-card.negative .pnl-value {
            color: var(--accent-red);
        }
        
        .pnl-change {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
        }
        
        .bottom-nav {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: var(--bg-secondary);
            display: flex;
            justify-content: space-around;
            padding: 12px 0 28px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 4px;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 10px;
        }
        
        .nav-item.active {
            color: var(--accent-blue);
        }
        
        .nav-icon {
            font-size: 22px;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        .refresh-btn {
            position: fixed;
            top: 16px;
            right: 16px;
            background: var(--accent-blue);
            color: white;
            border: none;
            border-radius: 50%;
            width: 44px;
            height: 44px;
            font-size: 20px;
            cursor: pointer;
            z-index: 100;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: var(--text-secondary);
        }
        
        .loading-spinner {
            display: inline-block;
            width: 30px;
            height: 30px;
            border: 3px solid var(--bg-card);
            border-top-color: var(--accent-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: var(--text-secondary);
        }
        
        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }
    </style>
</head>
<body>
    <button class="refresh-btn" onclick="refreshData()">🔄</button>
    
    <div class="header">
        <h1>🚀 Pump Monitor</h1>
        <div class="status-dot" id="statusDot"></div>
    </div>
    
    <!-- Tab: Dashboard -->
    <div id="tabDashboard" class="tab-content active">
        <div class="pnl-card" id="pnlCard">
            <div class="pnl-label">Сегодня P&L</div>
            <div class="pnl-value" id="pnlValue">$0.00</div>
            <div class="pnl-change" id="pnlChange">0 сделок</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value green" id="statPumps">0</div>
                <div class="stat-label">Пампы</div>
            </div>
            <div class="stat-card">
                <div class="stat-value red" id="statSignals">0</div>
                <div class="stat-label">Сигналы</div>
            </div>
            <div class="stat-card">
                <div class="stat-value yellow" id="statWinrate">0%</div>
                <div class="stat-label">Винрейт</div>
            </div>
            <div class="stat-card">
                <div class="stat-value blue" id="statBalance">$0</div>
                <div class="stat-label">Баланс</div>
            </div>
        </div>
        
        <div class="section-title">🔥 Активные сигналы</div>
        <div id="signalsList" class="signal-list">
            <div class="loading">
                <div class="loading-spinner"></div>
                <p>Загрузка...</p>
            </div>
        </div>
    </div>
    
    <!-- Tab: Signals -->
    <div id="tabSignals" class="tab-content">
        <div class="section-title">📊 Все сигналы</div>
        <div id="allSignalsList" class="signal-list"></div>
    </div>
    
    <!-- Tab: News -->
    <div id="tabNews" class="tab-content">
        <div class="section-title">📰 Крипто новости</div>
        <div id="newsList"></div>
    </div>
    
    <!-- Tab: Stats -->
    <div id="tabStats" class="tab-content">
        <div class="section-title">📈 Статистика</div>
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="totalTrades">0</div>
                <div class="stat-label">Всего сделок</div>
            </div>
            <div class="stat-card">
                <div class="stat-value green" id="totalWins">0</div>
                <div class="stat-label">Выигрышей</div>
            </div>
            <div class="stat-card">
                <div class="stat-value red" id="totalLosses">0</div>
                <div class="stat-label">Проигрышей</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="profitFactor">0</div>
                <div class="stat-label">Profit Factor</div>
            </div>
        </div>
        
        <div class="pnl-card" id="allTimePnl">
            <div class="pnl-label">Общий P&L</div>
            <div class="pnl-value" id="allTimePnlValue">$0.00</div>
            <div class="pnl-change" id="allTimePnlPct">0%</div>
        </div>
        <div class="section-title">📉 История баланса</div>
        <div class="stat-card" style="padding:8px;">
            <canvas id="pnlChart" width="100%" height="120" style="width:100%;height:120px;border-radius:8px;"></canvas>
        </div>
        <button class="refresh-btn" style="top:auto;bottom:80px;left:16px;right:auto;" onclick="exportTrades()">📥 Экспорт</button>
    </div>
    
    <nav class="bottom-nav">
        <a href="#" class="nav-item active" onclick="switchTab('Dashboard')">
            <span class="nav-icon">📊</span>
            <span>Главная</span>
        </a>
        <a href="#" class="nav-item" onclick="switchTab('Signals')">
            <span class="nav-icon">🎯</span>
            <span>Сигналы</span>
        </a>
        <a href="#" class="nav-item" onclick="switchTab('News')">
            <span class="nav-icon">📰</span>
            <span>Новости</span>
        </a>
        <a href="#" class="nav-item" onclick="switchTab('Stats')">
            <span class="nav-icon">📈</span>
            <span>Статы</span>
        </a>
    </nav>
    
    <script>
        // State
        let currentTab = 'Dashboard';
        let data = {
            pnl: { today: 0, allTime: 0, trades: 0 },
            stats: { pumps: 0, signals: 0, winrate: 0, balance: 100 },
            signals: [],
            news: [],
            pnlHistory: []
        };
        
        // Switch tabs
        function switchTab(tab) {
            currentTab = tab;
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            document.getElementById('tab' + tab).classList.add('active');
            event.target.closest('.nav-item').classList.add('active');
        }
        
        // Render signal card
        function renderSignal(signal) {
            const isShort = signal.side === 'SHORT';
            const changeClass = signal.pnl >= 0 ? '' : 'negative';
            
            return `
                <div class="signal-card ${isShort ? 'short' : ''}">
                    <div class="signal-header">
                        <span class="signal-symbol">${signal.symbol}</span>
                        <span class="signal-change ${changeClass}">${signal.change >= 0 ? '+' : ''}${signal.change.toFixed(1)}%</span>
                    </div>
                    <div class="signal-details">
                        <div class="signal-detail">
                            <div class="signal-detail-value">${signal.score}</div>
                            <div class="signal-detail-label">Score</div>
                        </div>
                        <div class="signal-detail">
                            <div class="signal-detail-value">${signal.rsi.toFixed(0)}</div>
                            <div class="signal-detail-label">RSI</div>
                        </div>
                        <div class="signal-detail">
                            <div class="signal-detail-value">${signal.volume.toFixed(1)}x</div>
                            <div class="signal-detail-label">Vol</div>
                        </div>
                    </div>
                </div>
            `;
        }
        
        // Render news card
        function renderNews(news) {
            const signalClass = news.signal.includes('LONG') ? 'long' : 
                               news.signal.includes('SHORT') ? 'short' : '';
            
            return `
                <div class="news-card">
                    <span class="news-signal ${signalClass}">${news.signal}</span>
                    <div class="news-title">${news.title}</div>
                    <div class="news-meta">${news.source} • ${news.time}</div>
                </div>
            `;
        }
        
        // Update UI
        function updateUI() {
            // PnL
            const pnlCard = document.getElementById('pnlCard');
            const pnlValue = document.getElementById('pnlValue');
            pnlValue.textContent = `$${data.pnl.today >= 0 ? '+' : ''}${data.pnl.today.toFixed(2)}`;
            pnlCard.classList.toggle('negative', data.pnl.today < 0);
            document.getElementById('pnlChange').textContent = `${data.pnl.trades} сделок сегодня`;
            
            // Stats
            document.getElementById('statPumps').textContent = data.stats.pumps;
            document.getElementById('statSignals').textContent = data.stats.signals;
            document.getElementById('statWinrate').textContent = data.stats.winrate + '%';
            document.getElementById('statBalance').textContent = '$' + data.stats.balance.toFixed(0);
            
            // Signals
            const signalsList = document.getElementById('signalsList');
            if (data.signals.length > 0) {
                signalsList.innerHTML = data.signals.slice(0, 5).map(renderSignal).join('');
            } else {
                signalsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📭</div>
                        <p>Нет активных сигналов</p>
                    </div>
                `;
            }
            
            // All signals
            const allSignalsList = document.getElementById('allSignalsList');
            allSignalsList.innerHTML = data.signals.map(renderSignal).join('');
            
            // News
            const newsList = document.getElementById('newsList');
            if (data.news.length > 0) {
                newsList.innerHTML = data.news.map(renderNews).join('');
            } else {
                newsList.innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">📰</div>
                        <p>Нет новостей</p>
                    </div>
                `;
            }
            
            // All-time stats
            document.getElementById('totalTrades').textContent = data.stats.totalTrades || 0;
            document.getElementById('totalWins').textContent = data.stats.wins || 0;
            document.getElementById('totalLosses').textContent = data.stats.losses || 0;
            document.getElementById('profitFactor').textContent = (data.stats.profitFactor || 0).toFixed(2);
            
            const allTimePnlCard = document.getElementById('allTimePnl');
            document.getElementById('allTimePnlValue').textContent = 
                `$${data.pnl.allTime >= 0 ? '+' : ''}${data.pnl.allTime.toFixed(2)}`;
            allTimePnlCard.classList.toggle('negative', data.pnl.allTime < 0);
            drawPnlChart();
        }
        
        function drawPnlChart() {
            const h = data.pnlHistory || [];
            if (h.length < 2) return;
            const c = document.getElementById('pnlChart');
            if (!c) return;
            const ctx = c.getContext('2d');
            const w = c.offsetWidth, H = 120;
            c.width = w; c.height = H;
            const vals = h.map(x => x.balance);
            const min = Math.min(...vals), max = Math.max(...vals);
            const range = max - min || 1;
            ctx.fillStyle = '#1a1a25';
            ctx.fillRect(0, 0, w, H);
            ctx.strokeStyle = data.stats.balance >= (min + max)/2 ? '#00ff88' : '#ff4466';
            ctx.lineWidth = 2;
            ctx.beginPath();
            for (let i = 0; i < vals.length; i++) {
                const x = (i / (vals.length - 1)) * (w - 4) + 2;
                const y = H - 4 - ((vals[i] - min) / range) * (H - 8);
                if (i === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }
        
        async function exportTrades() {
            try {
                const r = await fetch('/api/mobile/export?format=csv');
                const blob = await r.blob();
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'trades_' + new Date().toISOString().slice(0,10) + '.csv';
                a.click();
            } catch (e) { alert('Ошибка экспорта'); }
        }
        
        async function fetchData() {
            try {
                const response = await fetch('/api/mobile/data');
                if (response.ok) {
                    data = await response.json();
                    updateUI();
                }
            } catch (e) {
                console.error('API Error:', e);
                document.getElementById('signalsList').innerHTML = '<div class="empty-state"><p>Ошибка загрузки данных</p></div>';
            }
        }
        
        function connectWebSocket() {
            const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const ws = new WebSocket(wsProto + '//' + location.host + '/api/mobile/ws');
            ws.onmessage = (e) => {
                try {
                    data = JSON.parse(e.data);
                    updateUI();
                } catch (err) {}
            };
            ws.onclose = () => setTimeout(connectWebSocket, 5000);
            ws.onerror = () => ws.close();
        }
        
        function refreshData() {
            document.getElementById('signalsList').innerHTML = '<div class="loading"><div class="loading-spinner"></div><p>Обновление...</p></div>';
            fetchData();
        }
        
        fetchData();
        connectWebSocket();
    </script>
</body>
</html>
'''


class MobileDashboard:
    """
    Мобильный веб-дашборд
    
    Оптимизирован под телефоны:
    - Адаптивный дизайн
    - Тёмная тема
    - Bottom navigation
    - Pull to refresh
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8081):
        self.host = host
        self.port = port
        
        # Data storage
        self.data = {
            'pnl': {'today': 0, 'allTime': 0, 'trades': 0},
            'stats': {
                'pumps': 0,
                'signals': 0,
                'winrate': 0,
                'balance': 100,
                'totalTrades': 0,
                'wins': 0,
                'losses': 0,
                'profitFactor': 0
            },
            'signals': [],
            'news': [],
            'pnlHistory': [],
            'trades': []
        }
        
        self.app = None
        self.runner = None
        self._ws_clients: set = set()
    
    async def _broadcast_ws(self):
        """Push data to all WebSocket clients"""
        if not self._ws_clients:
            return
        msg = json.dumps(self.data, default=str)
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._ws_clients.discard(ws)
    
    def update_pnl(self, today: float, all_time: float, trades: int, balance: float = None):
        """Обновить P&L данные"""
        self.data['pnl'] = {
            'today': today,
            'allTime': all_time,
            'trades': trades
        }
        if balance is not None:
            hist = self.data.setdefault('pnlHistory', [])
            hist.append({'ts': datetime.now().isoformat(), 'balance': balance, 'pnl': all_time})
            self.data['pnlHistory'] = hist[-200:]
    
    def update_stats(
        self,
        pumps: int = None,
        signals: int = None,
        winrate: float = None,
        balance: float = None,
        total_trades: int = None,
        wins: int = None,
        losses: int = None,
        profit_factor: float = None
    ):
        """Обновить статистику"""
        if pumps is not None:
            self.data['stats']['pumps'] = pumps
        if signals is not None:
            self.data['stats']['signals'] = signals
        if winrate is not None:
            self.data['stats']['winrate'] = winrate
        if balance is not None:
            self.data['stats']['balance'] = balance
        if total_trades is not None:
            self.data['stats']['totalTrades'] = total_trades
        if wins is not None:
            self.data['stats']['wins'] = wins
        if losses is not None:
            self.data['stats']['losses'] = losses
        if profit_factor is not None:
            self.data['stats']['profitFactor'] = profit_factor
        
        # Debug logging
        logger.debug(f"📱 Dashboard updated: balance=${balance}, pumps={pumps}, trades={total_trades}")
    
    def add_signal(
        self,
        symbol: str,
        side: str,
        change: float,
        score: int,
        rsi: float,
        volume: float,
        pnl: float = 0
    ):
        """Добавить сигнал"""
        signal = {
            'symbol': symbol,
            'side': side,
            'change': change,
            'score': score,
            'rsi': rsi,
            'volume': volume,
            'pnl': pnl,
            'time': datetime.now().isoformat()
        }
        
        self.data['signals'].insert(0, signal)
        
        # Ограничить до 50 сигналов
        self.data['signals'] = self.data['signals'][:50]
    
    def add_news(self, signal: str, title: str, source: str, time_ago: str):
        """Добавить новость"""
        news = {
            'signal': signal,
            'title': title,
            'source': source,
            'time': time_ago
        }
        
        self.data['news'].insert(0, news)
        self.data['news'] = self.data['news'][:20]
    
    async def start(self):
        """Запустить веб-сервер"""
        try:
            from aiohttp import web
        except ImportError:
            logger.warning("aiohttp not installed, mobile dashboard disabled")
            return
        
        self.app = web.Application()
        
        self.app.router.add_get('/', self._handle_index)
        self.app.router.add_get('/mobile', self._handle_index)
        self.app.router.add_get('/api/mobile/data', self._handle_api_data)
        self.app.router.add_get('/api/mobile/export', self._handle_export)
        self.app.router.add_get('/api/mobile/ws', self._handle_ws)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        # Try to bind to port, if fails, try next few ports
        for i in range(5):
             try:
                 site = web.TCPSite(self.runner, self.host, self.port + i)
                 await site.start()
                 self.port = self.port + i
                 logger.info(f"📱 Mobile Dashboard: http://localhost:{self.port}/mobile")
                 return
             except OSError:
                 logger.warning(f"Port {self.port + i} in use, trying next...")
        
        logger.error("Could not find open port for Mobile Dashboard")
    
    async def _handle_index(self, request):
        """Отдать HTML страницу"""
        from aiohttp import web
        return web.Response(text=MOBILE_DASHBOARD_HTML, content_type='text/html')
    
    async def _handle_api_data(self, request):
        from aiohttp import web
        return web.json_response(self.data)
    
    async def _handle_export(self, request):
        from aiohttp import web
        fmt = request.query.get('format', 'csv')
        trades = self.data.get('trades', [])
        if fmt == 'csv':
            lines = ['symbol,side,entry,qty,pnl,time']
            for t in trades:
                lines.append(f"{t.get('symbol','')},{t.get('side','')},{t.get('entry',0)},{t.get('qty',0)},{t.get('pnl',0)},{t.get('time','')}")
            body = '\n'.join(lines)
            return web.Response(text=body, content_type='text/csv', headers={
                'Content-Disposition': 'attachment; filename="trades.csv"'
            })
        return web.json_response(trades)
    
    async def _handle_ws(self, request):
        from aiohttp import web
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        try:
            await ws.send_str(json.dumps(self.data, default=str))
            async for _ in ws:
                pass
        finally:
            self._ws_clients.discard(ws)
        return ws
    
    async def stop(self):
        """Остановить сервер"""
        if self.runner:
            await self.runner.cleanup()

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
    <meta name="theme-color" content="#06080d">
    <title>🚀 Pump Monitor Pro</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-0: #06080d;
            --bg-1: #0c1019;
            --bg-2: #131926;
            --bg-3: #1a2236;
            --glass: rgba(16, 22, 36, 0.7);
            --glass-border: rgba(255,255,255,0.06);
            --glass-highlight: rgba(255,255,255,0.03);
            --text-1: #f0f4ff;
            --text-2: #8899bb;
            --text-3: #4a5578;
            --green: #00e676;
            --green-bg: rgba(0,230,118,0.1);
            --green-glow: rgba(0,230,118,0.25);
            --red: #ff3d57;
            --red-bg: rgba(255,61,87,0.1);
            --red-glow: rgba(255,61,87,0.25);
            --orange: #ffab00;
            --orange-bg: rgba(255,171,0,0.1);
            --blue: #448aff;
            --blue-bg: rgba(68,138,255,0.1);
            --purple: #b388ff;
            --purple-bg: rgba(179,136,255,0.1);
            --cyan: #18ffff;
            --gradient-brand: linear-gradient(135deg, #ff3d57 0%, #ff8a00 50%, #ffab00 100%);
            --gradient-card: linear-gradient(165deg, rgba(25,35,60,0.6) 0%, rgba(12,16,25,0.85) 100%);
            --radius: 16px;
            --nav-h: 72px;
        }

        * { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color: transparent; }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-0);
            color: var(--text-1);
            min-height: 100vh;
            overflow-x: hidden;
            padding-bottom: calc(var(--nav-h) + 16px);
        }

        /* Animated BG */
        body::before {
            content: '';
            position: fixed; inset: 0;
            background:
                radial-gradient(ellipse 300px 250px at 20% 30%, rgba(68,138,255,0.07), transparent 70%),
                radial-gradient(ellipse 250px 200px at 80% 60%, rgba(255,61,87,0.05), transparent 70%);
            pointer-events: none;
            z-index: 0;
            animation: bgFloat 15s ease-in-out infinite alternate;
        }
        @keyframes bgFloat {
            from { transform: translate(0,0) scale(1); }
            to { transform: translate(-10px,8px) scale(1.03); }
        }

        /* === HEADER === */
        .header {
            position: sticky; top: 0; z-index: 100;
            background: rgba(6,8,13,0.88);
            backdrop-filter: blur(24px) saturate(180%);
            -webkit-backdrop-filter: blur(24px) saturate(180%);
            border-bottom: 1px solid var(--glass-border);
            padding: 0 16px;
            height: 56px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .logo {
            display: flex; align-items: center; gap: 10px;
        }
        .logo-icon {
            width: 32px; height: 32px;
            border-radius: 9px;
            background: var(--gradient-brand);
            display: flex; align-items: center; justify-content: center;
            font-size: 0.95rem;
            box-shadow: 0 3px 12px rgba(255,61,87,0.3);
        }
        .logo-text {
            font-size: 1.05rem; font-weight: 800;
            background: var(--gradient-brand);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .header-badges {
            display: flex; align-items: center; gap: 10px;
        }
        .live-pill {
            display: flex; align-items: center; gap: 5px;
            background: var(--green-bg);
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.65rem; font-weight: 700;
            color: var(--green);
            border: 1px solid rgba(0,230,118,0.12);
        }
        .dot-live {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: var(--green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%,100% { box-shadow: 0 0 0 0 var(--green-glow); }
            50% { box-shadow: 0 0 0 5px transparent; }
        }
        .clock {
            font-size: 0.72rem; font-weight: 600;
            color: var(--text-2);
            font-variant-numeric: tabular-nums;
        }

        /* === MAIN WRAP === */
        .main {
            position: relative; z-index: 1;
            padding: 12px 14px;
        }

        /* === PNL HERO === */
        .pnl-hero {
            position: relative;
            background: var(--gradient-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 20px;
            padding: 24px 20px;
            margin-bottom: 14px;
            text-align: center;
            overflow: hidden;
        }
        .pnl-hero::before {
            content: '';
            position: absolute; inset: 0;
            border-radius: 20px;
            padding: 1px;
            background: linear-gradient(160deg, rgba(255,255,255,0.08), transparent 40%);
            -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
            -webkit-mask-composite: xor;
            mask-composite: exclude;
            pointer-events: none;
        }
        .pnl-label {
            font-size: 0.65rem; font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: var(--text-3);
            margin-bottom: 6px;
        }
        .pnl-value {
            font-size: 2.8rem; font-weight: 900;
            letter-spacing: -2px;
            color: var(--green);
            text-shadow: 0 0 30px var(--green-glow);
            font-variant-numeric: tabular-nums;
            line-height: 1.1;
        }
        .pnl-hero.negative .pnl-value {
            color: var(--red);
            text-shadow: 0 0 30px var(--red-glow);
        }
        .pnl-trades {
            font-size: 0.72rem; font-weight: 500;
            color: var(--text-3);
            margin-top: 6px;
        }

        /* === STAT GRID === */
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 14px;
        }
        .stat-mini {
            background: var(--gradient-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            padding: 12px 8px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }
        .stat-mini::after {
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 2px;
            border-radius: 14px 14px 0 0;
        }
        .stat-mini.g::after { background: var(--green); }
        .stat-mini.r::after { background: var(--red); }
        .stat-mini.o::after { background: var(--orange); }
        .stat-mini.b::after { background: var(--blue); }
        .stat-num {
            font-size: 1.3rem; font-weight: 800;
            font-variant-numeric: tabular-nums;
            line-height: 1.2;
        }
        .stat-num.green { color: var(--green); }
        .stat-num.red { color: var(--red); }
        .stat-num.orange { color: var(--orange); }
        .stat-num.blue { color: var(--blue); }
        .stat-lbl {
            font-size: 0.55rem; font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-3);
            margin-top: 2px;
        }

        /* === SECTION === */
        .section-head {
            font-size: 0.72rem; font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 1.2px;
            color: var(--text-3);
            padding: 14px 4px 8px;
            display: flex; align-items: center; gap: 6px;
        }
        .section-badge {
            font-size: 0.6rem; font-weight: 700;
            background: var(--blue-bg);
            color: var(--blue);
            padding: 1px 7px;
            border-radius: 8px;
        }

        /* === GLASS CARD === */
        .glass {
            background: var(--gradient-card);
            backdrop-filter: blur(12px);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            overflow: hidden;
            margin-bottom: 10px;
        }

        /* === SIGNAL CARD === */
        .sig-card {
            padding: 14px 16px;
            border-bottom: 1px solid var(--glass-border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.15s;
        }
        .sig-card:active { background: var(--glass-highlight); }
        .sig-card.long { border-left: 3px solid var(--green); }
        .sig-card.short { border-left: 3px solid var(--red); }
        .sig-left { flex: 1; }
        .sig-sym {
            font-size: 0.95rem; font-weight: 700;
            margin-bottom: 2px;
        }
        .sig-meta {
            display: flex; gap: 10px;
            font-size: 0.68rem; color: var(--text-3);
        }
        .sig-right {
            text-align: right;
        }
        .sig-change {
            font-size: 0.95rem; font-weight: 700;
            margin-bottom: 2px;
        }
        .sig-change.up { color: var(--green); }
        .sig-change.dn { color: var(--red); }
        .sig-score {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 0.6rem; font-weight: 700;
        }
        .score-s { background: var(--green-bg); color: var(--green); }
        .score-a { background: var(--blue-bg); color: var(--blue); }
        .score-b { background: var(--orange-bg); color: var(--orange); }
        .score-c { background: rgba(255,255,255,0.06); color: var(--text-3); }

        @keyframes sigSlide {
            from { transform: translateX(-10px); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        .sig-card.fresh { animation: sigSlide 0.35s ease; }

        /* === NEWS CARD === */
        .news-item {
            padding: 12px 16px;
            border-bottom: 1px solid var(--glass-border);
        }
        .news-item:active { background: var(--glass-highlight); }
        .news-top {
            display: flex; gap: 6px; align-items: center;
            margin-bottom: 5px;
        }
        .news-badge {
            font-size: 0.55rem; font-weight: 700;
            text-transform: uppercase;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .news-badge.long { background: var(--green-bg); color: var(--green); }
        .news-badge.short { background: var(--red-bg); color: var(--red); }
        .news-badge.neutral { background: rgba(255,255,255,0.05); color: var(--text-3); }
        .news-title {
            font-size: 0.78rem; font-weight: 600;
            line-height: 1.4;
            color: var(--text-1);
        }
        .news-footer {
            font-size: 0.62rem; color: var(--text-3);
            margin-top: 4px;
        }

        /* === STATS TAB === */
        .stats-detail-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-bottom: 14px;
        }
        .detail-card {
            background: var(--gradient-card);
            border: 1px solid var(--glass-border);
            border-radius: 14px;
            padding: 16px;
            text-align: center;
        }
        .detail-val {
            font-size: 1.5rem; font-weight: 800;
            font-variant-numeric: tabular-nums;
        }
        .detail-lbl {
            font-size: 0.62rem; font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-3);
            margin-top: 4px;
        }

        /* Chart Canvas */
        .chart-wrap {
            background: var(--gradient-card);
            border: 1px solid var(--glass-border);
            border-radius: var(--radius);
            padding: 12px;
            margin-bottom: 14px;
        }
        .chart-wrap canvas {
            width: 100%; height: 140px;
            border-radius: 8px;
        }

        /* === EMPTY STATE === */
        .empty {
            text-align: center;
            padding: 32px 20px;
            color: var(--text-3);
        }
        .empty-icon {
            font-size: 2.5rem;
            margin-bottom: 10px;
            opacity: 0.5;
        }
        .empty-text {
            font-size: 0.78rem;
        }
        .spinner {
            display: inline-block;
            width: 24px; height: 24px;
            border: 2px solid var(--bg-3);
            border-top-color: var(--blue);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-bottom: 10px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* === TAB CONTENT === */
        .tab { display: none; }
        .tab.on { display: block; }

        /* === BOTTOM NAV === */
        .nav {
            position: fixed; bottom: 0; left: 0; right: 0;
            z-index: 100;
            height: var(--nav-h);
            background: rgba(6, 8, 13, 0.92);
            backdrop-filter: blur(24px) saturate(180%);
            -webkit-backdrop-filter: blur(24px) saturate(180%);
            border-top: 1px solid var(--glass-border);
            display: flex;
            justify-content: space-around;
            align-items: flex-start;
            padding-top: 8px;
        }
        .nav-btn {
            display: flex; flex-direction: column; align-items: center; gap: 3px;
            background: none; border: none;
            color: var(--text-3);
            font-size: 0.58rem; font-weight: 600;
            cursor: pointer;
            padding: 4px 12px;
            transition: color 0.2s;
            -webkit-tap-highlight-color: transparent;
        }
        .nav-btn.on { color: var(--blue); }
        .nav-ico { font-size: 1.3rem; }

        /* Refresh FAB */
        .fab {
            position: fixed;
            top: 62px; right: 14px;
            z-index: 90;
            width: 38px; height: 38px;
            border-radius: 50%;
            background: var(--bg-2);
            border: 1px solid var(--glass-border);
            color: var(--blue);
            font-size: 1.1rem;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer;
            box-shadow: 0 4px 16px rgba(0,0,0,0.4);
            transition: transform 0.3s;
        }
        .fab:active { transform: rotate(180deg) scale(0.9); }

        /* === SIGNAL DETAIL MODAL === */
        .modal-backdrop {
            position: fixed; inset: 0;
            background: rgba(0,0,0,0.6);
            backdrop-filter: blur(6px);
            -webkit-backdrop-filter: blur(6px);
            z-index: 200;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.25s;
        }
        .modal-backdrop.show {
            opacity: 1;
            pointer-events: auto;
        }
        .modal-sheet {
            position: fixed; bottom: 0; left: 0; right: 0;
            z-index: 201;
            background: var(--bg-1);
            border-radius: 20px 20px 0 0;
            padding: 20px;
            padding-bottom: calc(20px + env(safe-area-inset-bottom, 0));
            transform: translateY(100%);
            transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1);
            max-height: 70vh;
            overflow-y: auto;
        }
        .modal-backdrop.show .modal-sheet {
            transform: translateY(0);
        }
        .modal-handle {
            width: 36px; height: 4px;
            background: rgba(255,255,255,0.15);
            border-radius: 2px;
            margin: 0 auto 16px;
        }
        .modal-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 16px;
        }
        .modal-sym {
            font-size: 1.4rem; font-weight: 800;
        }
        .modal-side {
            padding: 4px 12px;
            border-radius: 8px;
            font-size: 0.72rem; font-weight: 700;
        }
        .modal-side.long { background: var(--green-bg); color: var(--green); }
        .modal-side.short { background: var(--red-bg); color: var(--red); }
        .modal-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-bottom: 16px;
        }
        .modal-item {
            background: var(--gradient-card);
            border: 1px solid var(--glass-border);
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }
        .modal-item-val {
            font-size: 1.2rem; font-weight: 700;
            font-variant-numeric: tabular-nums;
        }
        .modal-item-lbl {
            font-size: 0.6rem; font-weight: 600;
            color: var(--text-3);
            text-transform: uppercase;
            margin-top: 2px;
        }
        .live-dot-sm {
            display: inline-block;
            width: 6px; height: 6px;
            border-radius: 50%;
            background: #00e5ff;
            margin-right: 4px;
            vertical-align: middle;
            animation: livePulse 1.5s infinite;
        }
        @keyframes livePulse {
            0%, 100% { opacity: 1; box-shadow: 0 0 4px #00e5ff; }
            50% { opacity: 0.4; box-shadow: none; }
        }
        .modal-mexc-btn {
            display: block;
            width: 100%;
            padding: 14px;
            border: none;
            border-radius: 12px;
            background: var(--gradient-brand);
            color: white;
            font-size: 0.85rem;
            font-weight: 700;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
        }

        /* Clickable news */
        .news-item { cursor: pointer; }
        .news-item:hover .news-title { color: var(--blue); }
        .news-link-icon {
            font-size: 0.55rem; color: var(--text-3);
            margin-left: auto;
        }
    </style>
</head>
<body>
    <!-- SIGNAL DETAIL MODAL -->
    <div class="modal-backdrop" id="sigModal" onclick="closeModal(event)">
        <div class="modal-sheet" onclick="event.stopPropagation()">
            <div class="modal-handle"></div>
            <div class="modal-header">
                <span class="modal-sym" id="mdSym">--</span>
                <span class="modal-side" id="mdSide">--</span>
            </div>
            <div class="modal-grid">
                <div class="modal-item">
                    <div class="modal-item-val" id="mdChange" style="color:var(--green)">0%</div>
                    <div class="modal-item-lbl">Изменение</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdScore" style="color:var(--blue)">0</div>
                    <div class="modal-item-lbl">Score</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdEntry" style="color:var(--text-1)">--</div>
                    <div class="modal-item-lbl">📍 Точка входа</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdLive" style="color:var(--cyan, #00e5ff)"><span class="live-dot-sm"></span>--</div>
                    <div class="modal-item-lbl">💹 Цена LIVE</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdRsi" style="color:var(--orange)">0</div>
                    <div class="modal-item-lbl">RSI</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdVol" style="color:var(--purple)">0x</div>
                    <div class="modal-item-lbl">Объём</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdPnl">$0</div>
                    <div class="modal-item-lbl">P&L</div>
                </div>
                <div class="modal-item">
                    <div class="modal-item-val" id="mdTime" style="color:var(--text-2)">--</div>
                    <div class="modal-item-lbl">Время</div>
                </div>
            </div>
            <a class="modal-mexc-btn" id="mdLink" href="#" target="_blank">
                📈 Открыть на MEXC
            </a>
        </div>
    </div>

    <!-- HEADER -->
    <header class="header">
        <div class="logo">
            <div class="logo-icon">🔥</div>
            <div class="logo-text">PUMP MONITOR</div>
        </div>
        <div class="header-badges">
            <div class="live-pill"><div class="dot-live"></div>LIVE</div>
            <div class="clock" id="clock">--:--</div>
        </div>
    </header>

    <button class="fab" onclick="refreshData()" id="fabBtn">🔄</button>

    <div class="main">
        <!-- TAB: DASHBOARD -->
        <div id="tabDashboard" class="tab on">
            <div class="pnl-hero" id="pnlCard">
                <div class="pnl-label">Сегодня P&L</div>
                <div class="pnl-value" id="pnlValue">$0.00</div>
                <div class="pnl-trades" id="pnlChange">0 сделок</div>
            </div>

            <div class="stat-grid">
                <div class="stat-mini g">
                    <div class="stat-num green" id="statPumps">0</div>
                    <div class="stat-lbl">Пампы</div>
                </div>
                <div class="stat-mini r">
                    <div class="stat-num red" id="statSignals">0</div>
                    <div class="stat-lbl">Сигналы</div>
                </div>
                <div class="stat-mini o">
                    <div class="stat-num orange" id="statWinrate">0%</div>
                    <div class="stat-lbl">Винрейт</div>
                </div>
                <div class="stat-mini b">
                    <div class="stat-num blue" id="statBalance">$0</div>
                    <div class="stat-lbl">Баланс</div>
                </div>
            </div>

            <div class="section-head">🔥 Активные сигналы <span class="section-badge" id="sigBadge">0</span></div>
            <div class="glass" id="signalsList">
                <div class="empty"><div class="spinner"></div><div class="empty-text">Сканирование рынка...</div></div>
            </div>
        </div>

        <!-- TAB: SIGNALS -->
        <div id="tabSignals" class="tab">
            <div class="section-head">📊 Все сигналы</div>
            <div class="glass" id="allSignalsList">
                <div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Нет сигналов</div></div>
            </div>
        </div>

        <!-- TAB: NEWS -->
        <div id="tabNews" class="tab">
            <div class="section-head">📰 Крипто новости</div>
            <div class="glass" id="newsList">
                <div class="empty"><div class="empty-icon">📰</div><div class="empty-text">Загрузка...</div></div>
            </div>
        </div>

        <!-- TAB: STATS -->
        <div id="tabStats" class="tab">
            <div class="section-head">📈 Статистика</div>
            <div class="stats-detail-grid">
                <div class="detail-card">
                    <div class="detail-val" id="totalTrades" style="color:var(--text-1)">0</div>
                    <div class="detail-lbl">Всего сделок</div>
                </div>
                <div class="detail-card">
                    <div class="detail-val" id="totalWins" style="color:var(--green)">0</div>
                    <div class="detail-lbl">Выигрышей</div>
                </div>
                <div class="detail-card">
                    <div class="detail-val" id="totalLosses" style="color:var(--red)">0</div>
                    <div class="detail-lbl">Проигрышей</div>
                </div>
                <div class="detail-card">
                    <div class="detail-val" id="profitFactor" style="color:var(--orange)">0</div>
                    <div class="detail-lbl">Profit Factor</div>
                </div>
            </div>

            <div class="pnl-hero" id="allTimePnl">
                <div class="pnl-label">Общий P&L</div>
                <div class="pnl-value" id="allTimePnlValue">$0.00</div>
                <div class="pnl-trades" id="allTimePnlPct">0%</div>
            </div>

            <div class="section-head">📉 История баланса</div>
            <div class="chart-wrap">
                <canvas id="pnlChart"></canvas>
            </div>
        </div>
    </div>

    <!-- BOTTOM NAV -->
    <nav class="nav">
        <button class="nav-btn on" data-tab="Dashboard" onclick="switchTab(this)">
            <span class="nav-ico">📊</span><span>Главная</span>
        </button>
        <button class="nav-btn" data-tab="Signals" onclick="switchTab(this)">
            <span class="nav-ico">🎯</span><span>Сигналы</span>
        </button>
        <button class="nav-btn" data-tab="News" onclick="switchTab(this)">
            <span class="nav-ico">📰</span><span>Новости</span>
        </button>
        <button class="nav-btn" data-tab="Stats" onclick="switchTab(this)">
            <span class="nav-ico">📈</span><span>Статы</span>
        </button>
    </nav>

    <script>
    /* === STATE === */
    let data = {
        pnl: { today: 0, allTime: 0, trades: 0 },
        stats: { pumps:0, signals:0, winrate:0, balance:100, totalTrades:0, wins:0, losses:0, profitFactor:0 },
        signals: [],
        news: [],
        pnlHistory: []
    };

    /* === CLOCK === */
    function tickClock() {
        const d = new Date();
        document.getElementById('clock').textContent =
            d.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    }
    setInterval(tickClock, 1000);
    tickClock();

    /* === TABS === */
    function switchTab(btn) {
        const tab = btn.dataset.tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('on'));
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('on'));
        document.getElementById('tab' + tab).classList.add('on');
        btn.classList.add('on');
    }

    /* === RENDER SIGNALS (clickable → modal) === */
    function renderSignalCard(s, fresh, idx) {
        const isShort = s.side === 'SHORT';
        const pct = s.change || 0;
        const score = s.score || 0;
        const sc = score >= 90 ? 's' : score >= 80 ? 'a' : score >= 70 ? 'b' : 'c';
        const sym = (s.symbol || '').replace('_USDT','').replace('USDT','');
        const cls = `sig-card ${isShort ? 'short' : 'long'}${fresh ? ' fresh' : ''}`;

        const entry = s.entry_price || 0;
        const live = s.current_price || entry;
        const fmtPrice = (p) => p >= 1 ? '$'+p.toFixed(4) : p >= 0.001 ? '$'+p.toFixed(6) : '$'+p.toFixed(8);

        return `<div class="${cls}" onclick="showSignalDetail(${idx})" style="cursor:pointer">
            <div class="sig-left">
                <div class="sig-sym">${sym}</div>
                <div class="sig-meta">
                    <span>📍 ${entry > 0 ? fmtPrice(entry) : '--'}</span>
                    <span>${s.side || 'LONG'}</span>
                </div>
            </div>
            <div class="sig-right">
                <div class="sig-change ${pct >= 0 ? 'up' : 'dn'}">${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%</div>
                <span class="sig-score score-${sc}">${score}/100</span>
            </div>
        </div>`;
    }

    /* === SIGNAL MODAL === */
    function showSignalDetail(idx) {
        const s = data.signals[idx];
        if (!s) return;
        const sym = (s.symbol || '').replace('_USDT','').replace('USDT','');
        const isShort = s.side === 'SHORT';
        const pct = s.change || 0;

        document.getElementById('mdSym').textContent = sym;
        const sideEl = document.getElementById('mdSide');
        sideEl.textContent = s.side || 'LONG';
        sideEl.className = 'modal-side ' + (isShort ? 'short' : 'long');

        const chEl = document.getElementById('mdChange');
        chEl.textContent = `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
        chEl.style.color = pct >= 0 ? 'var(--green)' : 'var(--red)';

        document.getElementById('mdScore').textContent = (s.score || 0) + '/100';

        // Entry price
        const entry = s.entry_price || 0;
        const fmtP = (p) => p >= 1 ? '$'+p.toFixed(4) : p >= 0.001 ? '$'+p.toFixed(6) : '$'+p.toFixed(8);
        document.getElementById('mdEntry').textContent = entry > 0 ? fmtP(entry) : '--';

        // Live price
        const live = s.current_price || entry;
        const liveEl = document.getElementById('mdLive');
        liveEl.innerHTML = live > 0 ? '<span class="live-dot-sm"></span>' + fmtP(live) : '--';

        document.getElementById('mdRsi').textContent = (s.rsi || 0).toFixed(1);
        document.getElementById('mdVol').textContent = (s.volume || 0).toFixed(1) + 'x';

        const pnlEl = document.getElementById('mdPnl');
        const pnl = s.pnl || 0;
        pnlEl.textContent = `$${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`;
        pnlEl.style.color = pnl >= 0 ? 'var(--green)' : 'var(--red)';

        const t = s.time ? new Date(s.time) : new Date();
        document.getElementById('mdTime').textContent = t.toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});

        // MEXC link
        const pair = (s.symbol || '').replace('_USDT','USDT');
        document.getElementById('mdLink').href = `https://www.mexc.com/exchange/${pair}`;

        document.getElementById('sigModal').classList.add('show');
    }

    function closeModal(e) {
        document.getElementById('sigModal').classList.remove('show');
    }

    /* === RENDER NEWS (clickable → open URL) === */
    function renderNewsCard(n) {
        const signalClass = n.signal.includes('LONG') ? 'long' : n.signal.includes('SHORT') ? 'short' : 'neutral';
        const hasUrl = n.url && n.url.length > 0;
        const onClick = hasUrl ? `onclick="window.open('${n.url}','_blank')"` : '';
        const arrow = hasUrl ? '<span class="news-link-icon">🔗</span>' : '';
        return `<div class="news-item" ${onClick}>
            <div class="news-top">
                <span class="news-badge ${signalClass}">${n.signal}</span>
                <span style="font-size:0.55rem;color:var(--text-3)">${n.source} • ${n.time}</span>
                ${arrow}
            </div>
            <div class="news-title">${n.title}</div>
        </div>`;
    }

    /* === UPDATE UI === */
    function updateUI() {
        // PnL hero
        const pnlCard = document.getElementById('pnlCard');
        const v = data.pnl.today;
        document.getElementById('pnlValue').textContent = `$${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
        pnlCard.classList.toggle('negative', v < 0);
        document.getElementById('pnlChange').textContent = `${data.pnl.trades} сделок сегодня`;

        // Mini stats
        document.getElementById('statPumps').textContent = data.stats.pumps;
        document.getElementById('statSignals').textContent = data.stats.signals;
        document.getElementById('statWinrate').textContent = data.stats.winrate + '%';
        document.getElementById('statBalance').textContent = '$' + (data.stats.balance || 0).toFixed(0);

        // Signals
        const sl = document.getElementById('signalsList');
        const al = document.getElementById('allSignalsList');
        const badge = document.getElementById('sigBadge');
        badge.textContent = data.signals.length;

        if (data.signals.length > 0) {
            sl.innerHTML = data.signals.slice(0, 6).map((s,i) => renderSignalCard(s, i===0, i)).join('');
            al.innerHTML = data.signals.map((s,i) => renderSignalCard(s, false, i)).join('');
        } else {
            sl.innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Нет активных сигналов</div></div>';
            al.innerHTML = '<div class="empty"><div class="empty-icon">📭</div><div class="empty-text">Нет сигналов</div></div>';
        }

        // News
        const nl = document.getElementById('newsList');
        if (data.news.length > 0) {
            nl.innerHTML = data.news.map(renderNewsCard).join('');
        } else {
            nl.innerHTML = '<div class="empty"><div class="empty-icon">📰</div><div class="empty-text">Нет новостей</div></div>';
        }

        // Stats tab
        document.getElementById('totalTrades').textContent = data.stats.totalTrades || 0;
        document.getElementById('totalWins').textContent = data.stats.wins || 0;
        document.getElementById('totalLosses').textContent = data.stats.losses || 0;
        document.getElementById('profitFactor').textContent = (data.stats.profitFactor || 0).toFixed(2);

        const at = data.pnl.allTime || 0;
        const atCard = document.getElementById('allTimePnl');
        document.getElementById('allTimePnlValue').textContent = `$${at >= 0 ? '+' : ''}${at.toFixed(2)}`;
        atCard.classList.toggle('negative', at < 0);

        drawChart();
    }

    /* === P&L CHART === */
    function drawChart() {
        const h = data.pnlHistory || [];
        if (h.length < 2) return;
        const c = document.getElementById('pnlChart');
        if (!c) return;
        const ctx = c.getContext('2d');
        const W = c.offsetWidth, H = 140;
        c.width = W; c.height = H;

        const vals = h.map(x => x.balance);
        const min = Math.min(...vals), max = Math.max(...vals);
        const range = max - min || 1;
        const pad = 6;

        // Gradient fill
        const isUp = vals[vals.length-1] >= vals[0];
        const grd = ctx.createLinearGradient(0, 0, 0, H);
        if (isUp) {
            grd.addColorStop(0, 'rgba(0,230,118,0.25)');
            grd.addColorStop(1, 'rgba(0,230,118,0)');
        } else {
            grd.addColorStop(0, 'rgba(255,61,87,0.25)');
            grd.addColorStop(1, 'rgba(255,61,87,0)');
        }

        // Points
        const pts = vals.map((v, i) => ({
            x: pad + (i / (vals.length - 1)) * (W - 2*pad),
            y: H - pad - ((v - min) / range) * (H - 2*pad)
        }));

        // Fill
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.lineTo(pts[pts.length-1].x, H);
        ctx.lineTo(pts[0].x, H);
        ctx.closePath();
        ctx.fillStyle = grd;
        ctx.fill();

        // Line
        ctx.beginPath();
        ctx.moveTo(pts[0].x, pts[0].y);
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i].x, pts[i].y);
        ctx.strokeStyle = isUp ? 'var(--green)' : 'var(--red)';
        ctx.lineWidth = 2;
        ctx.stroke();

        // End dot
        const last = pts[pts.length-1];
        ctx.beginPath();
        ctx.arc(last.x, last.y, 4, 0, Math.PI*2);
        ctx.fillStyle = isUp ? '#00e676' : '#ff3d57';
        ctx.fill();
    }

    /* === DATA FETCH === */
    async function fetchData() {
        try {
            const r = await fetch('/api/mobile/data');
            if (r.ok) { data = await r.json(); updateUI(); }
        } catch(e) {}
    }

    function refreshData() {
        document.getElementById('signalsList').innerHTML =
            '<div class="empty"><div class="spinner"></div><div class="empty-text">Обновление...</div></div>';
        fetchData();
    }

    /* === WEBSOCKET === */
    function connectWS() {
        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(proto + '//' + location.host + '/api/mobile/ws');
        ws.onmessage = (e) => {
            try { data = JSON.parse(e.data); updateUI(); } catch(err) {}
        };
        ws.onclose = () => setTimeout(connectWS, 5000);
        ws.onerror = () => ws.close();
    }

    /* === INIT === */
    fetchData();
    connectWS();
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
        pnl: float = 0,
        entry_price: float = 0,
        current_price: float = 0
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
            'entry_price': entry_price,
            'current_price': current_price,
            'time': datetime.now().isoformat()
        }
        
        self.data['signals'].insert(0, signal)
        
        # Ограничить до 50 сигналов
        self.data['signals'] = self.data['signals'][:50]
        
        # Instant broadcast to all WS clients
        asyncio.ensure_future(self._broadcast_ws())
    
    def update_signal_prices(self, prices: dict):
        """Update live prices for active signals. prices = {symbol: current_price}"""
        changed = False
        for sig in self.data.get('signals', []):
            sym = sig.get('symbol', '')
            if sym in prices and prices[sym] > 0:
                sig['current_price'] = prices[sym]
                changed = True
        if changed:
            asyncio.ensure_future(self._broadcast_ws())
    
    def add_news(self, signal: str, title: str, source: str, time_ago: str, url: str = ''):
        """Добавить новость"""
        news = {
            'signal': signal,
            'title': title,
            'source': source,
            'time': time_ago,
            'url': url
        }
        
        self.data['news'].insert(0, news)
        self.data['news'] = self.data['news'][:20]
        
        # Instant broadcast
        asyncio.ensure_future(self._broadcast_ws())
    
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
    
    async def _broadcast_ws(self):
        """Push data to all connected WS clients"""
        if not self._ws_clients:
            return
        payload = json.dumps(self.data, default=str)
        closed = []
        for ws in self._ws_clients:
            try:
                await ws.send_str(payload)
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._ws_clients.discard(ws)
    
    async def stop(self):
        """Остановить сервер"""
        if self.runner:
            await self.runner.cleanup()

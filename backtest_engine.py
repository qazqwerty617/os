"""
MEXC Pump Monitor - BACKTEST ENGINE (The Lab)
Tests strategies on historical data to validate "Genius" logic.
"""

import asyncio
import logging
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class BacktestResult:
    total_trades: int
    win_rate: float
    total_pnl_pct: float
    equity_curve: List[float]
    best_trade: float
    worst_trade: float
    max_drawdown: float

class BacktestEngine:
    """
    🧪 The Laboratory
    Simulates strategies on historical klines.
    """
    
    def __init__(self, mexc_client):
        self.client = mexc_client
    
    async def run_test(self, symbol: str, days: int = 7, timeframe: str = 'Min60'):
        """Run backtest on a symbol"""
        print(f"🧪 STARING BACKTEST: {symbol} ({days} days, {timeframe})")
        
        # 1. Fetch History
        limit = int(days * 24 * (60 / int(timeframe[3:]))) 
        # Approx calculation, assuming Min60 or Min15. 
        # Helper to parse timeframe
        interval_map = {'Min60': 60, 'Min15': 15, 'Min5': 5}
        mins = interval_map.get(timeframe, 60)
        limit = int(days * 24 * (60/mins))
        
        # MEXC limit is usually 1000. Might need loop for more.
        # For this prototype, we cap at 1000 candles (approx 40 days of 1H)
        limit = min(limit, 1000)
        
        klines = await self.client.get_klines(symbol, interval=timeframe, limit=limit)
        if not klines:
            print("❌ No data found")
            return
            
        print(f"📊 Loaded {len(klines)} candles")
        
        # 2. Vectorized Prep
        closes = np.array([k.close for k in klines])
        highs = np.array([k.high for k in klines])
        lows = np.array([k.low for k in klines])
        opens = np.array([k.open for k in klines])
        volumes = np.array([k.volume for k in klines])
        
        # 3. Calculate Indicators (Vectorized)
        rsi = self._calculate_rsi(closes)
        
        # 4. Simulation Loop
        trades = []
        equity = 1000.0
        equity_curve = [equity]
        in_position = False
        entry_price = 0
        stop_loss = 0
        take_profit = 0
        position_size = 0
        
        for i in range(50, len(closes)):
            if in_position:
                # Check Exit
                # Hit SL?
                if lows[i] <= stop_loss:
                    pnl = (stop_loss - entry_price) / entry_price * 100
                    equity *= (1 + pnl/100) # Simple compounding simulation
                    trades.append(pnl)
                    in_position = False
                # Hit TP?
                elif highs[i] >= take_profit:
                    pnl = (take_profit - entry_price) / entry_price * 100
                    equity *= (1 + pnl/100)
                    trades.append(pnl)
                    in_position = False
                # Timeout/Stale? (Optional)
                
            else:
                # Check Entry (Strategy Logic)
                # STRATEGY: RSI Oversold + Reversal (Simple example)
                # "Genius" Strategy: RSI < 35 and Price > Prev Low (Divergence-ish)
                
                # Condition 1: RSI < 35
                if rsi[i] < 35:
                     # Condition 2: Green Candle (Reversal char)
                     if closes[i] > opens[i]:
                         # ENTER LONG
                         entry_price = closes[i]
                         stop_loss = lows[i] * 0.98 # 2% SL
                         take_profit = closes[i] * 1.05 # 5% TP
                         in_position = True
        
        # 5. Compile Stats
        win_rate = 0
        if trades:
            wins = sum(1 for t in trades if t > 0)
            win_rate = (wins / len(trades)) * 100
            
        total_pnl = (equity - 1000) / 1000 * 100
        
        result = BacktestResult(
            total_trades=len(trades),
            win_rate=win_rate,
            total_pnl_pct=total_pnl,
            equity_curve=equity_curve,
            best_trade=max(trades) if trades else 0,
            worst_trade=min(trades) if trades else 0,
            max_drawdown=0 # TODO impl
        )
        
        print("\n🏆 BACKTEST COMPLETE")
        print(f"Trades: {result.total_trades}")
        print(f"Win Rate: {result.win_rate:.1f}%")
        print(f"Total PnL: {result.total_pnl_pct:.1f}%")
        print(f"Final Equity: ${equity:.2f}")
        
        return result

    def _calculate_rsi(self, prices, period=14):
        """Vectorized RSI"""
        delta = np.diff(prices, prepend=prices[0])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        # Simple Moving Average for first period, then exponential
        avg_gain = np.full_like(prices, 0.0)
        avg_loss = np.full_like(prices, 0.0)
        
        # Standard RSI smoothing (Wilder's) is hard to fully vectorize without loop or pandas ewma
        # Using simple loop for generic numpy
        avg_gain[period-1] = np.mean(gain[:period])
        avg_loss[period-1] = np.mean(loss[:period])
        
        for i in range(period, len(prices)):
            avg_gain[i] = (avg_gain[i-1] * (period-1) + gain[i]) / period
            avg_loss[i] = (avg_loss[i-1] * (period-1) + loss[i]) / period
            
        rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(prices), where=avg_loss!=0)
        rsi = 100 - (100 / (1 + rs))
        return rsi

"""
MEXC Pump Monitor - Chart Generator
Генерация графиков для отправки в Telegram
"""

import io
import logging
from typing import List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not installed - charts disabled")


class ChartGenerator:
    """
    📊 Chart Generator for Telegram
    
    Создаёт графики:
    - Candlestick charts
    - Price + RSI
    - Volume bars
    - Entry/SL/TP levels
    """
    
    def __init__(self):
        self.style = {
            'bg_color': '#1a1a2e',
            'text_color': '#ffffff',
            'grid_color': '#2a2a4e',
            'up_color': '#00ff88',
            'down_color': '#ff4444',
            'volume_color': '#4a4a8e',
            'ema_color': '#ffaa00',
            'entry_color': '#00aaff',
            'sl_color': '#ff0000',
            'tp_color': '#00ff00',
        }
        
        if MATPLOTLIB_AVAILABLE:
            plt.style.use('dark_background')
    
    def generate_price_chart(
        self,
        symbol: str,
        prices: List[float],
        volumes: List[float] = None,
        timestamps: List[int] = None,
        entry: float = None,
        stop_loss: float = None,
        take_profit: float = None,
        rsi: float = None,
        title: str = None
    ) -> Optional[bytes]:
        """
        Генерировать график цены с уровнями
        
        Returns:
            PNG image as bytes, or None if failed
        """
        if not MATPLOTLIB_AVAILABLE:
            return None
        
        if len(prices) < 5:
            return None
        
        try:
            # Create figure with subplots
            fig, axes = plt.subplots(
                2, 1, 
                figsize=(10, 6),
                gridspec_kw={'height_ratios': [3, 1]},
                facecolor=self.style['bg_color']
            )
            
            ax_price = axes[0]
            ax_volume = axes[1]
            
            # Set background colors
            for ax in axes:
                ax.set_facecolor(self.style['bg_color'])
                ax.tick_params(colors=self.style['text_color'])
                ax.spines['bottom'].set_color(self.style['grid_color'])
                ax.spines['top'].set_color(self.style['grid_color'])
                ax.spines['left'].set_color(self.style['grid_color'])
                ax.spines['right'].set_color(self.style['grid_color'])
            
            # X axis
            x = list(range(len(prices)))
            
            # Plot price line
            colors = []
            for i in range(len(prices)):
                if i == 0:
                    colors.append(self.style['up_color'])
                elif prices[i] >= prices[i-1]:
                    colors.append(self.style['up_color'])
                else:
                    colors.append(self.style['down_color'])
            
            ax_price.plot(x, prices, color=self.style['up_color'], linewidth=2, alpha=0.9)
            ax_price.fill_between(x, prices, alpha=0.1, color=self.style['up_color'])
            
            # Add EMA (simple moving average for now)
            if len(prices) >= 20:
                ema = []
                for i in range(len(prices)):
                    if i < 20:
                        ema.append(sum(prices[:i+1]) / (i+1))
                    else:
                        ema.append(sum(prices[i-19:i+1]) / 20)
                ax_price.plot(x, ema, color=self.style['ema_color'], linewidth=1.5, 
                            alpha=0.7, linestyle='--', label='EMA20')
            
            # Add entry/SL/TP lines
            current_price = prices[-1]
            
            if entry:
                ax_price.axhline(y=entry, color=self.style['entry_color'], 
                               linestyle='-', linewidth=2, alpha=0.8, label=f'Entry: ${entry:.4f}')
            
            if stop_loss:
                ax_price.axhline(y=stop_loss, color=self.style['sl_color'], 
                               linestyle='--', linewidth=2, alpha=0.8, label=f'SL: ${stop_loss:.4f}')
                # Shade SL zone
                ax_price.axhspan(current_price, stop_loss, alpha=0.1, color=self.style['sl_color'])
            
            if take_profit:
                ax_price.axhline(y=take_profit, color=self.style['tp_color'], 
                               linestyle='--', linewidth=2, alpha=0.8, label=f'TP: ${take_profit:.4f}')
                # Shade TP zone
                ax_price.axhspan(take_profit, current_price, alpha=0.1, color=self.style['tp_color'])
            
            # Title
            chart_title = title or f"📊 {symbol}"
            if rsi:
                chart_title += f"  |  RSI: {rsi:.1f}"
            
            ax_price.set_title(chart_title, color=self.style['text_color'], 
                             fontsize=14, fontweight='bold', pad=10)
            
            ax_price.legend(loc='upper left', facecolor=self.style['bg_color'],
                          edgecolor=self.style['grid_color'], fontsize=8)
            
            ax_price.grid(True, alpha=0.2, color=self.style['grid_color'])
            ax_price.set_ylabel('Price ($)', color=self.style['text_color'])
            
            # Plot volume
            if volumes and len(volumes) == len(prices):
                vol_colors = [self.style['up_color'] if i == 0 or prices[i] >= prices[i-1] 
                            else self.style['down_color'] for i in range(len(prices))]
                ax_volume.bar(x, volumes, color=vol_colors, alpha=0.6)
                ax_volume.set_ylabel('Volume', color=self.style['text_color'])
            else:
                # Create dummy volume based on price changes
                dummy_vol = [abs(prices[i] - prices[i-1]) * 1000 if i > 0 else 100 
                           for i in range(len(prices))]
                ax_volume.bar(x, dummy_vol, color=self.style['volume_color'], alpha=0.5)
            
            ax_volume.grid(True, alpha=0.2, color=self.style['grid_color'])
            ax_volume.set_xlabel('Time', color=self.style['text_color'])
            
            # Tight layout
            plt.tight_layout()
            
            # Save to bytes
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100, 
                       facecolor=self.style['bg_color'], 
                       edgecolor='none',
                       bbox_inches='tight')
            buf.seek(0)
            
            plt.close(fig)
            
            return buf.getvalue()
            
        except Exception as e:
            logger.error(f"Chart generation failed: {e}")
            return None
    
    def generate_signal_chart(
        self,
        symbol: str,
        prices: List[float],
        signal_data: dict
    ) -> Optional[bytes]:
        """
        Генерировать полный график сигнала
        """
        return self.generate_price_chart(
            symbol=symbol,
            prices=prices,
            entry=signal_data.get('entry_price'),
            stop_loss=signal_data.get('stop_loss'),
            take_profit=signal_data.get('take_profit_1'),
            rsi=signal_data.get('rsi'),
            title=f"🔴 SHORT SIGNAL: {symbol}"
        )
    
    def generate_mini_chart(
        self,
        prices: List[float],
        width: int = 200,
        height: int = 80
    ) -> Optional[bytes]:
        """
        Генерировать миниатюрный график (sparkline)
        """
        if not MATPLOTLIB_AVAILABLE or len(prices) < 3:
            return None
        
        try:
            fig, ax = plt.subplots(figsize=(width/100, height/100), 
                                  facecolor=self.style['bg_color'])
            ax.set_facecolor(self.style['bg_color'])
            
            x = list(range(len(prices)))
            color = self.style['up_color'] if prices[-1] >= prices[0] else self.style['down_color']
            
            ax.plot(x, prices, color=color, linewidth=1.5)
            ax.fill_between(x, prices, alpha=0.2, color=color)
            
            ax.axis('off')
            plt.tight_layout(pad=0)
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100,
                       facecolor=self.style['bg_color'],
                       bbox_inches='tight', pad_inches=0)
            buf.seek(0)
            plt.close(fig)
            
            return buf.getvalue()
            
        except Exception as e:
            logger.error(f"Mini chart failed: {e}")
            return None

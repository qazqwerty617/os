"""
MEXC Pump Monitor - Market Heat Map Generator
Визуальная карта рынка с цветовой кодировкой
"""

import asyncio
import logging
import time
import io
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)

# Try to import matplotlib
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib not available - heatmap disabled")


@dataclass
class TokenCell:
    """Ячейка токена в хитмапе"""
    symbol: str
    price_change_1h: float = 0
    price_change_24h: float = 0
    volume_24h: float = 0
    market_cap: float = 0
    
    # Calculated
    color: str = "#808080"
    size: float = 1.0
    
    # Position in grid
    x: int = 0
    y: int = 0
    width: int = 1
    height: int = 1


class HeatMapType(Enum):
    """Типы хитмапов"""
    PRICE_CHANGE_1H = "1h"
    PRICE_CHANGE_24H = "24h"
    VOLUME = "volume"
    FUNDING = "funding"


class MarketHeatMap:
    """
    🗺️ Market Heat Map Generator
    
    Функции:
    - Визуальная карта рынка
    - Цветовая кодировка по изменению цены
    - Размер по рыночной капитализации
    - Группировка по секторам
    - Экспорт в PNG
    """
    
    # Color gradients
    COLORS = {
        'extreme_bearish': '#8B0000',  # Dark red
        'bearish': '#FF4444',           # Red
        'slight_bearish': '#FF8888',    # Light red
        'neutral': '#808080',           # Gray
        'slight_bullish': '#88FF88',    # Light green
        'bullish': '#44FF44',           # Green
        'extreme_bullish': '#008B00'    # Dark green
    }
    
    # Sector groups
    SECTORS = {
        'Layer 1': ['BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'NEAR', 'APT', 'SUI', 'SEI'],
        'Layer 2': ['MATIC', 'ARB', 'OP', 'IMX', 'STRK', 'MANTA', 'BLAST'],
        'DeFi': ['UNI', 'AAVE', 'MKR', 'CRV', 'COMP', 'SNX', 'SUSHI', 'CAKE'],
        'Meme': ['DOGE', 'SHIB', 'PEPE', 'FLOKI', 'BONK', 'WIF', 'MEME', 'TURBO'],
        'AI': ['FET', 'RNDR', 'AGIX', 'OCEAN', 'TAO', 'ARKM', 'WLD'],
        'Gaming': ['AXS', 'SAND', 'MANA', 'ENJ', 'GALA', 'IMX', 'MAGIC'],
        'Exchange': ['BNB', 'OKB', 'CRO', 'FTT', 'KCS', 'HT', 'GT']
    }
    
    def __init__(self, telegram=None, mexc_client=None):
        self.telegram = telegram
        self.client = mexc_client
        
        # Token data cache
        self.tokens: Dict[str, TokenCell] = {}
        
        # Stats
        self.stats = {
            'heatmaps_generated': 0,
            'last_update': 0
        }
    
    def update_token(
        self,
        symbol: str,
        price_change_1h: float = None,
        price_change_24h: float = None,
        volume_24h: float = None,
        market_cap: float = None
    ):
        """Обновить данные токена"""
        if symbol not in self.tokens:
            self.tokens[symbol] = TokenCell(symbol=symbol)
        
        token = self.tokens[symbol]
        
        if price_change_1h is not None:
            token.price_change_1h = price_change_1h
        if price_change_24h is not None:
            token.price_change_24h = price_change_24h
        if volume_24h is not None:
            token.volume_24h = volume_24h
        if market_cap is not None:
            token.market_cap = market_cap
        
        # Update color based on change
        token.color = self._get_color(token.price_change_24h)
    
    def _get_color(self, change: float) -> str:
        """Получить цвет по изменению"""
        if change <= -10:
            return self.COLORS['extreme_bearish']
        elif change <= -5:
            return self.COLORS['bearish']
        elif change <= -1:
            return self.COLORS['slight_bearish']
        elif change >= 10:
            return self.COLORS['extreme_bullish']
        elif change >= 5:
            return self.COLORS['bullish']
        elif change >= 1:
            return self.COLORS['slight_bullish']
        else:
            return self.COLORS['neutral']
    
    def generate_heatmap(
        self,
        heatmap_type: HeatMapType = HeatMapType.PRICE_CHANGE_24H,
        top_n: int = 50,
        width: int = 1200,
        height: int = 800
    ) -> Optional[bytes]:
        """
        Сгенерировать хитмап
        
        Returns:
            PNG bytes
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("matplotlib not available")
            return None
        
        if not self.tokens:
            logger.warning("No token data")
            return None
        
        try:
            # Sort tokens by volume/market cap
            sorted_tokens = sorted(
                self.tokens.values(),
                key=lambda t: t.volume_24h,
                reverse=True
            )[:top_n]
            
            if not sorted_tokens:
                return None
            
            # Create figure
            fig, ax = plt.subplots(figsize=(width/100, height/100), facecolor='#1a1a2e')
            ax.set_facecolor('#1a1a2e')
            
            # Calculate grid layout (treemap-style)
            self._layout_treemap(sorted_tokens, 0, 0, width, height)
            
            # Draw cells
            for token in sorted_tokens:
                # Get change value based on type
                if heatmap_type == HeatMapType.PRICE_CHANGE_1H:
                    change = token.price_change_1h
                else:
                    change = token.price_change_24h
                
                color = self._get_color(change)
                
                # Draw rectangle
                rect = patches.FancyBboxPatch(
                    (token.x, token.y),
                    token.width - 2,
                    token.height - 2,
                    boxstyle="round,pad=0.02",
                    facecolor=color,
                    edgecolor='#1a1a2e',
                    linewidth=2
                )
                ax.add_patch(rect)
                
                # Add text if cell is big enough
                if token.width > 60 and token.height > 40:
                    # Symbol
                    symbol_clean = token.symbol.replace('_USDT', '')
                    ax.text(
                        token.x + token.width/2,
                        token.y + token.height/2 + 5,
                        symbol_clean,
                        ha='center', va='center',
                        fontsize=min(14, token.width/8),
                        fontweight='bold',
                        color='white'
                    )
                    
                    # Change percentage
                    sign = '+' if change >= 0 else ''
                    ax.text(
                        token.x + token.width/2,
                        token.y + token.height/2 - 12,
                        f"{sign}{change:.1f}%",
                        ha='center', va='center',
                        fontsize=min(11, token.width/10),
                        color='white'
                    )
            
            # Title
            title_text = {
                HeatMapType.PRICE_CHANGE_1H: "Рынок за 1 час",
                HeatMapType.PRICE_CHANGE_24H: "Рынок за 24 часа",
                HeatMapType.VOLUME: "Объём торгов",
                HeatMapType.FUNDING: "Ставки финансирования"
            }
            
            ax.set_title(
                f"🗺️ {title_text.get(heatmap_type, 'Market Heat Map')}",
                fontsize=18, color='white', fontweight='bold', pad=10
            )
            
            ax.set_xlim(0, width)
            ax.set_ylim(0, height)
            ax.set_aspect('equal')
            ax.axis('off')
            
            # Legend
            legend_y = height - 30
            legend_items = [
                (self.COLORS['extreme_bullish'], ">+10%"),
                (self.COLORS['bullish'], "+5%"),
                (self.COLORS['slight_bullish'], "+1%"),
                (self.COLORS['neutral'], "0%"),
                (self.COLORS['slight_bearish'], "-1%"),
                (self.COLORS['bearish'], "-5%"),
                (self.COLORS['extreme_bearish'], "<-10%"),
            ]
            
            legend_x = 20
            for color, label in legend_items:
                rect = patches.Rectangle(
                    (legend_x, legend_y), 15, 15,
                    facecolor=color, edgecolor='white'
                )
                ax.add_patch(rect)
                ax.text(
                    legend_x + 20, legend_y + 8, label,
                    fontsize=8, color='white', va='center'
                )
                legend_x += 70
            
            # Save to bytes
            buf = io.BytesIO()
            plt.savefig(
                buf, format='png', dpi=100,
                facecolor='#1a1a2e', edgecolor='none',
                bbox_inches='tight'
            )
            buf.seek(0)
            
            plt.close(fig)
            
            self.stats['heatmaps_generated'] += 1
            self.stats['last_update'] = int(time.time() * 1000)
            
            return buf.getvalue()
            
        except Exception as e:
            logger.error(f"Heatmap generation failed: {e}")
            return None
    
    def _layout_treemap(
        self,
        tokens: List[TokenCell],
        x: float, y: float,
        width: float, height: float
    ):
        """Расположить токены в treemap layout"""
        if not tokens:
            return
        
        if len(tokens) == 1:
            tokens[0].x = x
            tokens[0].y = y
            tokens[0].width = width
            tokens[0].height = height
            return
        
        # Calculate total weight
        total_weight = sum(max(t.volume_24h, 1) for t in tokens)
        
        # Sort by weight
        sorted_tokens = sorted(tokens, key=lambda t: t.volume_24h, reverse=True)
        
        # Simple squarified treemap
        if width > height:
            # Split horizontally
            current_x = x
            for token in sorted_tokens:
                weight = max(token.volume_24h, 1) / total_weight
                token_width = width * weight
                token.x = current_x
                token.y = y
                token.width = token_width
                token.height = height
                current_x += token_width
        else:
            # Split vertically
            current_y = y
            for token in sorted_tokens:
                weight = max(token.volume_24h, 1) / total_weight
                token_height = height * weight
                token.x = x
                token.y = current_y
                token.width = width
                token.height = token_height
                current_y += token_height
    
    async def generate_and_send(
        self,
        heatmap_type: HeatMapType = HeatMapType.PRICE_CHANGE_24H
    ) -> bool:
        """Сгенерировать и отправить в Telegram"""
        if not self.telegram:
            return False
        
        image_bytes = self.generate_heatmap(heatmap_type)
        
        if not image_bytes:
            return False
        
        try:
            await self.telegram.send_photo(
                image_bytes,
                caption=f"🗺️ Market Heat Map ({heatmap_type.value})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send heatmap: {e}")
            return False
    
    def generate_text_heatmap(self, top_n: int = 20) -> str:
        """Текстовый хитмап для Telegram"""
        if not self.tokens:
            return "Нет данных"
        
        sorted_tokens = sorted(
            self.tokens.values(),
            key=lambda t: t.volume_24h,
            reverse=True
        )[:top_n]
        
        lines = ["🗺️ <b>MARKET HEAT MAP</b>\n"]
        
        # Group by change
        gainers = sorted([t for t in sorted_tokens if t.price_change_24h > 0],
                        key=lambda t: t.price_change_24h, reverse=True)[:5]
        losers = sorted([t for t in sorted_tokens if t.price_change_24h < 0],
                       key=lambda t: t.price_change_24h)[:5]
        
        lines.append("<b>🟢 Топ растущие:</b>")
        for t in gainers:
            symbol = t.symbol.replace('_USDT', '')
            lines.append(f"  {symbol}: +{t.price_change_24h:.1f}%")
        
        lines.append("\n<b>🔴 Топ падающие:</b>")
        for t in losers:
            symbol = t.symbol.replace('_USDT', '')
            lines.append(f"  {symbol}: {t.price_change_24h:.1f}%")
        
        # Overall sentiment
        avg_change = sum(t.price_change_24h for t in sorted_tokens) / len(sorted_tokens)
        sentiment = "🟢 БЫЧИЙ" if avg_change > 1 else "🔴 МЕДВЕЖИЙ" if avg_change < -1 else "⚪ НЕЙТРАЛЬНЫЙ"
        
        lines.append(f"\n<b>📊 Общий сентимент:</b> {sentiment}")
        lines.append(f"<b>📈 Средний change:</b> {avg_change:+.2f}%")
        
        return "\n".join(lines)
    
    async def send_text_heatmap(self):
        """Отправить текстовый хитмап"""
        if not self.telegram:
            return
        
        msg = self.generate_text_heatmap()
        await self.telegram.send_message(msg)
    
    def get_sector_performance(self) -> Dict[str, float]:
        """Производительность по секторам"""
        sector_perf = {}
        
        for sector, symbols in self.SECTORS.items():
            changes = []
            for symbol in symbols:
                token = self.tokens.get(f"{symbol}_USDT")
                if token:
                    changes.append(token.price_change_24h)
            
            if changes:
                sector_perf[sector] = sum(changes) / len(changes)
        
        return sector_perf

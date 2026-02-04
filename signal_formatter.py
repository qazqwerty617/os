"""
MEXC Pump Monitor - Signal Formatter
Улучшенное форматирование сигналов для ручной торговли
"""

import time
from typing import Dict, Optional
from datetime import datetime
from signal_engine import EnhancedSignal, SignalQuality
from short_signal_engine import ShortEntry

logger = None  # Will be set if needed


class SignalFormatter:
    """
    Форматтер сигналов для ручной торговли
    Создает понятные и информативные сообщения
    """
    
    @staticmethod
    def format_enhanced_signal(signal: EnhancedSignal, priority: str = "MEDIUM") -> str:
        """
        Форматировать улучшенный сигнал для Telegram
        
        Args:
            signal: EnhancedSignal объект
            priority: Приоритет сигнала (CRITICAL, HIGH, MEDIUM, LOW)
        """
        # Эмодзи по приоритету
        priority_emoji = {
            'CRITICAL': '🚨🚨🚨',
            'HIGH': '🔥🔥',
            'MEDIUM': '⚡',
            'LOW': '📊'
        }
        emoji = priority_emoji.get(priority, '⚡')
        
        # Эмодзи по качеству
        quality_emoji = {
            SignalQuality.S_TIER: '💎',
            SignalQuality.A_TIER: '🔥',
            SignalQuality.B_TIER: '⚡',
            SignalQuality.C_TIER: '📊'
        }
        quality_icon = quality_emoji.get(signal.quality, '📊')
        
        # Эмодзи по типу пампы
        if signal.price_change_pct >= 50:
            pump_emoji = '🚀🚀🚀'
            pump_tier = 'MEGA ПАМП'
        elif signal.price_change_pct >= 30:
            pump_emoji = '🔥🔥'
            pump_tier = 'MASSIVE ПАМП'
        elif signal.price_change_pct >= 10:
            pump_emoji = '⚡'
            pump_tier = 'STRONG ПАМП'
        else:
            pump_emoji = '📈'
            pump_tier = 'EARLY ПАМП'
        
        # RSI эмодзи
        if signal.rsi >= 85:
            rsi_emoji = '🔴🔴'
        elif signal.rsi >= 75:
            rsi_emoji = '🔴'
        else:
            rsi_emoji = '🟡'
        
        # Форматирование цены
        price_str = f"${signal.price:.8f}".rstrip('0').rstrip('.')
        
        # Рассчитать риск/прибыль
        risk_pct = abs((signal.stop_loss - signal.entry_price) / signal.entry_price * 100)
        reward_pct = abs((signal.entry_price - signal.take_profit_1) / signal.entry_price * 100)
        rr_ratio = reward_pct / risk_pct if risk_pct > 0 else 0
        
        # Рекомендация по размеру позиции
        if signal.final_score >= 90:
            size_recommendation = "2-3% от депозита"
        elif signal.final_score >= 80:
            size_recommendation = "1-2% от депозита"
        elif signal.final_score >= 70:
            size_recommendation = "0.5-1% от депозита"
        else:
            size_recommendation = "0.25-0.5% от депозита"
        
        # Рекомендация по плечу
        if signal.price_change_pct >= 50:
            leverage = "5-10x"
        elif signal.price_change_pct >= 30:
            leverage = "3-5x"
        else:
            leverage = "2-3x"
        
        # Предупреждения
        warnings_text = ""
        if signal.warnings:
            warnings_text = "\n\n⚠️ <b>ПРЕДУПРЕЖДЕНИЯ:</b>\n"
            for warning in signal.warnings[:3]:  # Максимум 3 предупреждения
                warnings_text += f"• {warning}\n"
        
        # Проверить есть ли умные уровни (из smart_levels)
        smart_levels_info = ""
        if hasattr(signal, 'smart_levels') and signal.smart_levels:
            sl = signal.smart_levels
            
            # Форматировать паттерны
            patterns_text = ""
            if sl.detected_patterns:
                patterns_text = f"🔍 <b>ПАТТЕРНЫ:</b> {', '.join(sl.detected_patterns[:3])}\n"
            
            # Форматировать Order Blocks
            ob_text = ""
            if sl.order_blocks:
                ob_details = []
                for ob in sl.order_blocks[:2]:
                    ob_type = "Бычий" if ob.is_bullish else "Медвежий"
                    ob_details.append(f"{ob_type} OB (сила {ob.strength:.0f})")
                ob_text = f"📦 <b>ORDER BLOCKS:</b> {', '.join(ob_details)}\n"
            
            # Форматировать ключевые уровни
            levels_text = ""
            if sl.key_levels:
                levels_details = []
                for level in sl.key_levels[:3]:
                    level_type_ru = "Поддержка" if level.level_type == 'support' else "Сопротивление"
                    levels_details.append(f"{level_type_ru} ${level.price:.8f} (сила {level.strength:.0f})")
                levels_text = f"📍 <b>КЛЮЧЕВЫЕ УРОВНИ:</b> {', '.join(levels_details)}\n"
            
            smart_levels_info = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 <b>УМНЫЕ УРОВНИ (ГРАФИЧЕСКИЙ АНАЛИЗ)</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🛑 <b>STOP LOSS:</b> <code>${sl.stop_loss:.8f}</code>
├ 📝 <b>Причина:</b> {sl.stop_loss_reason}
└ 💪 <b>Сила уровня:</b> {sl.stop_loss_strength:.0f}/100

🎁 <b>TAKE PROFITS:</b>
├ TP1: <code>${sl.take_profit_1:.8f}</code>
│   └ {sl.take_profit_1_reason} (сила {sl.take_profit_1_strength:.0f}/100)
├ TP2: <code>${sl.take_profit_2:.8f}</code>
│   └ {sl.take_profit_2_reason} (сила {sl.take_profit_2_strength:.0f}/100)
└ TP3: <code>${sl.take_profit_3:.8f}</code>
    └ {sl.take_profit_3_reason} (сила {sl.take_profit_3_strength:.0f}/100)

📊 <b>РИСК/ПРИБЫЛЬ:</b>
├ R:R TP1: 1:{sl.rr_ratio_1:.1f} (риск {sl.risk_pct:.1f}%, прибыль {sl.reward_1_pct:.1f}%)
├ R:R TP2: 1:{sl.rr_ratio_2:.1f} (прибыль {sl.reward_2_pct:.1f}%)
└ R:R TP3: 1:{sl.rr_ratio_3:.1f} (прибыль {sl.reward_3_pct:.1f}%)

📈 <b>СТРУКТУРА РЫНКА:</b> {sl.market_structure}
{patterns_text}{ob_text}{levels_text}
💡 <b>УВЕРЕННОСТЬ:</b> {sl.confidence}/100
📊 <b>РЕКОМЕНДУЕМЫЙ РАЗМЕР:</b> {sl.recommended_size_pct:.1f}% от депозита
"""
        
        # Форматированное сообщение
        message = f"""
{emoji} {quality_icon} <b>{pump_tier} ОБНАРУЖЕН</b> {quality_icon} {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>ТОКЕН:</b> <code>{signal.symbol}</code>
💰 <b>ТЕКУЩАЯ ЦЕНА:</b> <code>{price_str}</code>
📈 <b>РОСТ:</b> <b>+{signal.price_change_pct:.1f}%</b>
⏱ <b>ЗА ВРЕМЯ:</b> ~{signal.pump_tier.split()[0]} минут

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>АНАЛИЗ СИГНАЛА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <b>SCORE:</b> {signal.final_score}/100 {quality_icon}
📊 <b>КАЧЕСТВО:</b> {signal.quality.value}-TIER
{rsi_emoji} <b>RSI:</b> {signal.rsi:.1f} {'(КРИТИЧЕСКАЯ ПЕРЕКУПЛЕННОСТЬ)' if signal.rsi >= 85 else ''}
📊 <b>ОБЪЕМ:</b> {signal.volume_ratio:.1f}x от среднего
📈 <b>МОМЕНТУМ:</b> {signal.momentum:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 <b>РЕКОМЕНДАЦИИ ДЛЯ ВХОДА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 <b>ENTRY (ВХОД):</b>
├ 🎯 Идеально: <code>${signal.entry_price:.8f}</code>
├ 📉 Минимум: <code>${signal.entry_zone_low:.8f}</code>
└ 📈 Максимум: <code>${signal.entry_zone_high:.8f}</code>

{smart_levels_info if smart_levels_info else f"""
🛑 <b>STOP LOSS (СТОП-ЛОСС):</b>
└ <code>${signal.stop_loss:.8f}</code> ({risk_pct:.1f}% риск)

🎁 <b>TAKE PROFIT (ТЕЙК-ПРОФИТ):</b>
├ TP1: <code>${signal.take_profit_1:.8f}</code> ({reward_pct:.1f}% прибыль) — 30% позиции
└ TP2: <code>${signal.take_profit_2:.8f}</code> ({abs((signal.entry_price - signal.take_profit_2) / signal.entry_price * 100):.1f}% прибыль) — 70% позиции
"""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 <b>ПАРАМЕТРЫ ТОРГОВЛИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 <b>Размер позиции:</b> {size_recommendation}
💪 <b>Плечо:</b> {leverage}
📈 <b>Риск/Прибыль:</b> 1:{rr_ratio:.1f}
🎯 <b>Уверенность:</b> {signal.final_score}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 <b>ПОЧЕМУ ШОРТ?</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{rsi_emoji} RSI {signal.rsi:.1f} = {'КРИТИЧЕСКАЯ' if signal.rsi >= 85 else 'высокая'} перекупленность
📈 Памп {signal.price_change_pct:.1f}% без фундаментальных новостей
📊 Объем {signal.volume_ratio:.1f}x = {'экстремальный' if signal.volume_ratio >= 10 else 'высокий'} спрос
💡 Ожидаем откат на фиксации прибыли{warnings_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

👉 <a href="https://futures.mexc.com/exchange/{signal.symbol}_USDT"><b>🚀 ОТКРЫТЬ {signal.symbol} НА MEXC</b></a>

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        
        return message.strip()
    
    @staticmethod
    def format_quick_exit_alert(
        symbol: str,
        current_price: float,
        entry_price: float,
        reason: str,
        urgency: str,
        profit_pct: float
    ) -> str:
        """Форматировать алерт о быстром выходе"""
        urgency_emoji = {
            'CRITICAL': '🚨🚨🚨',
            'HIGH': '🔥',
            'MEDIUM': '⚠️',
            'LOW': '📊'
        }
        emoji = urgency_emoji.get(urgency, '⚠️')
        
        profit_emoji = '🟢' if profit_pct > 0 else '🔴'
        
        message = f"""
{emoji} <b>БЫСТРЫЙ ВЫХОД / QUICK EXIT</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>ТОКЕН:</b> <code>{symbol}</code>
💰 <b>ТЕКУЩАЯ ЦЕНА:</b> <code>${current_price:.8f}</code>
📊 <b>ВХОД БЫЛ:</b> <code>${entry_price:.8f}</code>
{profit_emoji} <b>ПРИБЫЛЬ:</b> {profit_pct:+.1f}%

⚠️ <b>ПРИЧИНА:</b> {reason}
🚨 <b>СРОЧНОСТЬ:</b> {urgency}

💡 <b>РЕКОМЕНДАЦИЯ:</b> Закрыть позицию немедленно

👉 <a href="https://futures.mexc.com/exchange/{symbol}_USDT"><b>ЗАКРЫТЬ ПОЗИЦИЮ</b></a>

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return message.strip()
    
    @staticmethod
    def format_liquidity_warning(
        symbol: str,
        liquidity_report
    ) -> str:
        """Форматировать предупреждение о ликвидности"""
        risk_emoji = {
            'LOW': '🟢',
            'MEDIUM': '🟡',
            'HIGH': '🟠',
            'CRITICAL': '🔴'
        }
        emoji = risk_emoji.get(liquidity_report.risk_level, '🟡')
        
        warnings_text = "\n".join([f"• {w}" for w in liquidity_report.warnings])
        
        message = f"""
{emoji} <b>ПРЕДУПРЕЖДЕНИЕ О ЛИКВИДНОСТИ</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🪙 <b>ТОКЕН:</b> <code>{symbol}</code>
📊 <b>LIQUIDITY SCORE:</b> {liquidity_report.liquidity_score}/100
⚠️ <b>РИСК:</b> {liquidity_report.risk_level}

📋 <b>ДЕТАЛИ:</b>
├ Bid ликвидность: ${liquidity_report.bid_liquidity_usd:,.0f}
├ Ask ликвидность: ${liquidity_report.ask_liquidity_usd:,.0f}
├ Спред: {liquidity_report.spread_pct:.2f}%
└ Рекомендуемый размер: {liquidity_report.recommended_size_pct*100:.0f}% от обычного

{warnings_text}

💡 <b>РЕКОМЕНДАЦИЯ:</b> {'Можно входить' if liquidity_report.can_enter else 'ОСТОРОЖНО - низкая ликвидность!'}

⏰ {datetime.now().strftime('%H:%M:%S')}
"""
        return message.strip()

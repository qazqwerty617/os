"""
MEXC Pump Monitor - Macro Radar (Geopolitical Monitor)
Monitors global events (War, SEC, Fed) for market risks
"""

import asyncio
import aiohttp
import logging
import feedparser
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger("MacroRadar")


class MacroEventType(Enum):
    WAR_CONFLICT = "war_conflict"    # War, invasion, attack
    REGULATION = "regulation"        # SEC, ban, lawsuit
    ECONOMIC = "economic"            # Fed, inflation, rates
    EXCHANGE_FUD = "exchange_fud"    # Insolvency, hack
    UNKNOWN = "unknown"


@dataclass
class MacroEvent:
    """Detected macro event"""
    title: str
    summary: str
    source: str
    event_type: MacroEventType
    impact_score: int  # 0-100
    sentiment: str  # bearish, bullish, neutral
    # New fields
    impact_verdict: str  # "Good" or "Bad"
    market_effect: str  # "Dump likely", "Pump started"
    affected_assets: List[str]  # ["BTC", "ETH"]
    signal: str  # "SHORT", "LONG"
    timestamp: datetime = field(default_factory=datetime.now)
    url: str = ""


class MacroRadar:
    """
    Geopolitical & Macro Economic Monitor
    - Scans RSS feeds for critical keywords
    - Evaluates "FUD Level"
    - Triggers emergency alerts with detailed analysis
    """
    
    def __init__(self):
        # High-impact keywords
        self.keywords = {
            MacroEventType.WAR_CONFLICT: [
                'war', 'invasion', 'missile', 'attack', 'nuclear', 
                'conflict', 'military', 'tank', 'explosion'
            ],
            MacroEventType.REGULATION: [
                'sec', 'gensler', 'ban', 'lawsuit', 'crackdown', 
                'regulation', 'subpoena', 'wells notice', 'banned'
            ],
            MacroEventType.ECONOMIC: [
                'fed', 'powell', 'rate hike', 'inflation', 'cpi', 
                'recession', 'fomc', 'interest rate', 'economy crash'
            ],
            MacroEventType.EXCHANGE_FUD: [
                'insolvent', 'bankruptcy', 'withdrawals halted', 'hack', 
                'exploit', 'ftx', 'alameda', 'terra', 'peg lost'
            ]
        }
        
        # Sources (RSS feeds - major crypto & world news)
        self.rss_sources = [
            "https://cointelegraph.com/rss",
            "https://coindesk.com/arc/outboundfeeds/rss",
            "https://cryptopotato.com/feed/"
        ]
        
        self.last_events: List[MacroEvent] = []
        self.seen_guids = set()
        self.fud_level = 0
        
        logger.info("🌍 Macro Radar initialized")
    
    async def scan(self) -> List[MacroEvent]:
        """Scan sources for new events"""
        new_events = []
        
        try:
            loop = asyncio.get_event_loop()
            for url in self.rss_sources:
                feed = await loop.run_in_executor(None, feedparser.parse, url)
                
                for entry in feed.entries[:10]:
                    guid = getattr(entry, 'guid', entry.link)
                    if guid in self.seen_guids:
                        continue
                    
                    self.seen_guids.add(guid)
                    
                    event = self._analyze_text(
                        entry.title, 
                        getattr(entry, 'summary', ''),
                        url
                    )
                    
                    if event and event.impact_score > 40:
                        new_events.append(event)
                        self.last_events.append(event)
        
        except Exception as e:
            logger.error(f"Macro scan error: {e}")
            
        self._update_fud_level()
        return new_events
    
    def _analyze_text(self, title: str, summary: str, source: str) -> Optional[MacroEvent]:
        """Analyze text for macro keywords and derive insights"""
        text = (title + " " + summary).lower()
        found_type = MacroEventType.UNKNOWN
        max_score = 0
        
        # 1. Identify Event Type
        for event_type, keywords in self.keywords.items():
            hits = 0
            for kw in keywords:
                if kw in text:
                    hits += 1
            
            if hits > 0:
                score = min(hits * 30, 95)
                if 'unconfirmed' in text or 'rumor' in text:
                    score /= 2
                    
                if score > max_score:
                    max_score = score
                    found_type = event_type
        
        if max_score == 0:
            return None
            
        # 2. Derive Sentiment & Impact
        impact_verdict = "BAD 🔴"
        market_effect = "Uncertainty / Volatility"
        signal = "AVOID"
        affected = ["BTC", "ETH"]
        
        if found_type == MacroEventType.WAR_CONFLICT:
            impact_verdict = "VERY BAD 🔴"
            market_effect = "Panic Dump likely"
            signal = "SHORT"
            affected = ["BTC", "Stocks", "Global Markets"]
            
        elif found_type == MacroEventType.REGULATION:
            impact_verdict = "BAD 🔴"
            market_effect = "Regulatory FUD / Dump"
            signal = "SHORT"
            
            # Detect specific targets
            if 'binance' in text or 'bnb' in text: affected = ["BNB", "Trust Wallet"]
            elif 'coinbase' in text: affected = ["USDC", "COIN"]
            elif 'ethereum' in text or 'eth' in text: affected = ["ETH", "L2s"]
            elif 'xrp' in text or 'ripple' in text: affected = ["XRP"]
            else: affected = ["Altcoins", "DeFi"]
            
        elif found_type == MacroEventType.ECONOMIC:
            if 'hike' in text or 'high' in text:
                impact_verdict = "BAD 🔴"
                market_effect = "Liquidity crunch"
                signal = "SHORT"
            elif 'cut' in text or 'lower' in text or 'print' in text:
                impact_verdict = "GOOD 🟢"
                market_effect = "Money printer go BRRR"
                signal = "LONG"
                found_type = MacroEventType.ECONOMIC  # Keep type but sentiment flips
            else:
                impact_verdict = "NEUTRAL ⚪"
                signal = "HEDGE"
                
        elif found_type == MacroEventType.EXCHANGE_FUD:
            impact_verdict = "CRITICAL ☠️"
            market_effect = "Bank run / Insolvency risk"
            signal = "SHORT EVERYTHING"
            affected = ["CEX Tokens", "Volatile Alts"]
            
        return MacroEvent(
            title=title,
            summary=summary[:200],
            source=source,
            event_type=found_type,
            impact_score=int(max_score),
            sentiment="bearish" if "BAD" in impact_verdict else "bullish",
            impact_verdict=impact_verdict,
            market_effect=market_effect,
            affected_assets=affected,
            signal=signal,
            url=""
        )

    def _update_fud_level(self):
        """Update FUD level based on last 24h events"""
        cutoff = datetime.now() - timedelta(hours=24)
        recent = [e for e in self.last_events if e.timestamp > cutoff]
        
        if not recent:
            self.fud_level = max(0, self.fud_level - 5) # Decay
            return
            
        total_impact = sum(e.impact_score for e in recent)
        self.fud_level = min(total_impact, 100)

    def format_telegram_alert(self, event: MacroEvent) -> str:
        """Format event for Telegram"""
        type_emoji = {
            MacroEventType.WAR_CONFLICT: "⚔️",
            MacroEventType.REGULATION: "⚖️",
            MacroEventType.ECONOMIC: "🏦",
            MacroEventType.EXCHANGE_FUD: "☠️",
            MacroEventType.UNKNOWN: "⚠️"
        }
        
        emoji = type_emoji.get(event.event_type, "⚠️")
        
        signal_emoji = "🟢" if "LONG" in event.signal else "🔴" if "SHORT" in event.signal else "🛡"
        
        return f"""
🌍 <b>MACRO RADAR</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
<b>TOPIC:</b> {event.title}

📊 <b>ANALYSIS / АНАЛИЗ:</b>
├ <b>Verdict:</b> {event.impact_verdict}
├ <b>Impact:</b> {event.market_effect}
├ <b>Affected:</b> {', '.join(event.affected_assets)}
└ <b>Risk Score:</b> {event.impact_score}/100

🧠 <b>AI CONCLUSION:</b>
{signal_emoji} <b>SIGNAL: {event.signal}</b>
<i>Recommended action based on macro risk</i>

🔥 <b>Global FUD Level:</b> {self.fud_level}%
"""


# Convenience instance
macro_radar = MacroRadar()

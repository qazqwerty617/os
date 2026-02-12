"""
Test script for Groq Economic Analysis Integration
Simulates a CPI data release
"""

import asyncio
import logging
from datetime import datetime, timedelta
from economic_calendar import EconomicCalendar, EconomicEvent, EventType, EventImpact
from groq_analyzer import groq_analyzer

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Test")

class MockOrchestrator:
    def __init__(self):
        self.groq = groq_analyzer
        self.news_parser_paused = False
        
    def pause_news_parser(self, duration):
        logger.info(f"PAUSE COMMAND RECEIVED for {duration}s")
        self.news_parser_paused = True

class MockTelegram:
    async def send_message(self, msg):
        print("\n--- TELEGRAM MESSAGE START ---")
        print(msg)
        print("--- TELEGRAM MESSAGE END ---\n")

async def test_cpi_analysis():
    orchestrator = MockOrchestrator()
    telegram = MockTelegram()
    calendar = EconomicCalendar(telegram=telegram, orchestrator=orchestrator)
    
    # Mock an event that just happened
    cpi_event = EconomicEvent(
        id="test_cpi",
        title="US CPI (YoY)",
        event_type=EventType.CPI,
        impact=EventImpact.CRITICAL,
        datetime_utc=datetime.utcnow(),
        country="US",
        previous="3.4%",
        forecast="2.9%",
        description="Consumer Price Index inflation data",
        bullish_if="Below forecast",
        bearish_if="Above forecast"
    )
    
    # Manually set actual to simulate release
    cpi_event.actual = "2.8%" # LOWER than forecast = BULLISH (LONG)
    
    logger.info("Starting analysis test...")
    await calendar.handle_event_result(cpi_event)
    
    if orchestrator.news_parser_paused:
        logger.info("✅ SUCCESS: News parser pause was triggered")
    else:
        logger.error("❌ FAILED: News parser pause was NOT triggered")

if __name__ == "__main__":
    asyncio.run(test_cpi_analysis())

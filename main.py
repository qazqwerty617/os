"""
MEXC Pump Monitor - GENIUS EDITION
Ultimate trading intelligence system
Entry Point
"""

import asyncio
import signal
import sys
import logging
import argparse
from config import config

# Import System Orchestrator
from system_orchestrator import SystemOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")

async def run(args):
    """Single entry: orchestrator starts everything (dashboard, mobile, all modules)"""
    orchestrator = SystemOrchestrator(
        capital=args.capital,
        risk_level=args.risk,
        with_dashboard=(args.mode in ('both', 'dashboard')),
        dashboard_port=args.port,
    )
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
    await orchestrator.start()

async def run_backtest_cli(args):
    """Run backtest from CLI"""
    from backtest_engine import BacktestEngine
    from mexc_client import MEXCClient
    
    print("⏳ Initializing Backtest Engine...")
    client = MEXCClient() 
    await client.start()
    
    engine = BacktestEngine(client)
    symbols = ['BTC_USDT', 'ETH_USDT', 'SOL_USDT']
    
    print(f"🔬 Testing on: {symbols}")
    for sym in symbols:
        await engine.run_test(sym, days=7, timeframe='Min60')
    
    await client.stop()

def main():
    parser = argparse.ArgumentParser(description='MEXC Pump Monitor - run: python main.py')
    parser.add_argument('--mode', choices=['monitor', 'dashboard', 'both', 'backtest'], default='both',
                        help='both=full (default), monitor=no main dashboard, dashboard=web only')
    parser.add_argument('--port', type=int, default=config.dashboard.port)
    parser.add_argument('--capital', type=float, default=None)
    parser.add_argument('--risk', choices=['conservative', 'moderate', 'aggressive', 'degen'], default='moderate')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║  🧠 MEXC PUMP MONITOR - ONE COMMAND TO START                 ║
║  ✓ 53 Modules  ✓ Mobile:8081  ✓ Dashboard:8080              ║
╚═══════════════════════════════════════════════════════════════╝
""")
    
    try:
        if args.mode == 'dashboard':
            from dashboard import run_dashboard
            run_dashboard()
        elif args.mode == 'backtest':
            asyncio.run(run_backtest_cli(args))
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal: {e}")

if __name__ == '__main__':
    main()

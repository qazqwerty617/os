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

async def run_monitor_only(args):
    """Run only the monitor (no dashboard)"""
    capital = args.capital if args.capital is not None else config.demo.initial_balance
    orchestrator = SystemOrchestrator(capital=capital, risk_level=args.risk)
    
    # Signal handling (Windows compatible)
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(orchestrator.stop()))
        
    await orchestrator.start()

async def run_with_dashboard(args):
    """Run monitor + dashboard"""
    import uvicorn
    from dashboard import app, set_components
    
    capital = args.capital if args.capital is not None else config.demo.initial_balance
    orchestrator = SystemOrchestrator(capital=capital, risk_level=args.risk)
    
    # Connect main dashboard to pump_detector (port 8080)
    set_components(orchestrator.pump_detector, orchestrator.market_analyzer, orchestrator.mtf_analyzer)
    
    # Start orchestrator in background
    orchestrator_task = asyncio.create_task(orchestrator.start())
    
    # Configure dashboard
    uvicorn_config = uvicorn.Config(
        app,
        host=config.dashboard.host,
        port=args.port,
        log_level="warning"
    )
    server = uvicorn.Server(uvicorn_config)
    
    # Handle shutdown
    loop = asyncio.get_running_loop()
    
    async def shutdown():
        logger.info("Received shutdown signal")
        await orchestrator.stop()
        server.should_exit = True
    
    # Handle shutdown (Windows compatible)
    if sys.platform != 'win32':
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown()))
        
    try:
        # Run both
        await asyncio.gather(
            orchestrator_task,
            server.serve()
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Runtime error: {e}")
    finally:
        if orchestrator.is_running:
            await orchestrator.stop()

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
    """Main entry point"""
    parser = argparse.ArgumentParser(description='MEXC Pump Monitor - Genius Edition')
    parser.add_argument('--mode', choices=['monitor', 'dashboard', 'both', 'backtest'], default='both')
    parser.add_argument('--port', type=int, default=config.dashboard.port)
    parser.add_argument('--capital', type=float, default=None,
                        help='Capital for risk/backtest. Demo balance uses config.demo.initial_balance ($100)')
    parser.add_argument('--risk', choices=['conservative', 'moderate', 'aggressive', 'degen'], default='moderate')
    parser.add_argument('--debug', action='store_true')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║   🧠 MEXC PUMP MONITOR - SYSTEM ORCHESTRATOR 🧠                  ║
    ║                                                                   ║
    ║   ✓ 53 Modules Linked & Synchronized                              ║
    ║   ✓ Fault Tolerance & Auto-Recovery                              ║
    ║   ✓ Unified Lifecycle Management                                 ║
    ║   ✓ "The Perfect Link" Architecture                               ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    """)
    
    try:
        if args.mode == 'monitor':
            asyncio.run(run_monitor_only(args))
        elif args.mode == 'dashboard':
            # Run only dashboard (legacy mode, might not show live data if monitor not running elsewhere sharing DB)
            from dashboard import run_dashboard
            run_dashboard()
        elif args.mode == 'backtest':
            asyncio.run(run_backtest_cli(args))
        else: # both
            asyncio.run(run_with_dashboard(args))
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")

if __name__ == '__main__':
    main()

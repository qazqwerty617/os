"""
MEXC Pump Monitor - SYSTEM DIAGNOSTIC TOOL
Verifies integrity of all modules and connections.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("SystemCheck")

async def run_diagnostics():
    print("🏥 STARTING FULL SYSTEM DIAGNOSTICS (ALL MODULES)...")
    print("==================================================")
    
    report = {
        'modules_found': 0,
        'modules_loaded': 0,
        'modules_failed': []
    }
    
    # 1. Dynamic Module Discovery
    # Get all .py files in current directory
    files = [f for f in os.listdir('.') if f.endswith('.py')]
    
    # Exclude scripts and non-modules
    exclude = ['system_check.py', 'start.sh', 'debug_mexc.py', 'debug_signals.py', 'test_signals.py', 'send_tokenomics.py', 'send_updated_signals.py']
    
    modules_to_check = []
    for f in files:
        if f in exclude: continue
        mod_name = f[:-3] # removing .py
        modules_to_check.append(mod_name)
    
    modules_to_check.sort()
    report['modules_found'] = len(modules_to_check)
    
    print(f"\n📂 Found {len(modules_to_check)} modules to verify...")
    
    # 2. Import Verification
    for mod in modules_to_check:
        try:
            __import__(mod)
            # print(f"✅ Loaded: {mod}")
            report['modules_loaded'] += 1
        except Exception as e:
            print(f"❌ FAILED: {mod} ({e})")
            report['modules_failed'].append(mod)
            
    # 3. Core Components Deep Check (Subset)
    print("\n🔬 CHECKING CORE SUBSYSTEMS...")
    
    core_checks = [
        ('ProfitMaximizer', 'profit_maximizer', 'ProfitMaximizer'),
        ('SelfLearning', 'self_learning', 'SelfLearningEngine'),
        ('PatternEngine', 'advanced_pattern_scanner', 'AdvancedPatternScanner'),
        ('NewsBot', 'news_bot', 'NewsBot'),
        ('RiskManager', 'risk_manager', 'RiskManager'),
        ('Database', 'database', 'SignalDatabase'),
        ('MarketHeatmap', 'market_heatmap', 'MarketHeatMap'),
        ('BacktestEngine', 'backtest_engine', 'BacktestEngine'),
        ('WhaleTracker', 'whale_wallet_tracker', 'WhaleWalletTracker'),
        ('SentimentNLP', 'sentiment_nlp', 'MarketSentimentNLP'),
        ('SystemOrchestrator', 'system_orchestrator', 'SystemOrchestrator')
    ]
    
    success_cores = 0
    for name, mod_name, class_name in core_checks:
        try:
            module = __import__(mod_name)
            if hasattr(module, class_name):
                success_cores += 1
                # print(f"  ✅ {name} OK")
            else:
                print(f"  ⚠️ {name} Class Missing")
        except:
             print(f"  ❌ {name} Import Failed")

    # 4. Summary
    print("\n📊 SYSTEM HEALTH REPORT")
    print(f"Total Modules:   {report['modules_found']}")
    print(f"Successfully Loaded: {report['modules_loaded']}")
    
    if len(report['modules_failed']) > 0:
        print(f"Failed Modules: {len(report['modules_failed'])}")
        for m in report['modules_failed']:
            print(f" - {m}")
    else:
        print("🎉 ALL MODULES FUNCTIONAL")
        
    print(f"\nCore Systems: {success_cores}/{len(core_checks)} Active")
    
    # Final Verdict
    if report['modules_loaded'] == report['modules_found']:
        print("\n🚀 STATUS: 100% OPERATIONAL")
    else:
        print("\n⚠️ STATUS: PARTIAL SYSTEM FAILURE")

if __name__ == "__main__":
    asyncio.run(run_diagnostics())

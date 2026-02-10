"""
MEXC Pump Monitor - Demo State Persistence
Сохраняет баланс и сделки демо-торговли между перезапусками
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DEMO_STATE_PATH = Path(__file__).parent / "data" / "demo_state.json"


def _serialize_order(order: Any) -> dict:
    """Convert AutoOrder to JSON-serializable dict"""
    return {
        "order_id": getattr(order, "order_id", ""),
        "symbol": getattr(order, "symbol", ""),
        "side": getattr(order, "side", None).value if hasattr(getattr(order, "side", None), "value") else str(getattr(order, "side", "")),
        "entry_price": getattr(order, "entry_price", 0),
        "quantity": getattr(order, "quantity", 0),
        "filled_price": getattr(order, "filled_price", 0),
        "filled_quantity": getattr(order, "filled_quantity", 0),
        "realized_pnl": getattr(order, "realized_pnl", 0),
        "created_at": getattr(order, "created_at", None).isoformat() if getattr(order, "created_at", None) else None,
        "filled_at": getattr(order, "filled_at", None).isoformat() if getattr(order, "filled_at", None) else None,
        "signal_source": getattr(order, "signal_source", ""),
    }


def load_demo_state() -> Optional[Dict[str, Any]]:
    """Load demo state from file. Returns None if not found or invalid."""
    try:
        if not DEMO_STATE_PATH.exists():
            return None
        data = json.loads(DEMO_STATE_PATH.read_text(encoding="utf-8"))
        return data
    except Exception as e:
        logger.debug(f"Demo state load failed: {e}")
        return None


def save_demo_state(
    demo_balance: float,
    demo_pnl: float,
    order_history: List[Any],
    stats: Dict[str, Any],
) -> None:
    """Save demo state to file."""
    try:
        DEMO_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        orders = [_serialize_order(o) for o in order_history[-500:]]  # Keep last 500
        data = {
            "demo_balance": demo_balance,
            "demo_pnl": demo_pnl,
            "order_history": orders,
            "stats": {
                "orders_placed": stats.get("orders_placed", 0),
                "orders_filled": stats.get("orders_filled", 0),
                "positions_opened": stats.get("positions_opened", 0),
                "positions_closed": stats.get("positions_closed", 0),
                "total_pnl_usd": stats.get("total_pnl_usd", 0),
                "wins": stats.get("wins", 0),
                "losses": stats.get("losses", 0),
            },
            "saved_at": datetime.now().isoformat(),
        }
        DEMO_STATE_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Demo state save failed: {e}")

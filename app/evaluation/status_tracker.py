"""
Status tracker for long-running evaluation tasks.
"""
from typing import Dict, Any

_eval_status = {
    "status": "idle",
    "progress": 0,
    "current": 0,
    "total": 0,
    "message": ""
}

def update_eval_status(status: str = None, current: int = None, total: int = None, message: str = None):
    global _eval_status
    if status: _eval_status["status"] = status
    if current is not None: _eval_status["current"] = current
    if total is not None: _eval_status["total"] = total
    if message: _eval_status["message"] = message
    
    if _eval_status["total"] > 0:
        _eval_status["progress"] = int((_eval_status["current"] / _eval_status["total"]) * 100)
    else:
        _eval_status["progress"] = 0

def get_eval_status() -> Dict[str, Any]:
    return _eval_status

def reset_eval_status():
    global _eval_status
    _eval_status = {
        "status": "idle",
        "progress": 0,
        "current": 0,
        "total": 0,
        "message": ""
    }

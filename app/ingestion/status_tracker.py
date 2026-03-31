"""
In-memory status tracker for background ingestion tasks.

Consistent with app.evaluation.status_tracker pattern.
No file I/O — avoids polluting the working directory.
"""
from typing import Any

_ingestion_status: dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "message": "No ingestion has run yet.",
}


def update_status(status: str, progress: int, message: str) -> None:
    """Update the current ingestion status."""
    global _ingestion_status
    _ingestion_status = {
        "status": status,
        "progress": progress,
        "message": message,
    }


def get_status() -> dict[str, Any]:
    """Read the current ingestion status."""
    return _ingestion_status


def reset_status() -> None:
    """Reset ingestion status to idle."""
    global _ingestion_status
    _ingestion_status = {
        "status": "idle",
        "progress": 0,
        "message": "No ingestion has run yet.",
    }

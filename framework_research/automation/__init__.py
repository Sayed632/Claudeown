"""
Automation module - Snapshot capture and backtest runners
"""

from .capture_snapshot import capture_snapshot, save_snapshot
from .run_backtest import run_all_frameworks_backtest, generate_comparison_report

__all__ = [
    'capture_snapshot',
    'save_snapshot',
    'run_all_frameworks_backtest',
    'generate_comparison_report'
]

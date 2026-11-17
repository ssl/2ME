"""
Progress tracking utilities for 2ME Domain Checker Framework
"""

import threading
import time

from core.utils import color_text

CLEAR_LINE = '\r\033[K'


class ProgressTracker:
    """Single-line progress display that can be advanced from several threads."""

    def __init__(self, task_name, total_items, min_interval=0.1):
        self.task_name = task_name
        self.total_items = total_items
        self.completed_items = 0
        self.start_time = time.time()
        self.min_interval = min_interval  # Seconds between redraws
        self._last_print = 0.0
        self.lock = threading.Lock()

    def advance(self, items=1):
        """Count `items` more as done."""
        with self.lock:
            self.completed_items += items
            self._print()

    def _print(self):
        if self.total_items <= 0:
            return
        now = time.time()
        finished = self.completed_items >= self.total_items
        if not finished and now - self._last_print < self.min_interval:
            return
        self._last_print = now
        percentage = (self.completed_items / self.total_items) * 100
        print(f"{CLEAR_LINE}{self.task_name}: {self.completed_items}/{self.total_items} "
              f"({percentage:.1f}%) - {now - self.start_time:.1f}s", end='', flush=True)

    def complete(self):
        """Replace the progress line with a green checkmark."""
        elapsed = time.time() - self.start_time
        print(f"{CLEAR_LINE}{color_text('✓', 'green')} {self.task_name} completed "
              f"({self.completed_items}/{self.total_items}) - {elapsed:.1f}s")


def create_progress_tracker(task_name, total_items):
    """Create a new progress tracker."""
    return ProgressTracker(task_name, total_items)

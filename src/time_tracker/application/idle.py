"""Content-free idle-duration policy independent of operating-system APIs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol


class IdleDetector(Protocol):
    """Return elapsed seconds since local user input without exposing content."""

    def idle_seconds(self) -> float:
        """Return a non-negative finite idle duration in seconds."""
        ...


@dataclass(frozen=True, slots=True)
class IdleDetectionStatus:
    """Current availability of the platform idle-duration adapter."""

    available: bool


class IdleEpisodeMonitor:
    """Detect one threshold crossing per observed continuous idle episode."""

    def __init__(self, threshold_seconds: float) -> None:
        if not math.isfinite(threshold_seconds) or threshold_seconds <= 0:
            raise ValueError("idle threshold must be a positive finite number")
        self._threshold_seconds = threshold_seconds
        self._last_reported: float | None = None
        self._baseline_idle = 0.0
        self._baseline_active = 0.0
        self._baseline_on_next_observation = False
        self._handled = False

    def reset(self, *, establish_baseline: bool) -> None:
        """Clear episode state, optionally excluding idle observed before reset."""
        self._last_reported = None
        self._baseline_idle = 0.0
        self._baseline_active = 0.0
        self._baseline_on_next_observation = establish_baseline
        self._handled = False

    def observe(self, reported_idle: float, active_elapsed: float) -> bool:
        """Return true once when eligible idle reaches the configured threshold."""
        _validate_duration(reported_idle, "reported idle duration")
        _validate_duration(active_elapsed, "active timer duration")
        if self._baseline_on_next_observation:
            self._baseline_idle = reported_idle
            self._baseline_active = active_elapsed
            self._baseline_on_next_observation = False
        elif self._last_reported is not None and reported_idle < self._last_reported:
            self._baseline_idle = 0.0
            self._baseline_active = 0.0
            self._handled = False
        self._last_reported = reported_idle
        eligible = min(
            max(0.0, reported_idle - self._baseline_idle),
            max(0.0, active_elapsed - self._baseline_active),
        )
        if self._handled or eligible < self._threshold_seconds:
            return False
        self._handled = True
        return True

    def mark_handled(self) -> None:
        """Consume the current episode when another active prompt already exists."""
        self._handled = True


def _validate_duration(value: float, label: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be non-negative and finite")

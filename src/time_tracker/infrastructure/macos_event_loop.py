"""Core Foundation asyncio integration for packaged macOS notifications."""

from __future__ import annotations

import asyncio
from typing import cast


def create_macos_event_loop() -> asyncio.AbstractEventLoop:
    """Create the main-thread loop required for Notification Center callbacks."""
    from rubicon.objc.runtime import load_library  # type: ignore[import-untyped]

    # Rubicon resolves AppKit classes while importing its event-loop module. Load
    # the framework explicitly because a headless PyInstaller agent has not done so.
    load_library("AppKit")

    from rubicon.objc.eventloop import (  # type: ignore[import-untyped]
        RubiconEventLoop,
    )

    return cast(asyncio.AbstractEventLoop, RubiconEventLoop())

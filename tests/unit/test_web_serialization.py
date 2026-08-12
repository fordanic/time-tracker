from __future__ import annotations

import asyncio
import threading
import time
from typing import cast

import pytest

from time_tracker.web.api import SerializedAgent, WebAgent


class SlowAgent:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.guard = threading.Lock()

    def operation(self, value: int) -> int:
        with self.guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.02)
        with self.guard:
            self.active -= 1
        return value


@pytest.mark.asyncio
async def test_serialized_agent_never_overlaps_calls_from_multiple_tabs() -> None:
    source = SlowAgent()
    agent = SerializedAgent(cast(WebAgent, source))

    results = await asyncio.gather(
        *(agent.call("operation", value) for value in range(5))
    )

    assert results == [0, 1, 2, 3, 4]
    assert source.max_active == 1

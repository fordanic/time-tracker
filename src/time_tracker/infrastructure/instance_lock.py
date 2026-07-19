"""Narrow cross-platform adapter for the single-agent instance lock."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast


class AgentAlreadyRunningError(RuntimeError):
    """Another process already owns the background-agent lock."""


class _FcntlModule(Protocol):
    LOCK_EX: int
    LOCK_NB: int
    LOCK_UN: int

    def flock(self, descriptor: int, operation: int) -> None: ...


class _MsvcrtModule(Protocol):
    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, descriptor: int, mode: int, count: int) -> None: ...


@contextmanager
def instance_lock(path: Path) -> Iterator[None]:
    """Hold a non-blocking exclusive process lock for the context lifetime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            if os.name == "nt":
                unlock = _acquire_windows_lock(descriptor)
            else:
                unlock = _acquire_posix_lock(descriptor)
        except OSError as error:
            raise AgentAlreadyRunningError(
                "another Time Tracker agent is already running"
            ) from error
        try:
            yield
        finally:
            unlock()
    finally:
        os.close(descriptor)


def _acquire_posix_lock(descriptor: int) -> Callable[[], None]:
    module = cast(
        _FcntlModule,
        cast(object, importlib.import_module("fcntl")),
    )
    module.flock(descriptor, module.LOCK_EX | module.LOCK_NB)

    def unlock() -> None:
        module.flock(descriptor, module.LOCK_UN)

    return unlock


def _acquire_windows_lock(descriptor: int) -> Callable[[], None]:
    module = cast(
        _MsvcrtModule,
        cast(object, importlib.import_module("msvcrt")),
    )
    if os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")
    os.lseek(descriptor, 0, os.SEEK_SET)
    module.locking(descriptor, module.LK_NBLCK, 1)

    def unlock() -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        module.locking(descriptor, module.LK_UNLCK, 1)

    return unlock

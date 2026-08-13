"""Cross-platform locations for the local database and agent endpoint."""

from __future__ import annotations

import getpass
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True, slots=True)
class AgentPaths:
    """Resolved paths shared by the foreground and background processes."""

    database: Path
    config: Path
    address: str
    secret: Path
    lock: Path
    log: Path
    family: str

    @classmethod
    def defaults(cls) -> AgentPaths:
        """Resolve platform-appropriate per-user application locations."""
        dirs = PlatformDirs("time-tracker", "Time Tracker")
        if os.name == "nt":
            safe_user = "".join(
                character if character.isalnum() else "-"
                for character in getpass.getuser()
            )
            address = rf"\\.\pipe\time-tracker-{safe_user}"
            family = "AF_PIPE"
        else:
            address = str(Path(dirs.user_runtime_path) / "agent.sock")
            family = "AF_UNIX"
        return cls(
            database=Path(dirs.user_data_path) / "time-tracker.sqlite3",
            config=Path(dirs.user_config_path) / "config.toml",
            address=address,
            secret=Path(dirs.user_state_path) / "agent.secret",
            lock=Path(dirs.user_state_path) / "agent.lock",
            log=Path(dirs.user_log_path) / "agent.log",
            family=family,
        )

    @classmethod
    def in_directory(cls, directory: Path) -> AgentPaths:
        """Resolve isolated paths for one test or development instance."""
        identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:16]
        if os.name == "nt":
            address = rf"\\.\pipe\time-tracker-test-{identity}"
            family = "AF_PIPE"
        else:
            candidate = directory / "agent.sock"
            if len(os.fsencode(candidate)) >= 100:
                candidate = Path("/tmp").resolve() / f"tt-{identity}.sock"
            address = str(candidate)
            family = "AF_UNIX"
        return cls(
            database=directory / "time-tracker.sqlite3",
            config=directory / "config.toml",
            address=address,
            secret=directory / "agent.secret",
            lock=directory / "agent.lock",
            log=directory / "agent.log",
            family=family,
        )

    def prepare(self) -> None:
        """Create private parent directories without touching stored data."""
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.config.parent.mkdir(parents=True, exist_ok=True)
        self.secret.parent.mkdir(parents=True, exist_ok=True)
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.log.parent.mkdir(parents=True, exist_ok=True)
        if self.family == "AF_UNIX":
            Path(self.address).parent.mkdir(parents=True, exist_ok=True)

    @property
    def foreground_lock(self) -> Path:
        """Return the sibling lock shared by TUI and web foreground processes."""
        return self.lock.with_name("foreground.lock")

    def authkey(self) -> bytes:
        """Load or atomically create the per-user IPC authentication secret."""
        self.prepare()
        try:
            descriptor = os.open(
                self.secret, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as secret_file:
                secret_file.write(os.urandom(32))
                secret_file.flush()
                os.fsync(secret_file.fileno())

        for _ in range(100):
            secret = self.secret.read_bytes()
            if len(secret) == 32:
                return secret
            time.sleep(0.01)
        raise RuntimeError("the IPC authentication secret is incomplete")

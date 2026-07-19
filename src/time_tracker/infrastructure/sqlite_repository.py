"""SQLite implementation of the timer persistence port."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path

from time_tracker.domain.models import ActiveTimer, CompletedTimer, require_utc

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MIGRATIONS = ((1, "001_initial.sql"),)


def datetime_to_micros(value: datetime) -> int:
    """Convert an aware instant to integer microseconds since the Unix epoch."""
    delta = require_utc(value) - _EPOCH
    return delta.days * 86_400_000_000 + delta.seconds * 1_000_000 + delta.microseconds


def micros_to_datetime(value: int) -> datetime:
    """Convert integer Unix microseconds to an aware UTC datetime."""
    return _EPOCH + timedelta(microseconds=value)


class SQLiteTimerRepository:
    """Persist timer transitions using short, transactional connections."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at_utc TEXT NOT NULL
                )
                """
            )
            applied = {
                int(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations")
            }

        migration_package = resources.files("time_tracker.infrastructure.migrations")
        for version, filename in _MIGRATIONS:
            if version in applied:
                continue
            sql = migration_package.joinpath(filename).read_text(encoding="utf-8")
            applied_at = datetime.now(UTC).isoformat()
            script = (
                "BEGIN IMMEDIATE;\n"
                f"{sql}\n"
                "INSERT INTO schema_migrations(version, applied_at_utc) "
                f"VALUES ({version}, '{applied_at}');\n"
                "COMMIT;"
            )
            connection = self._connect()
            try:
                connection.executescript(script)
            finally:
                connection.close()

    def get_active(self) -> ActiveTimer | None:
        """Load the active entry and its project/activity names."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT e.id, p.name AS project, a.name AS activity,
                       e.started_at_utc, e.note
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.stopped_at_utc IS NULL
                """
            ).fetchone()
        return self._active_from_row(row) if row is not None else None

    def list_projects(self) -> list[str]:
        """List non-archived projects using their canonical stored names."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM projects
                WHERE archived_at_utc IS NULL
                ORDER BY name COLLATE NOCASE, id
                """
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_activities(self, project: str) -> list[str]:
        """List non-archived activities for a case-insensitive project match."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.name
                FROM activities AS a
                JOIN projects AS p ON p.id = a.project_id
                WHERE p.name = ? COLLATE NOCASE
                  AND p.archived_at_utc IS NULL
                  AND a.archived_at_utc IS NULL
                ORDER BY a.name COLLATE NOCASE, a.id
                """,
                (project,),
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_completed(self) -> list[CompletedTimer]:
        """List completed entries chronologically, including archived names."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.id, p.name AS project, a.name AS activity,
                       e.started_at_utc, e.stopped_at_utc, e.note
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.stopped_at_utc IS NOT NULL
                ORDER BY e.started_at_utc, e.id
                """
            ).fetchall()
        return [self._completed_from_row(row) for row in rows]

    def start(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        note: str | None,
    ) -> ActiveTimer:
        """Stop any active entry and insert a new one in one transaction."""
        started_micros = datetime_to_micros(started_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT e.id, p.name AS project, a.name AS activity,
                       e.started_at_utc, e.note
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.stopped_at_utc IS NULL
                """
            ).fetchone()
            if current is not None:
                self._active_from_row(current).stop(started_at)
                connection.execute(
                    "UPDATE time_entries SET stopped_at_utc = ? WHERE id = ?",
                    (started_micros, int(current["id"])),
                )

            project_row = connection.execute(
                """
                SELECT id, name
                FROM projects
                WHERE name = ? COLLATE NOCASE AND archived_at_utc IS NULL
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if project_row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO projects(name, created_at_utc)
                    VALUES (?, ?)
                    """,
                    (project, started_micros),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return the inserted project ID")
                project_id = cursor.lastrowid
                canonical_project = project
            else:
                project_id = int(project_row["id"])
                canonical_project = str(project_row["name"])

            activity_row = connection.execute(
                """
                SELECT id, name
                FROM activities
                WHERE project_id = ?
                  AND name = ? COLLATE NOCASE
                  AND archived_at_utc IS NULL
                ORDER BY id
                LIMIT 1
                """,
                (project_id, activity),
            ).fetchone()
            if activity_row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO activities(project_id, name, created_at_utc)
                    VALUES (?, ?, ?)
                    """,
                    (project_id, activity, started_micros),
                )
                if cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return the inserted activity ID")
                activity_id = cursor.lastrowid
                canonical_activity = activity
            else:
                activity_id = int(activity_row["id"])
                canonical_activity = str(activity_row["name"])
            cursor = connection.execute(
                """
                INSERT INTO time_entries(
                    activity_id, started_at_utc, note, created_at_utc
                ) VALUES (?, ?, ?, ?)
                """,
                (activity_id, started_micros, note, started_micros),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the inserted entry ID")
            entry_id = cursor.lastrowid

        return ActiveTimer(
            entry_id=entry_id,
            project=canonical_project,
            activity=canonical_activity,
            started_at=require_utc(started_at),
            note=note,
        )

    def stop(self, stopped_at: datetime) -> CompletedTimer | None:
        """Stop the active entry transactionally and return the completed value."""
        stopped_micros = datetime_to_micros(stopped_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT e.id, p.name AS project, a.name AS activity,
                       e.started_at_utc, e.note
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.stopped_at_utc IS NULL
                """
            ).fetchone()
            if row is None:
                return None
            completed = self._active_from_row(row).stop(stopped_at)
            connection.execute(
                "UPDATE time_entries SET stopped_at_utc = ? WHERE id = ?",
                (stopped_micros, completed.entry_id),
            )
        return completed

    @staticmethod
    def _active_from_row(row: sqlite3.Row) -> ActiveTimer:
        return ActiveTimer(
            entry_id=int(row["id"]),
            project=str(row["project"]),
            activity=str(row["activity"]),
            started_at=micros_to_datetime(int(row["started_at_utc"])),
            note=str(row["note"]) if row["note"] is not None else None,
        )

    @staticmethod
    def _completed_from_row(row: sqlite3.Row) -> CompletedTimer:
        return CompletedTimer(
            entry_id=int(row["id"]),
            project=str(row["project"]),
            activity=str(row["activity"]),
            started_at=micros_to_datetime(int(row["started_at_utc"])),
            stopped_at=micros_to_datetime(int(row["stopped_at_utc"])),
            note=str(row["note"]) if row["note"] is not None else None,
        )

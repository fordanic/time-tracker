"""SQLite implementation of the timer persistence port."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from importlib import resources
from pathlib import Path

from time_tracker.application.tracking import ArchivedActivity
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

    def resolve_project_to_archive(self, project: str) -> str:
        """Validate a project archive target without changing it."""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown project: {project}")
        canonical_project = str(row["name"])
        if row["archived_at_utc"] is not None:
            raise ValueError(f"project is already archived: {canonical_project}")
        return canonical_project

    def resolve_activity_to_archive(
        self,
        project: str,
        activity: str,
    ) -> tuple[str, str]:
        """Validate an activity archive target without changing it."""
        with self._connect() as connection:
            project_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if project_row is None:
                raise ValueError(f"unknown project: {project}")
            canonical_project = str(project_row["name"])
            if project_row["archived_at_utc"] is not None:
                raise ValueError(f"project is archived: {canonical_project}")
            activity_row = connection.execute(
                """
                SELECT name, archived_at_utc
                FROM activities
                WHERE project_id = ? AND name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (int(project_row["id"]), activity),
            ).fetchone()
        if activity_row is None:
            raise ValueError(f"unknown activity: {activity}")
        canonical_activity = str(activity_row["name"])
        if activity_row["archived_at_utc"] is not None:
            raise ValueError(f"activity is already archived: {canonical_activity}")
        return canonical_project, canonical_activity

    def list_archived_projects(self) -> list[str]:
        """List archived projects using canonical names."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name
                FROM projects
                WHERE archived_at_utc IS NOT NULL
                ORDER BY name COLLATE NOCASE, id
                """
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def list_archived_activities(self) -> list[ArchivedActivity]:
        """List archived activities and whether their parent is archived."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT p.name AS project, a.name AS activity,
                       p.archived_at_utc AS project_archived_at_utc
                FROM activities AS a
                JOIN projects AS p ON p.id = a.project_id
                WHERE a.archived_at_utc IS NOT NULL
                ORDER BY p.name COLLATE NOCASE, p.id,
                         a.name COLLATE NOCASE, a.id
                """
            ).fetchall()
        return [
            ArchivedActivity(
                project=str(row["project"]),
                activity=str(row["activity"]),
                project_archived=row["project_archived_at_utc"] is not None,
            )
            for row in rows
        ]

    def archive_project(self, project: str, archived_at: datetime) -> str:
        """Archive a project without changing its activities or history."""
        archived_micros = datetime_to_micros(archived_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown project: {project}")
            canonical_project = str(row["name"])
            if row["archived_at_utc"] is not None:
                raise ValueError(f"project is already archived: {canonical_project}")
            connection.execute(
                "UPDATE projects SET archived_at_utc = ? WHERE id = ?",
                (archived_micros, int(row["id"])),
            )
        return canonical_project

    def archive_activity(
        self,
        project: str,
        activity: str,
        archived_at: datetime,
    ) -> tuple[str, str]:
        """Archive one activity while retaining it for historical joins."""
        archived_micros = datetime_to_micros(archived_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if project_row is None:
                raise ValueError(f"unknown project: {project}")
            if project_row["archived_at_utc"] is not None:
                raise ValueError(f"project is archived: {project_row['name']}")
            activity_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM activities
                WHERE project_id = ? AND name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (int(project_row["id"]), activity),
            ).fetchone()
            if activity_row is None:
                raise ValueError(f"unknown activity: {activity}")
            canonical_activity = str(activity_row["name"])
            if activity_row["archived_at_utc"] is not None:
                raise ValueError(f"activity is already archived: {canonical_activity}")
            connection.execute(
                "UPDATE activities SET archived_at_utc = ? WHERE id = ?",
                (archived_micros, int(activity_row["id"])),
            )
        return str(project_row["name"]), canonical_activity

    def unarchive_project(self, project: str) -> str:
        """Restore a project without changing child activity flags."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown project: {project}")
            canonical_project = str(row["name"])
            if row["archived_at_utc"] is None:
                raise ValueError(f"project is not archived: {canonical_project}")
            connection.execute(
                "UPDATE projects SET archived_at_utc = NULL WHERE id = ?",
                (int(row["id"]),),
            )
        return canonical_project

    def unarchive_activity(self, project: str, activity: str) -> tuple[str, str]:
        """Restore an activity only when its parent project is selectable."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if project_row is None:
                raise ValueError(f"unknown project: {project}")
            canonical_project = str(project_row["name"])
            if project_row["archived_at_utc"] is not None:
                raise ValueError(
                    f"restore project first: {canonical_project} is archived"
                )
            activity_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM activities
                WHERE project_id = ? AND name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (int(project_row["id"]), activity),
            ).fetchone()
            if activity_row is None:
                raise ValueError(f"unknown activity: {activity}")
            canonical_activity = str(activity_row["name"])
            if activity_row["archived_at_utc"] is None:
                raise ValueError(f"activity is not archived: {canonical_activity}")
            connection.execute(
                "UPDATE activities SET archived_at_utc = NULL WHERE id = ?",
                (int(activity_row["id"]),),
            )
        return canonical_project, canonical_activity

    def create_project(self, project: str, created_at: datetime) -> str:
        """Create a new project, rejecting an existing name in any state."""
        created_micros = datetime_to_micros(created_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT name
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if row is not None:
                raise ValueError(f"project already exists: {row['name']}")
            connection.execute(
                "INSERT INTO projects(name, created_at_utc) VALUES (?, ?)",
                (project, created_micros),
            )
        return project

    def create_activity(
        self,
        project: str,
        activity: str,
        created_at: datetime,
    ) -> tuple[str, str]:
        """Create a new activity under an existing, non-archived project."""
        created_micros = datetime_to_micros(created_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            project_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (project,),
            ).fetchone()
            if project_row is None:
                raise ValueError(f"project not found: {project}")
            canonical_project = str(project_row["name"])
            if project_row["archived_at_utc"] is not None:
                raise ValueError(f"project is archived: {canonical_project}")
            activity_row = connection.execute(
                """
                SELECT name
                FROM activities
                WHERE project_id = ? AND name = ? COLLATE NOCASE
                ORDER BY id
                LIMIT 1
                """,
                (int(project_row["id"]), activity),
            ).fetchone()
            if activity_row is not None:
                existing_activity = str(activity_row["name"])
                raise ValueError(
                    f"activity already exists: {canonical_project}/{existing_activity}"
                )
            connection.execute(
                """
                INSERT INTO activities(project_id, name, created_at_utc)
                VALUES (?, ?, ?)
                """,
                (int(project_row["id"]), activity, created_micros),
            )
        return canonical_project, activity

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
            project_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM projects
                WHERE name = ? COLLATE NOCASE
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
                if project_row["archived_at_utc"] is not None:
                    raise ValueError(f"project is archived: {project_row['name']}")
                project_id = int(project_row["id"])
                canonical_project = str(project_row["name"])

            activity_row = connection.execute(
                """
                SELECT id, name, archived_at_utc
                FROM activities
                WHERE project_id = ?
                  AND name = ? COLLATE NOCASE
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
                if activity_row["archived_at_utc"] is not None:
                    raise ValueError(f"activity is archived: {activity_row['name']}")
                activity_id = int(activity_row["id"])
                canonical_activity = str(activity_row["name"])

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

    def correct_completed(
        self,
        entry_id: int,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
    ) -> CompletedTimer:
        """Correct one completed entry after transactional target and overlap checks."""
        started_micros = datetime_to_micros(started_at)
        stopped_micros = datetime_to_micros(stopped_at)
        if stopped_micros <= started_micros:
            raise ValueError("corrected stop must be after start")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            original = connection.execute(
                """
                SELECT e.id, e.activity_id, p.name AS project,
                       a.name AS activity
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.id = ? AND e.stopped_at_utc IS NOT NULL
                """,
                (entry_id,),
            ).fetchone()
            if original is None:
                raise ValueError(f"unknown completed entry: {entry_id}")

            same_assignment = (
                project.casefold() == str(original["project"]).casefold()
                and activity.casefold() == str(original["activity"]).casefold()
            )
            if same_assignment:
                activity_id = int(original["activity_id"])
                canonical_project = str(original["project"])
                canonical_activity = str(original["activity"])
            else:
                activity_id, canonical_project, canonical_activity = (
                    self._resolve_selectable_activity(
                        connection,
                        project,
                        activity,
                        started_micros,
                    )
                )

            overlap_id = self._overlapping_entry_id(
                connection,
                started_micros,
                stopped_micros,
                exclude_entry_id=entry_id,
            )
            if overlap_id is not None:
                raise ValueError(f"corrected entry overlaps entry {overlap_id}")

            connection.execute(
                """
                UPDATE time_entries
                SET activity_id = ?, started_at_utc = ?, stopped_at_utc = ?, note = ?
                WHERE id = ?
                """,
                (activity_id, started_micros, stopped_micros, note, entry_id),
            )

        return CompletedTimer(
            entry_id=entry_id,
            project=canonical_project,
            activity=canonical_activity,
            started_at=started_at,
            stopped_at=stopped_at,
            note=note,
        )

    def delete_completed(self, entry_id: int) -> CompletedTimer:
        """Delete one completed entry without changing its target or active timer."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT e.id, p.name AS project, a.name AS activity,
                       e.started_at_utc, e.stopped_at_utc, e.note
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.id = ? AND e.stopped_at_utc IS NOT NULL
                """,
                (entry_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"unknown completed entry: {entry_id}")
            completed = self._completed_from_row(row)
            connection.execute("DELETE FROM time_entries WHERE id = ?", (entry_id,))
        return completed

    def create_completed(
        self,
        project: str,
        activity: str,
        started_at: datetime,
        stopped_at: datetime,
        note: str | None,
        created_at: datetime,
    ) -> CompletedTimer:
        """Create a closed entry after transactional target and overlap checks."""
        started_micros = datetime_to_micros(started_at)
        stopped_micros = datetime_to_micros(stopped_at)
        created_micros = datetime_to_micros(created_at)
        if stopped_micros <= started_micros:
            raise ValueError("manual entry stop must be after start")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            activity_id, canonical_project, canonical_activity = (
                self._resolve_selectable_activity(
                    connection,
                    project,
                    activity,
                    created_micros,
                )
            )
            overlap_id = self._overlapping_entry_id(
                connection,
                started_micros,
                stopped_micros,
            )
            if overlap_id is not None:
                raise ValueError(f"manual entry overlaps entry {overlap_id}")
            cursor = connection.execute(
                """
                INSERT INTO time_entries(
                    activity_id, started_at_utc, stopped_at_utc, note, created_at_utc
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    activity_id,
                    started_micros,
                    stopped_micros,
                    note,
                    created_micros,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the inserted entry ID")
            entry_id = cursor.lastrowid

        return CompletedTimer(
            entry_id=entry_id,
            project=canonical_project,
            activity=canonical_activity,
            started_at=started_at,
            stopped_at=stopped_at,
            note=note,
        )

    def edit_active(
        self,
        project: str,
        activity: str,
        note: str | None,
        updated_at: datetime,
    ) -> ActiveTimer:
        """Update active target and note while preserving identity and start."""
        updated_micros = datetime_to_micros(updated_at)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            original = connection.execute(
                """
                SELECT e.id, e.activity_id, e.started_at_utc, e.note,
                       p.name AS project, a.name AS activity
                FROM time_entries AS e
                JOIN activities AS a ON a.id = e.activity_id
                JOIN projects AS p ON p.id = a.project_id
                WHERE e.stopped_at_utc IS NULL
                """
            ).fetchone()
            if original is None:
                raise ValueError("no active timer to edit")

            same_assignment = (
                project.casefold() == str(original["project"]).casefold()
                and activity.casefold() == str(original["activity"]).casefold()
            )
            if same_assignment:
                activity_id = int(original["activity_id"])
                canonical_project = str(original["project"])
                canonical_activity = str(original["activity"])
            else:
                activity_id, canonical_project, canonical_activity = (
                    self._resolve_selectable_activity(
                        connection,
                        project,
                        activity,
                        updated_micros,
                    )
                )
            connection.execute(
                "UPDATE time_entries SET activity_id = ?, note = ? WHERE id = ?",
                (activity_id, note, int(original["id"])),
            )

        return ActiveTimer(
            entry_id=int(original["id"]),
            project=canonical_project,
            activity=canonical_activity,
            started_at=micros_to_datetime(int(original["started_at_utc"])),
            note=note,
        )

    @staticmethod
    def _resolve_selectable_activity(
        connection: sqlite3.Connection,
        project: str,
        activity: str,
        created_micros: int,
    ) -> tuple[int, str, str]:
        project_row = connection.execute(
            """
            SELECT id, name, archived_at_utc
            FROM projects
            WHERE name = ? COLLATE NOCASE
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
                (project, created_micros),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the inserted project ID")
            project_id = cursor.lastrowid
            canonical_project = project
        else:
            if project_row["archived_at_utc"] is not None:
                raise ValueError(f"project is archived: {project_row['name']}")
            project_id = int(project_row["id"])
            canonical_project = str(project_row["name"])

        activity_row = connection.execute(
            """
            SELECT id, name, archived_at_utc
            FROM activities
            WHERE project_id = ? AND name = ? COLLATE NOCASE
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
                (project_id, activity, created_micros),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return the inserted activity ID")
            activity_id = cursor.lastrowid
            canonical_activity = activity
        else:
            if activity_row["archived_at_utc"] is not None:
                raise ValueError(f"activity is archived: {activity_row['name']}")
            activity_id = int(activity_row["id"])
            canonical_activity = str(activity_row["name"])
        return activity_id, canonical_project, canonical_activity

    @staticmethod
    def _overlapping_entry_id(
        connection: sqlite3.Connection,
        started_micros: int,
        stopped_micros: int,
        *,
        exclude_entry_id: int | None = None,
    ) -> int | None:
        row = connection.execute(
            """
            SELECT id
            FROM time_entries
            WHERE (? IS NULL OR id <> ?)
              AND started_at_utc < ?
              AND (stopped_at_utc IS NULL OR stopped_at_utc > ?)
            ORDER BY started_at_utc, id
            LIMIT 1
            """,
            (
                exclude_entry_id,
                exclude_entry_id,
                stopped_micros,
                started_micros,
            ),
        ).fetchone()
        return int(row["id"]) if row is not None else None

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

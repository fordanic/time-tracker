from pathlib import Path

from pytest import MonkeyPatch

from time_tracker.infrastructure import local_files as local_files_module
from time_tracker.infrastructure.local_files import (
    clear_database_files,
    clear_local_files,
    database_files,
    local_files,
)
from time_tracker.infrastructure.paths import AgentPaths


def test_database_only_main_stops_agent_before_clearing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    calls: list[tuple[str, AgentPaths]] = []

    def record_clear(selected: AgentPaths) -> list[Path]:
        calls.append(("clear", selected))
        return []

    monkeypatch.setattr(AgentPaths, "defaults", lambda: paths)
    monkeypatch.setattr(
        local_files_module,
        "stop_agent",
        lambda selected: calls.append(("stop", selected)),
    )
    monkeypatch.setattr(
        local_files_module,
        "clear_database_files",
        record_clear,
    )

    result = local_files_module.main(["--database-only", "--yes"])

    assert result == 0
    assert calls == [("stop", paths), ("clear", paths)]


def test_clear_database_files_preserves_other_local_files(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    expected_files = database_files(paths)
    preserved_app_files = set(local_files(paths)) - set(expected_files)
    preserved_unrelated = tmp_path / "keep-me.txt"
    for path in local_files(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("app data", encoding="utf-8")
    preserved_unrelated.write_text("unrelated", encoding="utf-8")

    removed = clear_database_files(paths)

    assert removed == list(expected_files)
    assert all(not path.exists() for path in expected_files)
    assert all(path.exists() for path in preserved_app_files)
    assert preserved_unrelated.read_text(encoding="utf-8") == "unrelated"


def test_clear_local_files_only_removes_resolved_app_files(tmp_path: Path) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    expected_files = local_files(paths)
    preserved = tmp_path / "keep-me.txt"
    preserved.write_text("unrelated", encoding="utf-8")
    for path in expected_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("app data", encoding="utf-8")

    removed = clear_local_files(paths)

    assert removed == list(expected_files)
    assert all(not path.exists() for path in expected_files)
    assert preserved.read_text(encoding="utf-8") == "unrelated"

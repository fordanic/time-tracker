from pathlib import Path

from time_tracker.infrastructure.local_files import clear_local_files, local_files
from time_tracker.infrastructure.paths import AgentPaths


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

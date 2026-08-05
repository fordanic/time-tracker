from __future__ import annotations

from datetime import date, timedelta
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pytest import MonkeyPatch

from time_tracker.infrastructure import simulated_data
from time_tracker.infrastructure.paths import AgentPaths
from time_tracker.infrastructure.simulated_data import SeedSummary, simulated_entries


def test_simulated_entries_cover_45_days_without_weekends() -> None:
    local_timezone = ZoneInfo("Europe/Stockholm")
    end_date = date(2026, 7, 31)
    start_date = end_date - timedelta(days=44)

    entries = simulated_entries(end_date, local_timezone=local_timezone)

    expected_weekdays = {
        start_date + timedelta(days=offset)
        for offset in range(45)
        if (start_date + timedelta(days=offset)).weekday() < 5
    }
    entry_dates = {
        entry.started_at.astimezone(local_timezone).date() for entry in entries
    }
    assert entry_dates == expected_weekdays
    assert all(entry_date.weekday() < 5 for entry_date in entry_dates)
    assert all(entry.started_at < entry.stopped_at for entry in entries)
    assert all(
        previous.stopped_at <= current.started_at
        for previous, current in pairwise(entries)
    )
    assert {entry.project for entry in entries} == {
        "Client Portal",
        "Internal Operations",
        "Product Launch",
    }
    assert len({(entry.project, entry.activity) for entry in entries}) == 8
    assert any(entry.note is None for entry in entries)
    assert any(entry.note for entry in entries)
    assert len({entry.stopped_at - entry.started_at for entry in entries}) > 1


def test_main_requires_confirmation_before_stopping_agent(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        simulated_data,
        "stop_agent",
        lambda paths: pytest.fail(f"unexpected stop for {paths}"),
    )

    with pytest.raises(SystemExit):
        simulated_data.main([])


def test_main_stops_agent_before_seeding(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    paths = AgentPaths.in_directory(tmp_path)
    calls: list[str] = []

    def record_stop(selected: AgentPaths) -> None:
        assert selected == paths
        calls.append("stop")

    def record_seed(database: Path, *, end_date: date) -> SeedSummary:
        assert database == paths.database
        calls.append("seed")
        return SeedSummary(
            start_date=end_date - timedelta(days=44),
            end_date=end_date,
            project_count=3,
            activity_count=8,
            entry_count=100,
        )

    monkeypatch.setattr(AgentPaths, "defaults", lambda: paths)
    monkeypatch.setattr(simulated_data, "stop_agent", record_stop)
    monkeypatch.setattr(simulated_data, "seed_simulated_data", record_seed)

    result = simulated_data.main(["--yes"])

    assert result == 0
    assert calls == ["stop", "seed"]

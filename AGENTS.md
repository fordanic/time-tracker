# Agent Guidance

Before changing the repository, read `README.md`,
`docs/mvp-requirements.md`, and `docs/architecture.md`. Before committing, follow
`docs/commits.md`.

The MVP document is authoritative for product behavior and scope. The architecture
document is authoritative for technical choices and boundaries. Update the
relevant document when a decision changes; do not create a second source of truth.

## Current phase

The repository has its initial package and test scaffold. The next milestone is
the cross-platform walking skeleton described in `README.md` and
`docs/architecture.md`.

## Canonical development commands

Sync the locked environment before running checks:

```shell
uv sync --all-groups --locked
```

Run every check before committing:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

When a tier contains tests, use `uv run pytest tests/unit`,
`tests/integration`, or `tests/e2e` while iterating on it, but finish with the
complete suite. Apply formatting with `uv run ruff format .`; do not substitute
a different formatter or package manager.

## Working rules

- Keep business logic independent of the TUI and future GUI.
- Treat the background process as the single database writer.
- Persist timer transitions before reporting success.
- Inject clocks and external services so core behavior is deterministic in tests.
- Isolate operating-system-specific behavior behind narrow adapters.
- Do not add deferred features to the MVP without changing its requirements.
- Add tests with implementation changes and run the relevant checks.
- Preserve user data across crashes, restarts, and migrations.

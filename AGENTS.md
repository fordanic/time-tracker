# Agent Guidance

Before changing the repository, read `README.md`,
`docs/top-level-requirements.md`, `docs/feature-requirements/README.md`, and
`docs/architecture.md`. Before committing, follow `docs/commits.md`.

The top-level requirements document is authoritative for durable product behavior
and scope. The architecture document is authoritative for technical choices and
boundaries. Feature requirements record approved additional feature behavior and
must conform to both authoritative documents. Update the relevant document when a
decision changes; do not create a second source of truth.

## Current phase

Use the `README.md` Status section as the source of truth for current
implementation and validation status. Close the recorded validation gaps while
beginning the TUI work described in `docs/competitive-assessment.md`. Before
implementing a selected roadmap slice, define its behavior and acceptance
criteria in an individual file under `docs/feature-requirements/`. Update
`docs/top-level-requirements.md` when a top-level product rule or boundary changes
and `docs/architecture.md` when a technical choice or boundary changes.

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

- Keep business logic independent of the TUI.
- Treat the background process as the single database writer.
- Persist timer transitions before reporting success.
- Inject clocks and external services so core behavior is deterministic in tests.
- Isolate operating-system-specific behavior behind narrow adapters.
- Do not add feature behavior without updating the feature requirements, and do
  not let feature requirements conflict with the top-level requirements or
  architecture.
- Add tests with implementation changes and run the relevant checks.
- Preserve user data across crashes, restarts, and migrations.

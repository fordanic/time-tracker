# Agent Guidance

Before changing the repository, read `README.md`,
`docs/mvp-requirements.md`, and `docs/architecture.md`. Before committing, follow
`docs/commits.md`.

The MVP document is authoritative for product behavior and scope. The architecture
document is authoritative for technical choices and boundaries. Update the
relevant document when a decision changes; do not create a second source of truth.

## Current phase

The repository is ready for initial scaffolding. Canonical development commands
do not exist yet; add only commands that have been implemented and verified.

## Working rules

- Keep business logic independent of the TUI and future GUI.
- Treat the background process as the single database writer.
- Persist timer transitions before reporting success.
- Inject clocks and external services so core behavior is deterministic in tests.
- Isolate operating-system-specific behavior behind narrow adapters.
- Do not add deferred features to the MVP without changing its requirements.
- Add tests with implementation changes and run the relevant checks.
- Preserve user data across crashes, restarts, and migrations.

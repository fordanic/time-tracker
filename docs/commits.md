# Commit Guidelines

Commits should be small, coherent, and useful to a reviewer on their own. Each
commit must leave the repository in a valid state whenever practical.

## Before committing

1. Review `git status --short` and `git diff`.
2. Run the relevant format, lint, type-check, and test commands documented in
   `AGENTS.md`. Until those commands exist, perform the available documentation
   and consistency checks.
3. Stage only files and hunks that belong to the same change.
4. Review `git diff --cached` before creating the commit.
5. Check that no secrets, credentials, local paths, editor files, or generated
   artifacts are included unintentionally.

Keep tests with the behavior they verify and documentation with the decision or
interface it describes. Separate unrelated refactoring, formatting, and dependency
changes.

## Commit messages

Use this form:

```text
<type>(<optional scope>): <imperative summary>

<optional body explaining why and notable consequences>

<optional footer>
```

Use one of these types:

- `feat`: user-visible functionality.
- `fix`: defect correction.
- `docs`: documentation only.
- `refactor`: behavior-preserving restructuring.
- `test`: tests without production behavior changes.
- `build`: build system or dependency changes.
- `ci`: continuous-integration changes.
- `perf`: performance improvement.
- `chore`: maintenance not covered above.

The summary should:

- Complete the sentence “This commit will …”.
- State the outcome, not the editing activity.
- Use lowercase after the colon, omit the final period, and stay concise.
- Avoid vague wording such as “updates”, “changes”, or “fix stuff”.

Add a body when the motivation, trade-off, migration, or non-obvious behavior
matters. Explain why the change is needed and what a reviewer should know; do not
repeat the diff. Reference an issue in the footer when applicable. Mark breaking
changes with `BREAKING CHANGE:`.

Examples:

```text
docs: define MVP tracking behavior

feat(timer): switch activities atomically

fix(storage): preserve active timer after restart

refactor(ipc): isolate JSON message validation
```

## History hygiene

- Do not rewrite shared or published history without coordination.
- Do not combine unrelated work merely to reduce the number of commits.
- Fix up local review corrections before publishing when it improves clarity.
- Prefer a short sequence of meaningful commits over one large catch-all commit.

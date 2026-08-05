# Review entry deletion and duration display

**Status:** Implemented

## Purpose

Let users remove an unwanted completed entry from Review and make Review
durations easier to scan at minute precision.

## Required behavior

- In completed-entry mode, provide a Delete selected entry action next to the
  existing selected-entry actions.
- The first activation asks for explicit confirmation of the canonical selected
  entry. A second activation for the same entry performs the deletion.
- If the selected row represents one local-day segment of an entry that crosses
  midnight, delete the whole canonical completed entry.
- After deletion, refresh completed history, totals, summaries, filters, exports,
  and recent activities from their existing shared sources.
- In every Review representation, display durations as `Xh YYm`, with an
  unpadded non-negative hour count and a two-digit minute count.
- Round every displayed Review duration up to the next whole minute. An exact
  whole-minute duration is unchanged, and zero displays as `0h 00m`.
- Keep Track's live elapsed duration, stop messages, and today's completed total
  at their existing second precision.

## Invariants and error handling

- Deletion is owned by the background agent and persisted before success is
  reported. It removes only the selected completed entry and never changes the
  active timer or its reminder deadline.
- Reject an unknown or active entry identifier without changing storage.
- Summary rows and daily-total rows cannot be deleted.
- Changing the selected entry requires a fresh confirmation, preventing a stale
  confirmation from deleting another row.
- Duration presentation does not change stored timestamps or exported duration
  seconds.

## Acceptance criteria

1. A user can select a completed-entry row, activate Delete selected entry twice,
   and see the entry disappear from Review and subsequent exports.
2. The first activation does not mutate storage, changing rows invalidates that
   confirmation, and summary/day-total rows are rejected.
3. Deleting a cross-midnight segment removes the one canonical entry while an
   active timer and its timestamps remain unchanged.
4. Review details, daily summaries, range totals, and day totals display
   `Xh YYm`, rounding one or more remaining seconds upward to the next minute.
5. Unit, SQLite integration, IPC integration, and Textual tests cover deletion,
   confirmation, refresh behavior, and duration rounding.

## Documentation impact

- Top-level requirements authorize permanent completed-entry deletion after
  explicit confirmation. Architecture records the agent-owned transaction and
  protocol version 6. No schema migration is required.

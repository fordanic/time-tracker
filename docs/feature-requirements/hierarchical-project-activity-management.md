# Hierarchical project and activity management

**Status:** Implemented

## Purpose

Let users browse and select archive targets instead of retyping exact project and
activity names.

## Required behavior

- Manage displays all selectable projects and their activities in one
  hierarchical tree.
- Selecting a project or activity enables one archive action for that exact node.
- Manage displays archived projects and activities in a second hierarchical tree
  and restores the selected exact node.
- F8 and F9 retain project-archive and activity-archive behavior for the
  corresponding selected node.
- Refresh both trees whenever Manage is selected so changes made while another
  view is active are visible immediately.
- Refresh both trees after every successful archive or restore and keep a
  sensible neighboring selection when possible.
- Size both trees to the available terminal height: at least twelve rows each on
  terminals of thirty rows or more, and a reduced height on shorter terminals so
  the remaining Manage controls stay reachable by scrolling.

## Invariants and error handling

- Archiving still requires a second explicit confirmation naming the canonical
  target and warning that a running timer continues.
- An activity cannot be restored while its parent project is archived.
- Restoring a project does not change independent child archive flags.
- Tree selection and expansion are presentation-only and never change storage.

## Acceptance criteria

1. Active projects and activities are visible without typing and either node kind
   can be selected and archived after confirmation.
2. Archived projects and activities are visible with parent context and either
   node kind can be selected for restore.
3. Parent restore ordering, active-timer preservation, exact-target
   confirmation, and reserved-name behavior remain unchanged.
4. Both trees show at least twelve rows on a tall terminal and shrink on a short
   one without hiding the archive, restore, or preparation controls.
5. Textual tests cover project and activity selection, confirmation, refresh,
   restore ordering, empty states, tree height at both breakpoints, and F8/F9.

## Documentation impact

- Neither top-level requirements nor architecture changes. Existing archive
  behavior is presented through a safer TUI selection model.

# Status

## Current Phase
Sub-2 — Ledger Repos + Balance APIs. **IN_PROGRESS**.

## Active Subplan
[`docs/plans/2026-04-25-playto-sub-2.md`](plans/2026-04-25-playto-sub-2.md)

## Spec
[`docs/plans/2026-04-25-playto-spec.md`](plans/2026-04-25-playto-spec.md) — frozen 2026-04-25.

## Roadmap
[`docs/ROADMAP.md`](ROADMAP.md) — 7 phases.

## Worktree
- Path: `.worktrees/playto-impl/`
- Branch: `feature/payout-engine` (off `main`)

## Completed
- Sub-1: 26/26 tests passing. Last commit: `776ba51`
  - M1.1 `36245a8` feat(scaffold): django project + psycopg3 + pyproject
  - M1.2 `c7c881f` chore(structure): backend layered folder skeleton
  - M1.3 `348ec4e` feat(domain): enums, transitions, errors, money helpers
  - M1.4 `14f20f1` feat(models): merchants + payouts schema with constraints
  - M1.5 `6cd530a` test(config): pytest-django against real postgresql
  - M1.6 `776ba51` feat(seed): management command + credits + bank accounts

## Resume Point
Begin sub-2 milestone M2.1 (merchant_repo).

## Active Issues
None.

## Sync Footer
Synced: 2026-04-25 | Commit: 776ba51

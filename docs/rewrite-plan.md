# Rewrite plan

This started as a fork of treygoff24/rlcoach. That project has never had a license, so the code it wrote is still its author's. The aim is a tool that's entirely ours and only as big as it needs to be: the dashboard, the mistake reviews and coaching, and what Claude reads in chat (the local API, the database and a few commands).

## How

- Delete what nothing uses. Deleting is the cleanest answer to whose code it is.
- Rewrite what's left from what it does: its tests, the Ballchasing numbers and its output on real games. Don't rework the old files in place.
- Each phase lands on `main` on its own, through a short-lived branch.
- Inherited tests go with the module they test. New code gets new tests.

## Checking a phase

1. Back up `~/.rlcoach/data`, reload every game on the new code, and compare every value in `replays`, `player_game_stats`, `game_reviews`, `review_mistakes` and `review_goals` with the backup. Anything that changed has to be explained.
2. Run `tests/analysis/test_ballchasing_parity.py`.
3. Run every check in `AGENTS.md`.

## Where it stands

Lines still written by the original author, by `git blame -w -M -C`:

| | Before (2026-11-07) | After phase 1 |
| --- | --- | --- |
| `src/` and `parsers/` | 22,916 of 27,884 (82%) | 14,260 of 19,292 (74%) |
| `tests/` | 18,480 of 23,594 (78%) | 10,784 of 15,758 (68%) |
| `gui/src/` | 1,074 of 3,792 (28%) | 1,054 of 3,772 (28%) |

## Phase 1: delete what nothing reads (done 2026-11-07)

- The JSON report file written for every game, its schema and validation, the goldens and the Markdown report, with the `analyze` and `report-md` commands.
- Ten analyzers whose output reached nothing: mechanics, xG, ball prediction, defense, recovery, passing, insights, heatmaps, and the challenge and kickoff summaries.
- 32 of the 57 per-player stat columns, and `json_report_path`.
- `GET /replays/{id}/full`, the `benchmarks` command and the parser corpus script.
- The metric catalog, rewritten as a list of which way is better for each stored stat.
- `rlcoach ingest` now loads and reviews replays, so a game from outside the watch folder can get in.

Checked by reloading all 42 games: every kept value in the replays, players, stats, reviews, review goals and review mistakes matched the database from before, and only the benchmarks' import times changed.

## Phase 2: the plumbing

The command line, config, loading and storage, and the API. The behaviour is simple to state and easy to check.

- `cli.py` (46% his), `config.py`, `config_templates.py`, `ingest.py`, `watcher.py`, `pipeline.py`, `errors.py`
- `db/writer.py`, `db/models.py` (57% his), `db/session.py`
- `api/app.py`, `api/routers/analysis.py`, `api/routers/games.py`, `api/routers/players.py`, `benchmarks.py`
- `analysis/patterns.py` and `analysis/weaknesses.py`, which the Benchmarks page uses
- `identity.py` and `utils/identity.py`, which do overlapping jobs
- The `null` parser adapter and header-only mode. `null` is the default adapter today, so this means making the Rust parser the only one.

## Phase 3: the core the mistake detector stands on

- `normalize.py`
- `events/`: goals, touches, challenges, boost, demos, kickoffs, timeline, types
- `analysis/`: fundamentals, boost, movement, positioning. Compute only the stats the database stores, then shrink the parity test to those.
- `report.py`, which runs one replay end to end
- `field_constants.py`, `physics_constants.py`

`analysis/mistakes.py` calls `detect_goals`, `detect_touches`, `detect_challenge_events`, `normalize.build_timeline`, the parser's frame types and the field constants. Keep those shapes, or change `mistakes.py` in the same step.

The sample replays in `Replay_files/` and their Ballchasing CSVs also came with the original project. Replace them with your own replays and your own Ballchasing export as the tests are rewritten.

## Phase 4: the Rust parser

- `parsers/rlreplay_rust/src/lib.rs` (3,057 lines, 83% his), `arena_tables.rs`, the parts of `pads.rs` that are still his
- `parser/rust_adapter.py`, `parser/types.py`, `parser/interface.py`, `docs/parser_adapter.md`

boxcars, the replay library underneath, is a third-party MIT crate and stays. The build is fragile on this PC (see `AGENTS.md`), and a parser can pass its tests while missing data on real replays, so the reload comparison matters most here.

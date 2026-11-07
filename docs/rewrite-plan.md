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

| | Before (2026-11-07) | After phase 1 | After phase 2 |
| --- | --- | --- | --- |
| `src/` and `parsers/` | 22,916 of 27,884 (82%) | 14,260 of 19,292 (74%) | 10,456 of 16,741 (62%) |
| `tests/` | 18,480 of 23,594 (78%) | 10,784 of 15,758 (68%) | 6,544 of 12,947 (51%) |
| `gui/src/` | 1,074 of 3,792 (28%) | 1,054 of 3,772 (28%) | 1,054 of 3,772 (28%) |

The counts leave out the benchmark data files in `src/rlcoach/data/`. Blame still gives him 639 of the 2,451 lines in the files phase 2 rewrote: lines that came out the same character for character, such as imports, the config's field names, and the API's parameters and response fields, which the dashboard depends on.

## Phase 1: delete what nothing reads (done 2026-11-07)

- The JSON report file written for every game, its schema and validation, the goldens and the Markdown report, with the `analyze` and `report-md` commands.
- Ten analyzers whose output reached nothing: mechanics, xG, ball prediction, defense, recovery, passing, insights, heatmaps, and the challenge and kickoff summaries.
- 32 of the 57 per-player stat columns, and `json_report_path`.
- `GET /replays/{id}/full`, the `benchmarks` command and the parser corpus script.
- The metric catalog, rewritten as a list of which way is better for each stored stat.
- `rlcoach ingest` now loads and reviews replays, so a game from outside the watch folder can get in.

Checked by reloading all 42 games: every kept value in the replays, players, stats, reviews, review goals and review mistakes matched the database from before, and only the benchmarks' import times changed.

## Phase 2: the plumbing (done 2026-11-07)

Rewritten from what each part does, with new tests built from `tests/fixtures/builders.py` and the replays in `Replay_files/`:

- **One parse per game.** Loading a replay parsed and normalized it twice, once for the stats and again for the mistake review, and ran a pure-Python CRC check on it twice at 2 to 7 s each. `game.py` now reads a replay once into a `Game` (header, frames and events) that the stats and the review share, and `replay_file.py` checks the CRC with zlib in about 3 ms. Loading all 42 games on this PC took 752.6 s on `main` (17.9 s a game, 9.1 to 31.4 s) and 308.3 s on the new code (7.3 s a game, 3.5 to 13.0 s).
- **Game mode is data.** `modes.py` names each mode by its arenas, says whether the mistake rules fit it, and turns a header into a playlist. The stored playlist, the review's arena check, the config check and the benchmark files all read it. Hoops becomes one more `Mode` row with a playlist of its own once the rules fit its field.
- `pipeline.py` and `db/games.py` replace `ingest.py`, `db/writer.py` and `errors.py`. A game is stored in one transaction.
- The Rust parser is the only one. The `null` adapter, the adapter interface, the backend chain and header-only mode are gone.
- `identity.py` takes in `utils/identity.py`.
- `compare.py` replaces `analysis/patterns.py` and `analysis/weaknesses.py`, and the stats routes moved from `api/routers/analysis.py` to `api/routers/stats.py`.
- `cli.py`, `config.py` (with the template folded in), `watcher.py`, `db/models.py`, `db/session.py`, `benchmarks.py`, the app and the games and players routes are rewritten. `version.py` and `config_templates.py` are gone.

What behaves differently:

- Tournament games are filed by team size, where they were always STANDARD, and Knockout games are filed as EXTRA_MODE with Hoops and Dropshot, where they went by team size. None of the 42 games is either, so nothing stored changed, but a new one would show under a different playlist on the dashboard.
- A replay the parser reads no frames from fails to load, with the reason, instead of being stored from its header alone.
- A game you aren't in stores nothing. A player's name is the one from their most recently played game, whatever order games load in.
- The watcher waits for a file to settle between scans instead of sleeping on each one, and loads the oldest replay first.
- A stat whose benchmark has no spread is left out of weaknesses instead of failing, and an unknown period is a 400.
- `replays.match_id`, which nothing read, CORS, and the bare `/api/` route are gone. The dashboard is served from the same port, so it needs neither.

Left for phase 3: `report.py` now only reports what the database stores, but its analysis call is still the inherited one. `events/goals.py`, `analysis/__init__.py` and `normalize.py` still have branches for header-only games, which can no longer reach them.

Checked three ways:

- Every endpoint the dashboard calls, 228 calls in all, gave the same response on `main` and on the new code against a copy of the real database, apart from `/health`'s timestamp.
- Reloading all 42 games on the new code into a scratch home gave the same value in every shared column of `replays`, `players`, `player_game_stats`, `game_reviews`, `review_mistakes` and `review_goals` as the live database, and as a fresh reload on `main`. The only column gone is `replays.match_id`, which was empty in every row.
- `tests/analysis/test_ballchasing_parity.py` and every check in `AGENTS.md` pass. The suite passes at every commit.

## Proposal: keep each game's events (not built)

The database keeps each player's totals per game, the review's mistakes and every goal. The events behind them, each touch and challenge with its time, players and position, are thrown away after loading, so a question across games means parsing every replay again, about 7.3 s each.

Keeping them is small. One game has about 160 touches, 20 challenges, 4 demos and 7 kickoffs, so 42 games come to about 8,000 rows, under a megabyte. A table per kind, written in the same transaction as the game, adds milliseconds to a load. Games loaded before it need one reload.

One use: "Do you lose more 50/50s in your own half when you're last back, and is that getting better?" Each challenge already has its location, depth, both players and the winner, so with them stored this is one query over every game, which Claude can answer in chat and the Coach page could chart.

The catch is phase 3. It rewrites `events/`, and the review finds contacts its own way (`find_contacts` in `mistakes.py`), so stored touches would follow definitions that are about to change. Build it after phase 3, or store only challenges now and reload when they change.

## Phase 3: the core the mistake detector stands on

- `normalize.py`
- `events/`: goals, touches, challenges, boost, demos, kickoffs, timeline, types
- `analysis/`: fundamentals, boost, movement, positioning. Compute only the stats the database stores, then shrink the parity test to those.
- `report.py`, which turns a loaded game into the stats the database stores
- `field_constants.py`, `physics_constants.py`

`analysis/mistakes.py` reads a `Game` from `game.py`, which `detect_goals`, `detect_touches`, `detect_challenge_events` and `normalize.build_timeline` fill, and it uses the parser's frame types and the field constants. Keep those shapes, or change `mistakes.py` in the same step.

The sample replays in `Replay_files/` and their Ballchasing CSVs also came with the original project. Replace them with your own replays and your own Ballchasing export as the tests are rewritten.

## Phase 4: the Rust parser

- `parsers/rlreplay_rust/src/lib.rs` (3,057 lines, 83% his), `arena_tables.rs`, the parts of `pads.rs` that are still his
- `parser/rust_adapter.py`, `parser/types.py`, `docs/parser_adapter.md`

boxcars, the replay library underneath, is a third-party MIT crate and stays. The build is fragile on this PC (see `AGENTS.md`), and a parser can pass its tests while missing data on real replays, so the reload comparison matters most here.

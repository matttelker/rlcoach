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

| | Before (2026-11-07) | After phase 1 | After phase 2 | After phase 3 | After phase 4 (2026-11-08) |
| --- | --- | --- | --- | --- | --- |
| `src/` and `parsers/` | 22,916 of 27,884 (82%) | 14,260 of 19,292 (74%) | 10,456 of 16,741 (62%) | 4,972 of 11,706 (42%) | 1,178 of 9,560 (12%) |
| `tests/` | 18,480 of 23,594 (78%) | 10,784 of 15,758 (68%) | 6,544 of 12,947 (51%) | 1,291 of 7,450 (17%) | 398 of 7,345 (5%) |
| `gui/src/` | 1,074 of 3,792 (28%) | 1,054 of 3,772 (28%) | 1,054 of 3,772 (28%) | 1,054 of 3,772 (28%) | 1,053 of 4,575 (23%) |

The counts leave out the benchmark data files in `src/rlcoach/data/`. Kickoff coaching came between phases 3 and 4, so `main` before phase 4 stood at 4,972 of 12,555 (40%) in `src/` and `parsers/`, and 1,291 of 8,125 (16%) in `tests/`. Blame still gives him 639 of the 2,451 lines in the files phase 2 rewrote: lines that came out the same character for character, such as imports, the config's field names, and the API's parameters and response fields, which the dashboard depends on. In the files phase 3 rewrote it gives him 393 of 1,649, nearly all blank lines, closing brackets, docstring quotes and import lines. In the files phase 4 rewrote it gives him 155 of 2,041: blank lines, closing braces, imports, and the field names in `parser/types.py`, which normalize, the events and the stats read.

What's left is spread thin. No file holds more than 91 of his lines. The most are in the files phase 2 rewrote (the API's routers, the config, the models, the CLI) and in `tests/fixtures/builders.py`, whose function signatures every test calls.

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

Phase 3 has rewritten `events/` and left every event as it was, so the definitions are settled. The review still finds contacts its own way (`find_contacts` in `mistakes.py`), apart from the touches.

Kickoffs are stored since kickoff coaching (2026-11-07): `review_kickoffs` and `review_kickoff_cars` hold every car's kickoffs with each review, and `rlcoach reviews --redo` fills them in. They went with the review rather than the game because `ingest` skips a stored game, so only the review could fill in the games already loaded. The other kinds could follow the same way.

## Phase 3: the core the mistake detector stands on (done 2026-11-07)

Rewritten from what each part does, with new tests built from `tests/fixtures/builders.py` and checked against real replays:

- **Stats.** `analysis/` works out the 20 columns the database stores and nothing else, from the `Game`: the scoreboard and demos (`fundamentals.py`), boost (`boost.py`), speed (`movement.py`) and position (`positioning.py`), each over a player's own frames (`tracks.py`). The per-team pass and the stats nothing stored are gone. `report.py` turns a game into what `db/games.py` stores, whose `STAT_COLUMNS` names the stats. Working out the stats for 48 replays took 53.4 s on `main` and 14.1 s now.
- **Events.** Goals with their scorer and likely assist, touches, 50/50s, demos, kickoffs and boost pickups, one module each in `events/`. Kickoffs keep how each car played them: its role, its approach (speedflip, fake, and so on), the boost it used and its time to the ball, for the kickoff coaching to come. The fallback for replays without countdowns, the parser's kickoff markers, the team-side guessing, the pickup merge pass and the debug dump are gone.
- **Boost pickups** come from the pad events. A replay with none, or with fewer than half as many as its cars' boost rises, reads them from the rises instead, at the nearest pad of the rise's size.
- **Normalize** takes the parser's dicts straight into frames that carry only what the events, stats and review read. On the 48 replays it took 128.6 s on `main` and 69.4 s now, with every field anything reads the same.
- **Constants.** The field's walls, goals and 34 boost pads, numbered as the Rust parser numbers them, which a test now checks. `schemas/boost_pad_tables.json`, which only its own test read, the field helpers and the physics values nothing used are gone.
- **Test replays.** The sample replays and the Ballchasing CSV that came with the original project are gone. The tests that read real replays use your own from the folder `RLCOACH_TEST_REPLAYS` names, outside git (see `AGENTS.md`). The parity test compares three of your games, 18 players, with your Ballchasing exports.
- `Game.events`, which nothing read, is gone.

What behaves differently:

- Your Hoops game of 2026-11-01 is the only replay with no pad events, so its pickups come from boost rises. The rewritten rule moves its boost stolen (157 to 127 for you, 93 to 105 and 95 to 119 for two others) and your boost collected by 1 (1,075 to 1,076, BCPM 197.86 to 198.04). You agreed to this. On a Hoops field, Soccar pad positions make every steal a guess. On your 47 Soccar games the new rule is as close to the pad events as the old one: off by 17.3 boost stolen per player per game, where the old was off by 17.2.
- A replay whose frames show no countdown has no kickoffs. `main` guessed them then. All 48 replays have countdowns, so nothing stored changed.
- CI runs no test that reads a real replay, since your replays aren't in the repo. Before, it ran them on the samples. Locally they run whenever `RLCOACH_TEST_REPLAYS` is set.
- The parity bounds are measured on your games, so some are looser than on the old sample: time at zero and full boost read up to 20% and 28% high for a few players, stolen up to 23%. Two differences are known and written into the test: Ballchasing gives 2 goals from 1 shot 200% where we stop at 100%, and doesn't count the demo with no attacker at the end of E8D9.

Left for phase 4: `parser/types.py` still defines the frame fields `normalize.py` no longer fills, such as the driving inputs and the jump flags, and the parser tests are inherited ones pointed at your replays.

Checked:

- After every commit, the stored stats, reviews and events of 48 replays (the 42 live games and the 6 old samples, while they lasted) matched `main`'s, except the Hoops game's boost. All 314 kickoffs matched in every per-car field. The suite passes at every commit.
- Reloading all 42 games into scratch homes, on `main` and on the new code, gave the same value in every shared column of `replays`, `players`, `player_game_stats`, `game_reviews`, `review_mistakes` and `review_goals`, except those five Hoops values. `main`'s reload matched the live database exactly. Run side by side, the reloads took 200.9 s on `main` (4.8 s a game) and 109.3 s on the new code (2.6 s a game).
- Every endpoint the dashboard calls, 228 calls in all, gave the same response on `main` and on the new code against a copy of the real database, apart from `/health`'s timestamp.
- `tests/analysis/test_ballchasing_parity.py` and every check in `AGENTS.md` pass.

## Phase 4: the Rust parser (done 2026-11-08)

Rewritten from what it does, checked frame by frame against `main`'s output on all 42 games, with new tests: synthetic frames in Rust for the walk, the players and the pads, and your replays for what the module hands over (`tests/parser/`). boxcars, the replay library underneath, is a third-party MIT crate and stays, pinned at 0.13.0. [docs/parser.md](parser.md) says what the parser reads and how.

- **Rust.** `lib.rs` (3,057 lines, 83% his) is now 161 lines: the module's two functions, `header` and `frames`, and the conversion to Python values. The walk through the frames is `game.rs`, which player each car is `roster.rs`, and pad pickups `pads.rs`, each with its own tests. `arena_tables.rs` is gone: Python passes the pad table in, so the pads live in `field_constants.py` alone.
- **Python.** `rust_adapter.py` and `parser/errors.py` are gone. `parser/__init__.py` calls the module, `parser/header.py` turns the header's properties into a `Header`, and `parser/types.py` holds only what normalize fills. Normalize reads the parser's tuples straight into frames.
- **What the parser hands over** is only what normalize, the events, the stats and the review read. Gone: the driving inputs, the jump, flip and boost flags, the ball's spin, Euler angles, the camera settings, loadouts, the game's stat events, tick marks, kickoff markers, pad respawns and pickups with no player, the diagnostics and quality warnings, and the header fields nothing read (engine build, match id, mutators, overtime, match length, highlights).
- **Speed.** Reading a replay (header, frames and normalize) took 91.1 s for the 42 games on `main` and 20.8 s now, of which the Rust walk is 3.7 s. Reloading all 42 into scratch homes, back to back, took 90.8 s on `main` (2.2 s a game) and 38.6 s on the new code (0.9 s a game).

What behaves differently, none of it in your 42 games:

- A replay whose network data boxcars can't decode raises with boxcars' reason. `main` returned it with diagnostics and no frames, which already stopped the load.
- The pickup format from before `NewReplicatedPickupData`, a flag rather than a counter, isn't read, so such a replay's pickups come from boost rises.
- A replay whose header lists no players gets no stand-in numbering: only cars with a PRI are listed, past the (no) rows.
- The playlist always comes from the match type and team size. `main` went by `PlaylistID` when a header had one, which made it UNKNOWN. None of your 42 headers has one.
- The overtime flag in old headers isn't read. The report already went by the overtime kickoff, since current headers carry no flag.

Checked:

- Reloading all 42 games into scratch homes, on `main` and on the new code, gave the same value in every shared column of `replays`, `players`, `player_game_stats`, `game_reviews`, `review_mistakes`, `review_goals`, `review_kickoffs` and `review_kickoff_cars`. `main`'s reload matched the live database exactly.
- Every endpoint the dashboard calls, 228 calls in all, gave the same response on `main` and on the new code against a copy of the real database, apart from `/health`'s timestamp.
- `tests/analysis/test_ballchasing_parity.py` and every check in `AGENTS.md` pass.

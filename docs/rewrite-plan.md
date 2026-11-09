# Rewrite plan

This started as a fork of treygoff24/rlcoach. That project has never had a license, so the code it wrote is still its author's. The aim is a tool that's entirely ours and only as big as it needs to be: the dashboard, the mistake reviews and coaching, and what Claude reads in chat (the local API, the database and a few commands).

## How

- Delete what nothing uses. Deleting is the cleanest answer to whose code it is.
- Rewrite what's left from what it does: its tests, the Ballchasing numbers and its output on real games. Don't rework the old files in place.
- Each phase lands on `main` on its own, through a short-lived branch.
- Inherited tests go with the module they test. New code gets new tests.

## Checking a phase

1. Back up `~/.rlcoach/data`, reload every game on the new code, and compare every value in `replays`, `player_game_stats`, `game_reviews`, `review_mistakes`, `review_goals`, `review_kickoffs`, `review_kickoff_cars`, `review_touches`, `review_challenges` and `review_demos` with the backup. Anything that changed has to be explained.
2. Run `tests/analysis/test_ballchasing_parity.py`.
3. Run every check in `AGENTS.md`.

## Where it stands

Lines still written by the original author, by `git blame -w -M -C`:

| | Before (2026-11-07) | After phase 1 | After phase 2 | After phase 3 | After phase 4 (2026-11-08) | After the dashboard (2026-11-09) |
| --- | --- | --- | --- | --- | --- | --- |
| `src/` and `parsers/` | 22,916 of 27,884 (82%) | 14,260 of 19,292 (74%) | 10,456 of 16,741 (62%) | 4,972 of 11,706 (42%) | 1,166 of 9,794 (12%) | 1,157 of 10,261 (11%) |
| `tests/` | 18,480 of 23,594 (78%) | 10,784 of 15,758 (68%) | 6,544 of 12,947 (51%) | 1,291 of 7,450 (17%) | 398 of 7,409 (5%) | 398 of 7,749 (5%) |
| `gui/src/` | 1,074 of 3,792 (28%) | 1,054 of 3,772 (28%) | 1,054 of 3,772 (28%) | 1,054 of 3,772 (28%) | 1,053 of 4,575 (23%) | 492 of 5,044 (10%) |

The counts leave out the benchmark data files in `src/rlcoach/data/`. Kickoff coaching came between phases 3 and 4, so `main` before phase 4 stood at 4,972 of 12,555 (40%) in `src/` and `parsers/`, and 1,291 of 8,125 (16%) in `tests/`, and the dashboard's new lines are its, not phase 4's. Blame still gives him 639 of the 2,451 lines in the files phase 2 rewrote: lines that came out the same character for character, such as imports, the config's field names, and the API's parameters and response fields, which the dashboard depends on. In the files phase 3 rewrote it gives him 393 of 1,649, nearly all blank lines, closing brackets, docstring quotes and import lines. In the files phase 4 rewrote it gives him 155 of 2,041: blank lines, closing braces, imports, and the field names in `parser/types.py`, which normalize, the events and the stats read.

The dashboard's rewrite touched only `gui/src/`. The other two rows moved between phase 4 and it with the changes made on purpose and the game's own counts. Just before it, `main` stood at 1,020 of 4,616 (22%) in `gui/src/`.

What's left is spread thin. No file holds more than 90 of his lines, apart from the dashboard's `types/api.ts` with 109, nearly all of them the API's field names. The most are in the files phase 2 rewrote (the API's routers, the config, the models, the CLI) and in `tests/fixtures/builders.py`, whose function signatures every test calls.

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

## Keeping each game's events (done 2026-11-09)

The database kept each player's totals per game, the review's mistakes, every goal and every kickoff. The touches, 50/50s and demos behind them were thrown away after loading, so a question across games meant reading every replay again. Now each review keeps them next to its kickoffs, and the question is one query.

- **Where.** `review_touches`, `review_challenges` and `review_demos` hang off the review, as `review_kickoffs` does, and `db/reviews.py` writes them with it. They went with the review rather than the game because `ingest` skips a stored game, so `rlcoach reviews --redo` fills them in for games already loaded, without a reload. A game the review doesn't support, the Hoops game, has none, as it has no kickoffs.
- **What.** Every car's events, as the events give them, each on the game clock:
  - A touch: its player and team, where the car was, and the ball's speed.
  - A 50/50: both players, the team that won it (touched last, scramble included), and where it was, midway between the two cars at their touches. Phase 3 had dropped that midpoint from the event because nothing read it. It's back.
  - A demo: the victim, the attacker when the game says, and where the victim's car was. The demo detector already looked that up to spot repeats, and now keeps it.
  - One thing the events didn't have: whether each 50/50 player was their team's last back, meaning its car nearest its own goal, of those not demolished. That's how the goal review judges the last player back, and both now use one function.
- **Size.** 41 games hold 6,360 touches, 741 50/50s and 144 demos, about 155, 18 and 3.5 a game. The database grows from 0.9 MB to 2.9 MB. Redoing all 42 reviews took 28 s.
- Positions are in uu, with blue defending −y and orange +y. The table docstrings in `db/models.py` say how to tell a team's own half.

Checked on a copy of the real database:

- After `rlcoach reviews --redo`, every column of every existing table (`replays`, `players`, `player_game_stats`, `game_reviews`, `review_mistakes`, `review_goals`, `review_kickoffs`, `review_kickoff_cars`, `review_grades` and `benchmarks`) is unchanged. A second redo stores the same events again.
- The stored demos give every player's demos inflicted and taken in all 230 of their games. Each of the 13 "lost a 50/50 on low boost" flags has exactly one stored 50/50 of yours that the other team won, within 0.5 s after it.
- Every check in `AGENTS.md` passes.

### The first question it answered

"Do you lose more 50/50s in your own half when you're last back, and is that getting better?" This query lists your 50/50s, whether you lost, whether it was in your own half and whether you were last back:

```sql
select r.play_date, r.playlist,
  c.winner_team != r.my_team as lost,
  case r.my_team when 'ORANGE' then c.y else -c.y end > 0 as own_half,
  case when c.first_player = r.my_player_id then c.first_last_back
       else c.second_last_back end as last_back
from review_challenges c
join replays r using (replay_id)
where r.my_player_id in (c.first_player, c.second_player)
  and r.play_date >= '2026-01-01'
  -- Leave out kickoffs: the review skips 3 s after a kickoff's first touch
  and not exists (
    select 1 from review_kickoffs k
    where k.replay_id = c.replay_id
      and c.t >= k.t and c.t < k.t + coalesce(k.time_to_first_touch, 0) + 3.0)
```

It leaves out the three games from before 2026 and the 93 50/50s at kickoffs, which sit on the halfway line. That leaves 172 in open play over 38 games:

| Your 50/50s | Lost |
| --- | --- |
| In your half, last back | 9 of 18 (50%) |
| In your half, a teammate further back | 30 of 58 (52%) |
| In their half, last back | 8 of 9 (89%) |
| In their half, a teammate further back | 43 of 87 (49%) |
| All | 90 of 172 (52%) |

So no. In your own half you lose them at your usual rate, last back or not. Whether that's getting better can't be told yet: you had 2 to 6 of them a day over five days. One cell stands out, though the question didn't ask about it: going in as last back in their half, you lost 8 of 9. They came from six games, three from one, eight in Doubles, and five were more than 20 m past halfway. Nine is few, and the cell was picked after looking, so it's one to watch rather than a finding. "Lost" here is the event's, the other team touched last. The review's low-boost flag also asks that the ball then head for your goal.

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

### What changed on purpose (2026-11-09)

After the rewrite you asked for four changes. Each changes stored data, so the live database needs every game loaded again.

- **Player ids.** Every PlayStation, Xbox and Switch player was stored as `steam:<id>`, and one whose header row had no `PlayerID` as `onlineplatform_dingo:<id>`, so one Xbox player could have two ids. Each player now has one account under their own platform: `steam`, `epic`, `psn`, `xbox` or `switch`. 134 of the 180 players' ids change. Your one teammate tag, on LlamaTaboot8416, is on `steam:2533274833789272`, which becomes `xbox:2533274833789272`, so the reload has to carry it over.
- **Team size** is the header's `TeamSize`, where it was the bigger team's count of rows, which leave out leavers. A 3v3 that both teams finished a player short read as a 2v2. The two agree on all 42 games.
- **Touches are the game's own.** The parser hands over each player's touch count (`BallTouches`), which says who touched the ball and how often but rises up to a second late, and the ball's `HitTeamNum`, the team that touched it last, sent on the frame of the touch. `events/touches.py` places each counted touch with the ball (see [docs/parser.md](parser.md)). The 200 uu rule and the review's own contacts are gone: the review's contacts are the touches, and its last-touch team is the ball's. Against the ball's record, a touch by that team lands within 0.1 s of 98.9% of its changes of team, where the old contacts managed 90.4%. The touches' last-touch team matches the ball's on 97.0% of frames, against 90.1%, and they match the game's count of each player's touches, which the old contacts missed by 5.8 a player a game. Three of the 42 games are from before the count and get touches from the kicks alone, as the review did, with the ball's team in place of the 200 uu hint.
- **50/50 scrambles.** A third touch straight after a 50/50 made it nobody's. Now a quick run of touches is one scramble, won by the team that touched last.

What that changed, reloading all 42 games on `main` and on the new code, with `main`'s ids translated: `replays`, `player_game_stats`, `review_kickoffs` and `review_kickoff_cars` are the same, and `players` differs only in the platform and the teammate tag. In the reviews:

| | `main` | Now |
| --- | --- | --- |
| Flagged moments | 149 | 150 |
| Lost 50/50s on low boost | 12 | 13 |
| Double commits | 15 | 13 |
| Clears given back | 33 | 34 |
| Missed clears | 6 | 7 |
| Your touch turned it in | 3 | 4 |
| Last back and upfield | 9 | 8 |
| Clears counted | 205 | 222 |
| Goals put on you | 35 | 36 |

Every changed call checked by hand against the game's count and the ball's team agrees with the new code. Of the 50/50s on low boost only `main` flagged, in 3 you never touched the ball, in 2 the ball shows your team touched last, and 1 is from a game before the count. Each one only the new code flags in a game with the count shows you touching and an opponent last on the ball. Three goal reviews had a teammate turning the ball in, or you getting a touch on it, where the count shows they never touched it. A clear `main` said went straight to Incursion2169 in E561 had a touch by your teammate Jeyker09 in between, which the old contacts missed.

Reloading all 42 games took 37.7 s. The suite, the Rust tests and every check in `AGENTS.md` pass.

## The dashboard (2026-11-09)

The dashboard was redesigned in this fork but never went through a phase, so 1,020 of the 4,616 lines in `gui/src/` were still his. Unlike the other areas, they were real code: the API client, the skeleton, pagination, card and empty-state components, the entry and the routes, and the queries, filters, paging and saves on the Games, Players, player, game, Trends, Compare and Benchmarks pages. Rewritten from what each part does, its tests and the API in `types/api.ts`, with nothing you see changed:

- **The client** is one axios instance and a typed `get` per endpoint. The parameters nothing sent (`date_from`, `date_to`) and the default export are gone.
- **Lists.** Games and Players each kept their own copy of the same card: the error, ten rows of placeholders, the empty message, the table and Previous and Next. `PagedList` holds it once, and `Pagination` works from the offset and total.
- **Smaller pieces.** `BackLink` is the detail pages' link back, `LoadingCards` the two placeholder cards a whole page waits on, and `useTagPlayer` the tag and notes saves that Players and the player page share.
- **Gone:** the pages barrel, the inherited `chart-data` test (its date and label tests moved to `data-transforms.test.ts`), the empty states' unused `action` and defaults, and two CSS rules Tailwind's reset and the layout already cover: the body's margin and the `#root` height.
- **New tests** for the client's requests, the paging, the components, and the Games, Players and player pages, beside the contract tests, which pass unchanged.

What blame still gives him, 492 lines, is blank lines, closing tags, `return (`, `<thead>` and `<tbody>`, imports, the API's field and type names, the routes in `App.tsx`, the CSS declarations that have no other spelling, and two query keys the contract tests and the player saves depend on.

What behaves differently, none of it on screen:

- The Players filter's options are `tagged` and `untagged` where they were `true` and `false`. The request is the same.
- The back link's chevron sets its stroke on the `<svg>` rather than the `<path>`. It computes the same stroke, caps and box.
- The Players list sends `sort` before `limit` and `offset` in the query string.

Checked:

- The markup of 51 page states (loading, error, empty, one page and several, with and without a median, benchmarks or patterns), rendered on the old code and the new, matches apart from the first two differences above. The built CSS differs only by the two removed rules.
- Against the live dashboard at http://localhost:8000, at 1280 by 900, every page and every step of the Games and Players pagers and filters and the Trends, Compare and Benchmarks pickers gave the same DOM and the same requests, apart from the three differences above. Every element on all eight pages had the same position and size at 1280 by 900 and at phone width.
- Tagging, untagging, saving and cancelling notes, toggling the tag with the notes open (which closes them, as before) and grading a call behaved the same on the old and the new build, against a scratch API on a copy of your database.
- Every check in `AGENTS.md` passes.

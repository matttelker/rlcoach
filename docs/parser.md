# The parser

The parser reads a `.replay` file with [boxcars](https://github.com/nickbabcock/boxcars) and hands Python two things: the header and the network frames. It's Rust, built as the `rlreplay_rust` module (see [AGENTS.md](../AGENTS.md#building-the-parser)), and `src/rlcoach/parser/` is its Python side. `normalize.py` turns the frames into the `Frame`s that events, stats and the review read.

| | Where |
| --- | --- |
| Module functions, and frames as Python values | `parsers/rlreplay_rust/src/lib.rs` |
| The walk through the frames | `parsers/rlreplay_rust/src/game.rs` |
| Which player each car is | `parsers/rlreplay_rust/src/roster.rs` |
| Boost pad pickups | `parsers/rlreplay_rust/src/pads.rs` |
| The header as a `Header` | `src/rlcoach/parser/header.py` |
| The types normalize builds | `src/rlcoach/parser/types.py` |

A replay the parser can't read raises: `OSError` for a file it can't open, `ValueError` for a header or network data boxcars can't decode. Either way the game doesn't load, and the load says why.

## The header

`read_header` gives the match type (`Online`, `Private`, `Tournament`, `Offline` and so on), the arena, the scores, when the match started, who recorded it, its goals, and a row for each player in `PlayerStats`: name, team, scoreboard and accounts.

- `PlayerStats` lists the players who finished, so leavers have no row. The team size is the header's `TeamSize`, so a 3v3 that both teams finished a player short is still a 3v3. Only a header without it counts the bigger team's rows.
- A player's account is filed under their platform, from the row's `Platform`: `steam`, `epic`, `psn`, `xbox` (`OnlinePlatform_Dingo`) or `switch` (`OnlinePlatform_NNX`), the names the config takes. An Epic account is `PlayerID.EpicAccountId`. Every other platform's is a number, `PlayerID.Uid`, which `OnlineID` repeats, so a row without `PlayerID` still has it. Bots, and Epic rows without `PlayerID`, have no account and go by their name.
- `modes.playlist_of` turns the match type, team size and arena into a playlist.

## The frames

`read_frames` gives one dict per network frame, in order. `read_frames`' docstring has the fields. In short: the time, the ball and the team that touched it last, each player's car and whether it's jumping or flipping, and the frame's pickups, flips, touches, first touches and demolitions.

### Players are header rows

Every car is named by a row number: its player's row in `PlayerStats`, or a number past the rows for someone the header leaves out. Normalize turns a row into the player's id.

- A car points at its player's PRI, the actor holding their replicated info, and the PRI sends the player's name. A name only one row has gives the PRI that row, and its car.
- A row whose name no PRI ever sends (a renamed player, a bot) is free: the first car of that team without a row takes it. Every other row waits for its own PRI.
- A PRI with no row takes a free row of its team, or failing that a number past the rows, and keeps it for its later cars.
- A demolished car stays about 5 s, and its replacement comes after 3. The wreck keeps reporting as its player until the new car takes the row, but can't take a row of its own.
- A car with no team yet goes by the half of the field it's on.

### What a car carries

Position, velocity, angular velocity in radians a second, rotation as a quaternion, boost from 0 to 100, whether it's demolished, and whether it's jumping, double jumping or flipping. A car is listed once it has sent its position, its boost or its team. Until then it isn't on the field. Before it sends its boost it holds 33, the kickoff amount.

The jump, double jump and dodge components each send `ReplicatedActive`, a byte that goes up by one when the car starts using it and again when it stops, so an odd byte is in use. A component points at its car through `CarComponent_TA:Vehicle`. On your 42 games a jump lasts a median 0.11 s, a double jump 0.11 s and a flip 0.66 s, and 95% of flips start within two frames of a `DodgeTorque`. A few states stay on for seconds, up to 11 s, so read when one starts, not that it's on.

### Pickups

Pads never send where they are, only `NewReplicatedPickupData`: the car that took the pad and a counter that rises by 2 per pickup and reads 255 once the pad is back.

- A pad is placed by the first car seen taking it, at the nearest of the spots Python passes in (`field_constants.BOOST_PADS`) within 450 uu. A pickup before the pad is placed waits, and keeps its own time.
- A replay checkpoint, about every 10 s, re-creates every pad actor, often under a new id, and re-sends each pad's last state, sometimes an older one, naming a dead (`-1`) or unrelated car. So a pad is known by its level object name, a re-sent state is no pickup, and a counter that didn't advance counts only if the car is at the pad.
- A goal reset sets the counter to 255 without advancing it, so the next pickup can repeat the last value. The car being at the pad is what counts it then.
- Hoops and Dropshot have pads of their own, which the table doesn't hold. `modes.Mode.soccar_pads` says so, and their replays get no pickups, so boost pickups come from the cars' boost rises.

### Flips, touches, first touches, the game's counts and demolitions

- A flip is a `DodgeTorque`: the torque in the car's own axes, which points the way the stick did.
- Touches are the game's own count of each player's touches, `TAGame.PRI_TA:BallTouches`: the frame it rose on, and by how much. It only grows and is often sent again unchanged, so only a rise counts, and it can rise by several at once. It reaches the replay up to a second after the touch, a median 0.44 s on your games, so the frame it rose on isn't the touch's. Replays from before it (net version 11 and older) have none.
- The ball sends `HitTeamNum`, the team that touched it last, on the very frame of a touch that changes it. It's None until a kickoff's first touch, since each kickoff has a new ball.
- `events/touches.py` places the counted touches with the ball. A change of the ball's team is a touch on that frame by that team's player whose count rose next. Every other touch goes at a kick, a frame where the ball's speed changed by more than gravity explains with the player's car within 350 uu, or failing that where the car came nearest. Kicks where the ball names the other team, bounces off a surface and kicks another player took come last. On your 42 games a touch by that team lands within 0.1 s of 98.9% of the ball's changes of team. A replay without the count gets touches from the kicks alone.
- A first touch is the game's own count, `MatchFirstTouches`, rising by one. It replicates up to a second after the touch, so its time isn't the contact's. The game keeps re-sending the total, so only a rise counts. Replays before net version 12 have no counter, and `events/kickoffs.py` then finds the first touch from the frames.
- The game's own counts that the header's scoreboard leaves out, `MatchEpicSaves`, `MatchClears`, `MatchCenters` and `MatchAerialHits`, come as `(row, name, rise)` when one rises, named `epic_save`, `clear`, `center` and `aerial_hit`. Like the touch count they only grow, are sent again unchanged, and rise after the touch: aerial hits a median 0.4 s after, clears 1.0 s (up to 3.3 s) and centers 1.7 s. Summed per player they are the stats of the same names. Three of your 42 games, from 2022 and October 2024, carry none of them, so those games store no value. They match Ballchasing exactly on the 18 players of the three exported games (`tests/analysis/test_ballchasing_parity.py`). The game's clear is a touch from deep in front of your goal (a median 40 m from halfway), narrower than the review's clears from your half: 75 of yours on the 42 games against the review's 229.
- A demolition names the car demolished and the one that did it, if any.

## What it leaves out

Normalize and the code after it read only the fields above. The parser doesn't read the cars' inputs, the boost and flip-car components' `ReplicatedActive`, the ball's spin, the camera settings, loadouts, the game's stat events, the replay's tick marks, `bBallHasBeenHit`, or the game's shot and save counters, `MatchShots` and `MatchSaves`, since the header's scoreboard has those. Reading one means adding it to `game.rs`, the frame dict in `lib.rs`, and normalize.

Measured on your 42 games (2026-11-09), for when something wants them:

- The boost component's `ReplicatedActive` is the boost being held. Of 21,760 drops in a tank, 18 came with it off, and a burst's length at 33.3 a second predicts what it spent (median 0.99). Summed over a game it gives boost used within 4% of Ballchasing's. Ballchasing's boost used while supersonic can't be matched: it charges each drop to the car's speed on the frame the tank replicates, at the end of the burst, so it reads 0.45 to 3.1 times the boost held there on the three exported games.
- The shot and save counters match Ballchasing exactly on the 18 players of the three exported games, and match the header's scoreboard within 3. Saves rise a median 0.5 s after the touch, shots 0.9 s.
- `bBallHasBeenHit` first goes true on the frame `events/kickoffs.py` already takes as each kickoff's contact, on all 274 kickoffs, and is sent again many times after.

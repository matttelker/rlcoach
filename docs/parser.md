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

- `PlayerStats` lists the players who finished, so leavers have no row. The team size is the bigger team's row count.
- A player's accounts come from their unique id: `Uid` as Steam, `EpicAccountId` as Epic and `NpId` as PSN. Only when there's none is `OnlineID` filed under the platform. Consoles send their id in `Uid` too, so a PS4, Xbox or Switch player is stored as `steam:<id>`. That's inherited, and kept so ids don't change.
- `modes.playlist_of` turns the match type, team size and arena into a playlist.

## The frames

`read_frames` gives one dict per network frame, in order. `read_frames`' docstring has the fields. In short: the time, the ball, each player's car, and the frame's pickups, flips, touches, first touches and demolitions.

### Players are header rows

Every car is named by a row number: its player's row in `PlayerStats`, or a number past the rows for someone the header leaves out. Normalize turns a row into the player's id.

- A car points at its player's PRI, the actor holding their replicated info, and the PRI sends the player's name. A name only one row has gives the PRI that row, and its car.
- A row whose name no PRI ever sends (a renamed player, a bot) is free: the first car of that team without a row takes it. Every other row waits for its own PRI.
- A PRI with no row takes a free row of its team, or failing that a number past the rows, and keeps it for its later cars.
- A demolished car stays about 5 s, and its replacement comes after 3. The wreck keeps reporting as its player until the new car takes the row, but can't take a row of its own.
- A car with no team yet goes by the half of the field it's on.

### What a car carries

Position, velocity, angular velocity in radians a second, rotation as a quaternion, boost from 0 to 100, and whether it's demolished. A car is listed once it has sent its position, its boost or its team. Until then it isn't on the field. Before it sends its boost it holds 33, the kickoff amount.

### Pickups

Pads never send where they are, only `NewReplicatedPickupData`: the car that took the pad and a counter that rises by 2 per pickup and reads 255 once the pad is back.

- A pad is placed by the first car seen taking it, at the nearest of the spots Python passes in (`field_constants.BOOST_PADS`) within 450 uu. A pickup before the pad is placed waits, and keeps its own time.
- A replay checkpoint, about every 10 s, re-creates every pad actor, often under a new id, and re-sends each pad's last state, sometimes an older one, naming a dead (`-1`) or unrelated car. So a pad is known by its level object name, a re-sent state is no pickup, and a counter that didn't advance counts only if the car is at the pad.
- A goal reset sets the counter to 255 without advancing it, so the next pickup can repeat the last value. The car being at the pad is what counts it then.
- Hoops and Dropshot have pads of their own, which the table doesn't hold. `modes.Mode.soccar_pads` says so, and their replays get no pickups, so boost pickups come from the cars' boost rises.

### Flips, touches, first touches and demolitions

- A flip is a `DodgeTorque`: the torque in the car's own axes, which points the way the stick did.
- A touch is a car within 200 uu of the ball. A car's touches within 0.2 s of each other are one, and within 0.4 s if it hasn't moved 120 uu.
- A first touch is the game's own count, `MatchFirstTouches`, rising by one. It replicates up to a second after the touch, so its time isn't the contact's. The game keeps re-sending the total, so only a rise counts. Replays before net version 12 have no counter, and `events/kickoffs.py` then finds the first touch from the frames.
- A demolition names the car demolished and the one that did it, if any.

## What it leaves out

Normalize and the code after it read only the fields above. The parser doesn't read the cars' inputs, jumps, boosting, the ball's spin, the camera settings, loadouts, the game's own stat events or the replay's tick marks. Reading one means adding it to `game.rs`, the frame dict in `lib.rs`, and normalize.

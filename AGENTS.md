# rlcoach

A local Rocket League replay coach for one player, on Windows. There are no accounts and no hosting, and analysis never touches the network. Replays go in; a list of mistakes and personal training targets come out, on a browser dashboard called Soccar Doctor.

The only users are the player, through the dashboard, and Claude, through chats that read the local API and database. Keep what serves those and the coaching, and delete the rest rather than maintain it. [docs/rewrite-plan.md](docs/rewrite-plan.md) tracks replacing the code inherited from the original project.

## How it fits together

```text
.replay -> Rust parser -> normalize -> events -> analysis -> SQLite -> API -> dashboard
```

| Area | Where |
| --- | --- |
| Rust parser (pyo3, boxcars) | `parsers/rlreplay_rust/` |
| Python side of the parser | `src/rlcoach/parser/` |
| Checking a replay file before parsing it | `src/rlcoach/replay_file.py` |
| One replay read once: header, frames and events | `src/rlcoach/game.py` |
| Normalize and events | `src/rlcoach/normalize.py`, `src/rlcoach/events/` |
| Analysis modules | `src/rlcoach/analysis/` |
| One game's stats, as the database stores them | `src/rlcoach/report.py` |
| Loading a replay into the database | `src/rlcoach/pipeline.py`, `src/rlcoach/db/games.py` |
| Game modes and playlists | `src/rlcoach/modes.py` |
| Mistake detector | `src/rlcoach/analysis/mistakes.py` |
| Situations: how often each judged choice came up, for every car, and whether a goal followed. The evidence each rule stands on | `src/rlcoach/analysis/situations.py` |
| Stored reviews, training targets and highlights | `src/rlcoach/db/reviews.py`, `src/rlcoach/coaching.py` |
| Kickoff coaching: how you play kickoffs and the next step to learn | `src/rlcoach/kickoff_coaching.py`, `src/rlcoach/events/kickoffs.py` |
| Your right or wrong grades on the review's calls | `src/rlcoach/db/grades.py` |
| Each game's touches, 50/50s and demos, every car's, kept with its review for questions across games | `src/rlcoach/db/models.py`, `src/rlcoach/db/reviews.py` |
| Your stats against your wins, losses and a rank | `src/rlcoach/compare.py` |
| Database (SQLite, one file) | `src/rlcoach/db/` |
| Local API (FastAPI) | `src/rlcoach/api/` |
| Dashboard (React, Vite) | `gui/` |
| Bundled benchmarks | `src/rlcoach/data/` |

Your config is `~/.rlcoach/config.toml`. Your database is `~/.rlcoach/data/rlcoach.db`.

## Setup

Needs [uv](https://docs.astral.sh/uv/), Node 24 and Rust.

```bash
uv sync --inexact --python 3.14
```

```bash
npm --prefix gui ci
```

Always pass `--inexact`. Without it `uv sync` removes the Rust parser, which isn't a listed dependency.

## Running

Run Python through `uv run`, never the system Python.

One process serves everything at http://localhost:8000: the built dashboard at `/`, the API under `/api`, and a watcher that loads new replays. It runs in the background and starts when you sign in to Windows, so nothing depends on a terminal staying open.

```bash
npm --prefix gui run build
```

```bash
uv run rlcoach autostart on
```

`rlcoach start` and `rlcoach stop` start and stop it by hand, and `rlcoach autostart status` says whether it's running. Output goes to `~/.rlcoach/serve.log`. It runs the code and the built dashboard it started with, so after a change, rebuild the dashboard if it changed, then stop and start it.

To run it in a terminal instead, stop the background one and use `uv run rlcoach serve`. For dashboard work, `npm --prefix gui run dev` serves a live copy at http://localhost:5173 that sends `/api` to port 8000.

```bash
uv run rlcoach mistakes path/to/game.replay --player YourName
```

A replay file can land about 30 seconds after a match ends.

## Building the parser

This PC has the Rust GNU toolchain, so `maturin develop` fails at link time. Use cargo and copy the result. Run `uv run rlcoach stop` first, because the running server locks the `.pyd`.

```bash
export PATH="$HOME/.cargo/bin:$HOME/.rustup/toolchains/stable-x86_64-pc-windows-gnu/lib/rustlib/x86_64-pc-windows-gnu/bin/self-contained:$PATH"
export PYO3_PYTHON='D:\git\rlcoach\.venv\Scripts\python.exe' PYO3_USE_RAW_DYLIB=0
cargo build -p rlreplay_rust --release
cp target/release/rlreplay_rust.dll .venv/Lib/site-packages/rlreplay_rust/rlreplay_rust.pyd
```

`cargo test` also needs the folder holding `python3.dll` on `PATH`. On Linux, `maturin develop --uv --release -m parsers/rlreplay_rust/Cargo.toml` works.

## Checks

Run all of these before a commit. CI runs the same ones.

```bash
uv run ruff check src tests
```

```bash
uv run black --check src tests
```

```bash
uv run pytest -q
```

```bash
cargo fmt --all --check
```

```bash
cargo test -p rlreplay_rust
```

```bash
npm --prefix gui run lint
```

```bash
npm --prefix gui test
```

```bash
npm --prefix gui run build
```

Point `HOME` and `USERPROFILE` at a scratch folder when running pytest, so nothing touches your real `~/.rlcoach`. From Git Bash that leaves a stray `black/` cache folder in the repo; delete it.

The tests that read real replays use your own, which stay out of git. Point `RLCOACH_TEST_REPLAYS` at the folder that holds them, `D:\rlcoach-test-replays` on this PC. Without it those tests skip, as they do in CI. [tests/fixtures/real_replays.py](tests/fixtures/real_replays.py) lists the games and how the files are named.

## Rules

- Check parser, analysis and report changes against your real replays, not only synthetic data. Replay coaching numbers are easy to get plausibly wrong.
- For any stat the dashboard shows, run `tests/analysis/test_ballchasing_parity.py`, which compares three of your games with Ballchasing's own CSVs. Keep its bounds tight.
- Mirror new source modules with tests under `tests/`. Build synthetic data with `tests/fixtures/builders.py`.
- `analysis/__init__.py` computes each player's stats, exactly the columns in `STAT_COLUMNS` in `db/games.py`. Add a stat only when the dashboard or the coaching will read it.
- Changing database models or analysis means reloading replays, because `~/.rlcoach` holds results from the old code. There are no migrations. New tables are the exception: `init_db` creates them in an existing database.
- After changing the mistake detector or an event detector (touches, 50/50s, demos or kickoffs), run `uv run rlcoach reviews --redo` so stored reviews and events match the new rules. Each game's kickoffs, touches, 50/50s, demos and situations, every car's, are stored with its review.
- A coaching rule has to earn its place. Before adding or changing one, give it a situation in `analysis/situations.py` and compare how often a goal against follows the bad choice and the good one, across every player, where the ball was in the same part of the field. Keep a rule the outcomes support, and drop one they contradict. The player can't judge a call themselves, so outcomes are the check.
- Keep analysis local. Nothing in the parser or analyzers may call the network.

## Git

- There is one branch, `main`, and it tracks `origin/main` (matttelker/rlcoach). Short-lived branches merge back quickly.
- This started as a fork of treygoff24/rlcoach, which is no longer followed. Don't add it as a remote or sync with it.
- Commits are conventional: `type(scope): description`.

# rlcoach

A local Rocket League replay coach for one player, on Windows. There are no accounts and no hosting, and analysis never touches the network. Replays go in; a browser dashboard, Markdown reports and a list of mistakes come out.

## How it fits together

```text
.replay -> Rust parser -> normalize -> events -> analysis -> report -> SQLite -> API -> dashboard
```

| Area | Where |
| --- | --- |
| Rust parser (pyo3, boxcars) | `parsers/rlreplay_rust/` |
| Python adapters over the parser | `src/rlcoach/parser/` |
| Normalize and events | `src/rlcoach/normalize.py`, `src/rlcoach/events/` |
| Analysis modules | `src/rlcoach/analysis/` |
| Mistake detector | `src/rlcoach/analysis/mistakes.py` |
| Stored reviews, training targets and highlights | `src/rlcoach/db/reviews.py`, `src/rlcoach/coaching.py` |
| Your right or wrong grades on the review's calls | `src/rlcoach/db/grades.py` |
| JSON and Markdown reports | `src/rlcoach/report.py`, `src/rlcoach/report_markdown.py`, `schemas/` |
| Database (SQLite, one file) | `src/rlcoach/db/` |
| Local API (FastAPI) | `src/rlcoach/api/` |
| Dashboard (React, Vite) | `gui/` |
| Bundled benchmarks | `src/rlcoach/data/` |

Your config is `~/.rlcoach/config.toml`. Your database and reports live under `~/.rlcoach/`.

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

## Rules

- Check parser, analysis and report changes against real replays in `Replay_files/`, not only synthetic data. Replay coaching numbers are easy to get plausibly wrong.
- For any stat in a report, run `tests/analysis/test_ballchasing_parity.py`, which compares one real replay with Ballchasing's own CSV. Keep its bounds tight.
- Mirror new source modules with tests under `tests/`. Build synthetic data with `tests/fixtures/builders.py`.
- Analysis modules return `{"per_player": {...}, "per_team": {...}}`. Expensive analyzers are cached in `analysis/__init__.py`.
- When the report changes, update `schemas/replay_report.schema.json`, the goldens in `tests/goldens/` and `docs/report-mapping.md` in the same change.
- Changing database models or analysis means reloading replays, because `~/.rlcoach` holds results from the old code. There are no migrations. New tables are the exception: `init_db` creates them in an existing database.
- After changing the mistake detector, run `uv run rlcoach reviews --redo` so stored reviews match the new rules.
- Keep analysis local. Nothing in the parser or analyzers may call the network.

## Git

- There is one branch, `main`, and it tracks `origin/main` (matttelker/rlcoach). Short-lived branches merge back quickly.
- This started as a fork of treygoff24/rlcoach, which is no longer followed. Don't add it as a remote or sync with it.
- Commits are conventional: `type(scope): description`.

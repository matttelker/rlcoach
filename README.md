# rlcoach

A local Rocket League replay coach for one player. It reads your `.replay` files, finds the mistakes worth fixing and turns them into training targets on a dashboard called Soccar Doctor. Everything runs on your own PC, with no accounts and no network calls from the analysis.

## Setup

You need [uv](https://docs.astral.sh/uv/), Node 24 and Rust.

```bash
uv sync --inexact --python 3.14
```

```bash
npm --prefix gui ci
```

Build the Rust parser next. [AGENTS.md](AGENTS.md#building-the-parser) has the commands. rlcoach can't read replays without it.

Create a config:

```bash
uv run rlcoach config --init
```

Then edit `~/.rlcoach/config.toml` and set your `display_names` or `platform_ids`, your `watch_folder` (where Rocket League saves replays) and your `primary_playlist`.

## Use it

Build the dashboard, then set rlcoach to run in the background and start whenever you sign in to Windows:

```bash
npm --prefix gui run build
```

```bash
uv run rlcoach autostart on
```

Open http://localhost:8000. It loads your existing replays and every new one as it lands, reviews your mistakes in each, and builds your training targets on the Coach page. `uv run rlcoach stop` and `uv run rlcoach start` stop and start it, `uv run rlcoach autostart off` stops it starting at sign-in, and its output goes to `~/.rlcoach/serve.log`.

To run it in a terminal instead, use `uv run rlcoach serve` and press Ctrl+C to stop.

Load a replay from outside the watch folder:

```bash
uv run rlcoach ingest path/to/game.replay
```

List one player's mistakes in a game and what to do instead:

```bash
uv run rlcoach mistakes path/to/game.replay --player YourName
```

Review games that don't have a review yet, or redo every review after the rules change:

```bash
uv run rlcoach reviews
```

```bash
uv run rlcoach reviews --redo
```

## Benchmarks

Doubles and Standard each have a bundled file of benchmarks measured by ballchasing.com, one row per stat for every rank from G1 (Gold I) to C3, plus GC. Ballchasing groups every Grand Champion tier together, so GC combines GC1 through SSL. The server reloads them every time it starts. The Coach, Benchmarks, Compare and Trends pages compare you with `target_rank` in your config, P1 unless you set it, and Benchmarks and Compare let you pick another rank.

## Docs

- [AGENTS.md](AGENTS.md): how the code is laid out, how to build and test it, and the working rules.
- [docs/rewrite-plan.md](docs/rewrite-plan.md): what's left of the original code and the plan to replace it.
- [gui/README.md](gui/README.md): the dashboard.
- [docs/parser.md](docs/parser.md): what the parser reads from a replay, and how it tells the players apart.

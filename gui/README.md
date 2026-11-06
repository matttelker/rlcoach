# RLCoach local dashboard

A React dashboard for your own replays. It reads the local API, which reads your SQLite database.

## Setup

Run these from the repository root. Create a config, then set your `display_names` or
`platform_ids`, your `watch_folder` (the folder Rocket League saves replays to), and your
`primary_playlist`, which the dashboard opens on:

```bash
uv run rlcoach config --init
```

Install the dashboard's dependencies:

```bash
npm --prefix gui ci
```

## Run

Each of these runs until you stop it, so give each its own terminal.

Load your replays, and keep picking up new ones:

```bash
uv run rlcoach ingest --watch --process-existing
```

Start the API on port 8000:

```bash
uv run rlcoach serve
```

Start the dashboard at http://localhost:5173:

```bash
npm --prefix gui run dev
```

## Pages

- **Coach** is the home page. It shows your latest session, up to three training targets, your
  mistakes in five categories (last back, rotation, clearing, goalkeeping and boost), and
  highlights such as game winners, games with no goals on you, and habits you've stopped.
  Targets rank categories by the goals they cost you, then by how often they come up.
- **Games** lists every game. A game's page puts your flagged moments and every goal on a
  timeline of the game clock, groups the moments by category, and explains each goal against.
- **Stats** holds the trends, the rank comparison and the benchmarks.
- **Players** lists the people you've played with and against.

Ingest reviews your mistakes in every new game. Games loaded before reviews existed have none,
so fill them in once:

```bash
uv run rlcoach reviews
```

After a change to the mistake detector, review every game again with `--redo`.

## Benchmarks

On startup the API loads the bundled benchmarks for any playlist that has none. Doubles and
Standard each have their own file, with C2, C3 and GC1 rows measured by ballchasing.com across all
seasons. Ballchasing groups every Grand Champion tier together, so the GC1 rows combine GC1 through
SSL. Add other ranks or playlists with `uv run rlcoach benchmarks import <file>`.

## Checks

```bash
npm --prefix gui test
```

```bash
npm --prefix gui run lint
```

```bash
npm --prefix gui run build
```

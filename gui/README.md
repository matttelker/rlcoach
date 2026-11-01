# RLCoach local dashboard

A React dashboard for your own replays. It reads the local API and SQLite database, with no
accounts, Postgres or Redis.

## Setup

Run these from the repository root. Create a config, then set your `display_names` or
`platform_ids`, your `watch_folder` (the folder Rocket League saves replays to), and your
`primary_playlist`, which the dashboard opens on:

```bash
rlcoach config --init
```

Install the dashboard's dependencies:

```bash
npm --prefix gui ci
```

## Run

Each of these runs until you stop it, so give each its own terminal.

Load your replays, and keep picking up new ones:

```bash
rlcoach ingest --watch --process-existing
```

Start the API on port 8000:

```bash
rlcoach serve
```

Start the dashboard at http://localhost:5173:

```bash
npm --prefix gui run dev
```

## Benchmarks

On startup the API loads the bundled benchmarks for any playlist that has none. Doubles and
Standard each have their own file, with C2, C3 and GC1 rows measured by ballchasing.com across all
seasons. Ballchasing groups every Grand Champion tier together, so the GC1 rows combine GC1 through
SSL. Add other ranks or playlists with `rlcoach benchmarks import <file>`.

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

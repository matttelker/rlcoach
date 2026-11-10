# RLCoach local dashboard

A React dashboard for your own replays. `rlcoach serve` serves the built copy at
http://localhost:8000, with the API it reads under `/api`.

## Setup

Run these from the repository root. Create a config, then set your `display_names` or
`platform_ids`, your `watch_folder` (the folder Rocket League saves replays to), and your
`primary_playlist`, which the Stats pages open on:

```bash
uv run rlcoach config --init
```

Install the dashboard's dependencies:

```bash
npm --prefix gui ci
```

## Run

Build the dashboard, then run rlcoach in the background and start it whenever you sign in to
Windows. It loads new replays as they land, and the dashboard is at http://localhost:8000.

```bash
npm --prefix gui run build
```

```bash
uv run rlcoach autostart on
```

The server keeps the build it started with. After changing the dashboard, build it again and
restart the server:

```bash
uv run rlcoach stop
```

```bash
uv run rlcoach start
```

While working on the dashboard, `npm --prefix gui run dev` serves a live copy at
http://localhost:5173 that reloads on every edit and sends `/api` to the server on port 8000.

## Pages

- **Coach** is the home page. It shows your latest session, up to three training targets, your
  mistakes in five categories (last back, rotation, clearing, goalkeeping and boost), and
  highlights such as game winners, games with no goals on you, and habits you've stopped.
  Targets rank categories by the goals they cost you, then by how often they come up. It opens
  on the playlist of your latest game. It checks for new games when you come back to it, then
  every 30 seconds while it's on screen, so it keeps up while you play.
- **Games** lists every game. A game's page puts your flagged moments and every goal on a
  timeline of the game clock, groups the moments by category, and explains each goal against.
  A goal is on you when you had a chance to stop it in its last seconds, or when an earlier
  moment of yours led to it and the opponents kept the ball until it went in. Otherwise it
  reads "No mistake found", which means none of the rules matched, not that the play was clean.
  Mark each flagged moment and each goal verdict right or wrong as you rewatch the replay. Once
  you've graded some, the Coach page tallies them per rule, so you can see which rules to trust
  and which to fix. Grades outlast `rlcoach reviews --redo`, but a grade only counts while the
  review still makes the call you graded.
- **Stats** holds the trends, and the rank comparison with your wins against your losses.
- **Players** lists the people you've played with and against.

Ingest reviews your mistakes in every new game. Games loaded before reviews existed have none,
so fill them in once:

```bash
uv run rlcoach reviews
```

After a change to the mistake detector, review every game again with `--redo`.

## Benchmarks

The server reloads the bundled benchmarks every time it starts. Doubles and Standard each have
their own file, measured by ballchasing.com across all seasons, with a row per stat for every rank
from G1 (Gold I) to C3, plus GC. Ballchasing groups every Grand Champion tier together, so GC
combines GC1 through SSL. The pages open on `target_rank` from your config, P1 unless you set it.

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

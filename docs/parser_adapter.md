# Parser Adapter Contract

Canonical path: `docs/parser_adapter.md`.

This document defines the runtime contract between the parser bridge, normalization layer, event detectors, and report output.

## Build And Dev Workflow

To build and test the parser, see [AGENTS.md](../AGENTS.md#building-the-parser).

## Current Backend Posture

- Default backend policy is diagnostics-first with explicit degradation.
- `null` adapter remains a header-only fallback.
- `rust` adapter remains the primary network-data backend (boxcars + pyo3).
- Network failures must produce structured diagnostics, never silent fallback.
- JSON, Markdown, and corpus-health surfaces report parser scorecard coverage as current behavior.
- JSON and Markdown reports surface parser diagnostics plus scorecard coverage for the selected backend.
- Current corpus-health snapshot (2026-04-29): 202 replay files, 100% header success,
  99.50% usable network parses, 31,807 parser-authored event carriers, and one known
  degraded replay classified as `boxcars_unknown_attribute_network_error`.

## Header Contract

The parser header contract includes:

- `playlist_id`, `map_name`, `team_size`
- `engine_build`, `match_guid`, `overtime`, `mutators`
- `team0_score`, `team1_score`, `match_length`
- `players`, `goals`, `highlights`
- `quality_warnings`

When fields are unavailable, the adapter degrades with explicit warnings and leaves optional values unset.

## Network Frame Contract

Each frame should carry:

- `timestamp`
- `ball`
- `players`
- `boost_pad_events`
- `parser_touch_events`
- `parser_demo_events`
- `parser_tickmarks`
- `parser_kickoff_markers`
- `parser_first_touch_events`

`boost_pad_events` are preferred for boost pickups only when they account for at least
half of what the boost-delta detector finds. Many replays replicate only a fraction of
their pad pickups, and a sparse stream would otherwise undercount boost tenfold.

Positions are normalized through field-coordinate bounds. Velocity and angular-velocity
vectors are not position-clamped; downstream mechanics depend on preserving magnitude,
negative components, and sign flips.

Player component-state flags are tri-state semantically:

- `True`: parser explicitly observed active state
- `False`: parser explicitly observed inactive state
- `None`: parser could not provide authority for that field

## Boost Pad Events

`boost_pad_events` carries one `COLLECTED` event per real pickup, read from the pads'
replicated pickup state, and a `RESPAWNED` event when a pad returns unclaimed. A car
on a pad as it respawns collects with no `RESPAWNED` between. Totals agree with the
game's own `TAGame.PRI_TA:BoostPickups` counter to within one pickup per replay.

- Pads are dormant until first collected, and a replay checkpoint re-spawns every pad
  actor about every 10s, often under a new actor id, so pad state is keyed by level
  object name, not actor id.
- Checkpoints re-send each pad's last state, sometimes an older one, naming a dead
  (`-1`) or unrelated car. These are not pickups.
- `NewReplicatedPickupData` counts up by 2 per collection and reads 255 once the pad
  is back. A goal reset goes to 255 without advancing it, so the next collection can
  repeat the previous value. A repeated value counts only if the car is at the pad.
- Pads never replicate a position, so each is identified from the instigating car at
  pickup, using the tolerances in `schemas/boost_pad_tables.json`.
- Hoops, Dropshot and Rumble have no verified pad table. Pickups there are replicated
  but emit no events, so boost detection uses boost deltas instead.
- A collection whose car has no player binding (about 0.3%) is emitted without
  `player_id` and is skipped by pickup detection.

## Parser Event Streams

The parser-facing event carriers on each frame are:

- `parser_touch_events`
- `parser_demo_events`
- `parser_tickmarks`
- `parser_kickoff_markers`
- `parser_first_touch_events`

Event detectors consume parser events first when present, then use existing inference fallbacks when absent.
Touch and demo streams are event-type authoritative: once parser-authored touch/demo
events exist for a replay, downstream detectors do not add duplicate proximity/demo
heuristics for that event type.

Contact-sensitive mechanics use the same parser-first posture. If a replay has a
parser-authored touch stream, mechanics treat no-touch frames as authoritative no-contact
frames instead of falling back to player-ball proximity. Proximity remains a fallback only
for replay parses that do not expose parser touch authority.

`parser_first_touch_events` is the game's own record of who took each kickoff's first touch,
one event each time a player's `TAGame.PRI_TA:MatchFirstTouches` counter rises. The event's
timestamp is when the rise replicated, up to about a second after the touch, so it does not
give the contact time. The game keeps resending the total, so the parser compares values and
emits only a step of one. The counter exists from net version 12 on, so older replays emit
none, and `detect_kickoffs` then estimates `first_touch_player` from frames. A rise is dropped
if its player's name has no unique header row.

Corpus-health tracks parser event/provenance coverage across these carriers:

- `parser_event_coverage` reports touch, demo, tickmark, and kickoff-marker replay/frame coverage.
- `event_provenance` reports parser-vs-inferred prevalence for touch, demo, and kickoff event surfaces where provenance is observable.
- `parser_event_totals` and `parser_event_source_counts` preserve the raw aggregate event counts.

Parser event `source` values preserve provenance. Parser-authored carriers should use `source="parser"`; inferred downstream events retain `source="inferred"` when parser authority is absent.
Timeline entries carry the same provenance in their `data.source` field for parser-backed
touch, demo, kickoff, shot, and save surfaces.

## Diagnostics And Degradation Semantics

`network_diagnostics` must preserve:

- `status`
- `error_code`
- `error_detail`
- `frames_emitted`
- `attempted_backends`

Degraded and unavailable states are valid outputs and are expected in corpus-health reporting.

`scorecard` and `scorecard_coverage` fields measure whether parser output is usable for downstream analysis; the exact fields are listed below.

## Scorecard And Corpus-Health Semantics

Reports include `quality.parser.scorecard` with:

- `usable_network_parse`
- `non_empty_player_frame_coverage`
- `player_identity_coverage`
- `network_frame_count`
- `non_empty_player_frames`
- `players_with_identity`
- `expected_players`

The corpus harness extends those per-report scorecard semantics across replay roots and also reports:

- `scorecard_coverage`
- `parser_event_totals`
- `parser_event_coverage`
- `parser_event_source_counts`
- `event_provenance`

Invalid replay roots fail explicitly with `invalid_replay_root`; valid roots with no `.replay` files fail explicitly with `no_replays_found`.

## Test And Corpus-Health Commands

Core parser-analysis validation:

```bash
PYTHONPATH=src uv run pytest \
  tests/test_rust_adapter.py \
  tests/parser/test_rust_adapter_smoke.py \
  tests/test_parser_interface.py \
  tests/test_normalize.py \
  tests/test_events.py \
  tests/test_events_calibration_synthetic.py \
  tests/test_analysis_mechanics_contract.py \
  tests/test_analysis_mechanics_advanced.py \
  tests/test_schema_validation.py \
  tests/test_schema_validation_hardening.py \
  tests/test_docs_parser_contract.py \
  tests/test_benchmarks.py -q
```

Corpus-health gate:

```bash
PYTHONPATH=src uv run python scripts/parser_corpus_health.py --roots Replay_files --json
```

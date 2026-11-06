"""Tests for training targets and highlights built from game reviews."""

from __future__ import annotations

from datetime import date

from rlcoach.coaching import (
    FlagRow,
    GoalRow,
    ReviewedGame,
    find_highlights,
    pick_targets,
    summarize_categories,
)

OCT_31 = date(2026, 10, 31)
NOV_5 = date(2026, 11, 5)


def _flag(kind, category, cost_goal=False):
    return FlagRow(kind, category, cost_goal)


def _game(n, day, flags=(), goals=(), result="WIN", score=(2, 1)):
    return ReviewedGame(
        replay_id=f"r{n}",
        play_date=day,
        result=result,
        my_score=score[0],
        opponent_score=score[1],
        map="Stadium_P",
        flags=list(flags),
        goals=list(goals),
    )


def _against(on_me):
    return GoalRow("2:00", False, False, False, False, on_me)


def _by_me(clock, winner=False, equalizer=False):
    return GoalRow(clock, True, True, winner, equalizer, None)


def _by_category(summaries):
    return {s["category"]: s for s in summaries}


def test_targets_rank_goals_cost_above_frequency():
    clears = [_flag("clear_given_back", "clearing") for _ in range(5)]
    games = [
        _game(1, OCT_31, clears),
        _game(2, OCT_31, [_flag("last_back_upfield", "last_back", cost_goal=True)]),
    ]
    targets = pick_targets(summarize_categories(games))

    assert [t["category"] for t in targets] == ["last_back", "clearing"]
    assert targets[0]["goals_cost"] == 1
    assert targets[1]["flags"] == 5


def test_categories_without_flags_are_never_targets():
    games = [_game(1, OCT_31, [_flag("double_commit", "rotation")])]
    assert [t["category"] for t in pick_targets(summarize_categories(games))] == [
        "rotation"
    ]


def test_cue_comes_from_the_kind_that_cost_the_most_goals():
    games = [
        _game(
            1,
            OCT_31,
            [
                _flag("clear_given_back", "clearing"),
                _flag("clear_given_back", "clearing"),
                _flag("missed_clear", "clearing", cost_goal=True),
            ],
        )
    ]
    clearing = _by_category(summarize_categories(games))["clearing"]
    assert clearing["top_kind"] == "missed_clear"
    assert clearing["cue"].startswith("A slow ball by your net")
    assert clearing["kinds"] == {"clear_given_back": 2, "missed_clear": 1}


def test_latest_session_rate_is_compared_with_the_games_before():
    upfield = _flag("caught_upfield", "rotation")
    games = [
        _game(1, OCT_31),
        _game(2, OCT_31),
        _game(3, OCT_31, [upfield]),
        _game(4, NOV_5, [upfield, upfield]),
    ]
    rotation = _by_category(summarize_categories(games))["rotation"]
    assert rotation["before_per_game"] == 0.33
    assert rotation["latest_per_game"] == 2.0
    assert rotation["sessions"] == [
        {"play_date": "2026-10-31", "games": 3, "flags": 1},
        {"play_date": "2026-11-05", "games": 1, "flags": 2},
    ]


def test_one_session_has_no_before_rate():
    rotation = _by_category(summarize_categories([_game(1, NOV_5)]))["rotation"]
    assert rotation["before_per_game"] is None
    assert rotation["latest_per_game"] == 0


def test_clean_streak_counts_back_from_the_newest_game():
    miss = _flag("missed_save", "goalkeeping", cost_goal=True)
    games = [_game(1, OCT_31, [miss]), _game(2, OCT_31), _game(3, NOV_5)]
    assert _by_category(summarize_categories(games))["goalkeeping"]["clean_streak"] == 2


def test_highlights_call_out_a_winner_and_a_game_with_no_goals_on_me():
    games = [
        _game(1, OCT_31, goals=[_by_me("1:00", winner=True)]),
        _game(2, NOV_5, goals=[_by_me("1:09", winner=True), _against(on_me=False)]),
    ]
    highlights = find_highlights(games, summarize_categories(games))
    kinds = [(h["kind"], h["replay_id"]) for h in highlights]

    # Only the latest session's games are called out
    assert ("winner", "r2") in kinds
    assert ("winner", "r1") not in kinds
    assert ("clean", "r2") in kinds
    winner = next(h for h in highlights if h["kind"] == "winner")
    assert winner["detail"] == "2–1 on Stadium, with 1:09 left"


def test_a_habit_that_stopped_showing_up_is_a_highlight():
    miss = _flag("missed_save", "goalkeeping", cost_goal=True)
    games = [_game(1, OCT_31, [miss]), _game(2, NOV_5), _game(3, NOV_5)]
    highlights = find_highlights(games, summarize_categories(games))
    streak = [h for h in highlights if h["kind"] == "streak"]
    assert [h["title"] for h in streak] == ["Clean on goalkeeping"]
    assert streak[0]["detail"] == "No goalkeeping mistakes in your last 2 games"


def test_a_category_that_never_came_up_is_not_a_highlight():
    games = [_game(1, OCT_31), _game(2, NOV_5), _game(3, NOV_5)]
    highlights = find_highlights(games, summarize_categories(games))
    assert not [h for h in highlights if h["kind"] == "streak"]


def test_improvement_needs_a_real_drop_over_a_full_session():
    clear = _flag("clear_given_back", "clearing")
    games = [
        _game(1, OCT_31, [clear, clear]),
        _game(2, OCT_31, [clear, clear]),
        _game(3, NOV_5, [clear]),
        _game(4, NOV_5),
    ]
    highlights = find_highlights(games, summarize_categories(games))
    improving = [h for h in highlights if h["kind"] == "improving"]
    assert [h["title"] for h in improving] == ["Clearing is improving"]
    assert improving[0]["detail"] == ("2.0 a game before, 0.5 in your latest session")


def test_no_games_means_no_targets_or_highlights():
    assert summarize_categories([]) == []
    assert find_highlights([], []) == []

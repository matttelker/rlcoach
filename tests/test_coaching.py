"""Tests for training targets and highlights built from game reviews."""

from __future__ import annotations

from datetime import date, timedelta

from rlcoach.coaching import (
    MIN_POOL,
    UNMEASURED_SHARE,
    FlagRow,
    GoalRow,
    ReviewedGame,
    SituationRow,
    extra_risk,
    find_highlights,
    measure_risks,
    pick_targets,
    summarize_categories,
)

OCT_31 = date(2026, 10, 31)
NOV_5 = date(2026, 11, 5)


def _flag(kind, category, cost_goal=False):
    return FlagRow(kind, category, cost_goal)


def _game(n, day, flags=(), goals=(), result="WIN", score=(2, 1), situations=()):
    return ReviewedGame(
        replay_id=f"r{n}",
        play_date=day,
        result=result,
        my_score=score[0],
        opponent_score=score[1],
        map="Stadium_P",
        flags=list(flags),
        goals=list(goals),
        situations=list(situations),
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


def test_sessions_count_each_days_games_and_flags():
    upfield = _flag("caught_upfield", "rotation")
    games = [
        _game(1, OCT_31),
        _game(2, OCT_31),
        _game(3, OCT_31, [upfield]),
        _game(4, NOV_5, [upfield, upfield]),
    ]
    rotation = _by_category(summarize_categories(games))["rotation"]
    assert rotation["sessions"] == [
        {"play_date": "2026-10-31", "games": 3, "flags": 1},
        {"play_date": "2026-11-05", "games": 1, "flags": 2},
    ]


def _days(count, flags_in=lambda n: ()):
    """`count` games a day apart, oldest first, with `flags_in(n)` in game n."""
    return [
        _game(n, OCT_31 + timedelta(days=n), list(flags_in(n))) for n in range(count)
    ]


def test_fewer_than_ten_games_have_no_trend():
    upfield = _flag("caught_upfield", "rotation")
    games = _days(9, lambda n: [upfield])
    rotation = _by_category(summarize_categories(games))["rotation"]
    assert rotation["trend_games"] == 0
    assert (rotation["recent_per_game"], rotation["earlier_per_game"]) == (None, None)
    one = _by_category(summarize_categories([_game(1, NOV_5)]))["rotation"]
    assert (one["trend_games"], one["recent_per_game"]) == (0, None)


def test_ten_games_compare_the_last_five_with_the_five_before():
    upfield = _flag("caught_upfield", "rotation")
    games = _days(10, lambda n: [upfield] if n < 5 else [])
    rotation = _by_category(summarize_categories(games))["rotation"]
    assert rotation["trend_games"] == 5
    assert (rotation["recent_per_game"], rotation["earlier_per_game"]) == (0, 1.0)


def test_the_trend_compares_your_last_ten_games_with_the_ten_before():
    upfield = _flag("caught_upfield", "rotation")

    def flags(n):
        # Games 0-4 are older than the comparison and must not count
        if n < 5:
            return [upfield] * 5
        return [upfield] * (2 if n < 15 else 1)

    rotation = _by_category(summarize_categories(_days(25, flags)))["rotation"]
    assert rotation["trend_games"] == 10
    assert rotation["earlier_per_game"] == 2.0
    assert rotation["recent_per_game"] == 1.0


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


def test_epic_saves_in_the_latest_session_are_highlights():
    games = [_game(n, OCT_31 if n == 1 else NOV_5) for n in range(1, 6)]
    for game, saves in zip(games, (1, 0, 1, 2, 1), strict=True):
        game.epic_saves = saves
    highlights = find_highlights(games, summarize_categories(games))
    saves = [h for h in highlights if h["kind"] == "epic_save"]

    # Newest first, at most two, and only from the latest session
    assert [(h["title"], h["replay_id"]) for h in saves] == [
        ("Epic save", "r5"),
        ("2 epic saves", "r4"),
    ]
    assert saves[0]["detail"] == "In the 2–1 on Stadium"


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


def _improving(games):
    highlights = find_highlights(games, summarize_categories(games))
    return [h for h in highlights if h["kind"] == "improving"]


def test_improvement_over_your_last_games_is_a_highlight():
    clear = _flag("clear_given_back", "clearing")
    games = _days(10, lambda n: [clear, clear] if n < 5 else [clear] * (n % 2))
    improving = _improving(games)
    assert [h["title"] for h in improving] == ["Clearing is improving"]
    assert improving[0]["detail"] == (
        "0.6 a game over your last 5 games, 2.0 over the 5 before"
    )


def test_improvement_needs_a_real_drop():
    clear = _flag("clear_given_back", "clearing")
    # 1.0 a game down to 0.8 is not much of a drop
    games = _days(10, lambda n: [clear] if n < 5 or n % 5 else [])
    assert _improving(games) == []


def test_improvement_needs_enough_games_to_compare():
    clear = _flag("clear_given_back", "clearing")
    games = [
        _game(1, OCT_31, [clear, clear]),
        _game(2, OCT_31, [clear, clear]),
        _game(3, NOV_5, [clear]),
        _game(4, NOV_5),
    ]
    assert _improving(games) == []


def test_no_games_means_no_targets_or_highlights():
    assert summarize_categories([]) == []
    assert find_highlights([], []) == []


# What each habit costs


def _rows(kind, zone, bad, conceded, count, mine=False):
    """`count` situations, the first `conceded` of them followed by a goal."""
    return [SituationRow(kind, zone, bad, i < conceded, mine) for i in range(count)]


def test_extra_risk_compares_bad_and_good_choices_in_the_same_zone():
    rows = [
        # By your net: half the bad choices and 3 in 10 good ones conceded
        *_rows("clear", "own_third", True, 15, 30),
        *_rows("clear", "own_third", False, 3, 10),
        # Upfield: 1 in 10 bad choices, and no good one
        *_rows("clear", "their_half", True, 1, 10),
        *_rows("clear", "their_half", False, 0, 30),
    ]
    # Pooled, 16 of 40 against 3 of 40 would be 0.325. By zone the gap is 0.2
    # by your net and 0.1 upfield, weighted by where the bad choices were
    assert extra_risk(rows) == 0.175


def test_a_zone_without_both_choices_is_left_out():
    rows = [
        *_rows("clear", "own_third", True, 6, 30),
        *_rows("clear", "own_third", False, 3, 30),
        *_rows("clear", "own_half", True, 10, 10),
    ]
    assert extra_risk(rows) == 0.1


def test_extra_risk_needs_enough_of_both_choices():
    bad = _rows("jump", "own_half", True, 10, MIN_POOL)
    good = _rows("jump", "own_half", False, 1, MIN_POOL)
    assert extra_risk(bad + good) is not None
    assert extra_risk(bad[1:] + good) is None
    assert extra_risk(bad + good[1:]) is None


def test_risks_are_measured_for_each_kind():
    rows = [
        *_rows("jump", "own_half", True, 6, 30),
        *_rows("jump", "own_half", False, 3, 30),
        *_rows("clear", "own_half", True, 6, 5),
    ]
    assert measure_risks(rows) == {"jump": 0.1, "clear": None}


def _clears(mine_bad, mine_good, others_bad, others_good, conceded=0):
    """Clear situations: `conceded` of my bad ones were followed by a goal."""
    return [
        *_rows("clear", "own_half", True, conceded, mine_bad, mine=True),
        *_rows("clear", "own_half", False, 0, mine_good, mine=True),
        *_rows("clear", "own_half", True, 0, others_bad),
        *_rows("clear", "own_half", False, 0, others_good),
    ]


def test_situation_summaries_give_your_share_beside_everyone_elses():
    games = [
        _game(1, OCT_31, situations=_clears(1, 1, 1, 3, conceded=1)),
        _game(2, NOV_5, situations=_clears(1, 1, 0, 0)),
    ]
    clearing = _by_category(summarize_categories(games, {"clear": 0.1}))["clearing"]
    [clear] = clearing["situations"]
    assert clear == {
        "kind": "clear",
        "what": "clears from your half",
        "bad_label": "given straight back",
        "count": 4,
        "bad": 2,
        "bad_share": 0.5,
        "others_bad_share": 0.25,
        "conceded_after_bad": 1,
        "extra_risk": 0.1,
        # The games haven't shown a clear given back costs goals, so it's free
        "proven": False,
        "goals_per_game": 0.0,
    }
    assert (clearing["cost_per_game"], clearing["cost_measured"]) == (0.0, True)


def test_a_proven_bad_choice_costs_its_extra_risk_each_time():
    misses = _rows("jump", "own_half", True, 0, 2, mine=True)
    games = [_game(1, OCT_31, situations=misses), _game(2, NOV_5)]
    whiffs = _by_category(summarize_categories(games, {"jump": 0.1}))["whiffs"]
    [jump] = whiffs["situations"]
    # 2 misses over 2 games, each 0.1 more likely to cost a goal
    assert (jump["proven"], jump["goals_per_game"]) == (True, 0.1)
    assert (whiffs["cost_per_game"], whiffs["cost_measured"]) == (0.1, True)


def test_a_situation_without_a_measured_risk_has_no_cost():
    games = [_game(1, OCT_31, situations=_clears(1, 1, 0, 0))]
    clearing = _by_category(summarize_categories(games, {}))["clearing"]
    [clear] = clearing["situations"]
    assert (clear["extra_risk"], clear["goals_per_game"]) == (None, None)
    assert (clearing["cost_per_game"], clearing["cost_measured"]) == (0, False)


def test_a_bad_choice_that_costs_nothing_measures_as_free():
    games = [_game(1, OCT_31, situations=_clears(3, 1, 0, 0))]
    clearing = _by_category(summarize_categories(games, {"clear": -0.05}))["clearing"]
    assert clearing["situations"][0]["goals_per_game"] == 0
    assert (clearing["cost_per_game"], clearing["cost_measured"]) == (0, True)


def test_every_category_lists_its_kinds_of_situation():
    categories = _by_category(summarize_categories([_game(1, OCT_31)], {}))
    kinds = {key: [s["kind"] for s in c["situations"]] for key, c in categories.items()}
    assert kinds["last_back"] == ["shot_last_back", "last_back_challenge"]
    assert kinds["rotation"] == ["commit", "opp_attack"]
    assert kinds["clearing"] == ["clear"]
    assert kinds["whiffs"] == ["jump"]
    assert kinds["kickoffs"] == ["kickoff"]
    assert kinds["goalkeeping"] == []


def test_without_risks_the_games_measure_them():
    situations = [
        *_rows("jump", "own_half", True, 6, 30, mine=True),
        *_rows("jump", "own_half", False, 3, 30),
    ]
    games = [_game(1, OCT_31, situations=situations)]
    whiffs = _by_category(summarize_categories(games))["whiffs"]
    assert whiffs["situations"][0]["extra_risk"] == 0.1
    # 30 missed jumps in the one game, each 0.1 more likely to cost a goal
    assert whiffs["cost_per_game"] == 3.0


def test_an_unmeasured_category_costs_half_its_goals_a_game():
    miss = _flag("missed_save", "goalkeeping", cost_goal=True)
    games = [_game(1, OCT_31, [miss, miss]), _game(2, NOV_5, [miss])]
    goalkeeping = _by_category(summarize_categories(games, {}))["goalkeeping"]
    assert goalkeeping["goals_cost"] == 3
    assert goalkeeping["cost_per_game"] == round(3 / 2 * UNMEASURED_SHARE, 3)
    assert goalkeeping["cost_measured"] is False


def test_targets_rank_by_cost_a_game_before_goals():
    # Last back: one goal over 4 games, unmeasured, so 0.125 a game.
    # Whiffs: no flags, but 2 missed jumps at 0.5 extra risk, 0.25 a game
    commits = _rows("jump", "own_half", True, 0, 2, mine=True)
    games = [
        _game(1, OCT_31, [_flag("last_back_upfield", "last_back", cost_goal=True)]),
        _game(2, OCT_31, situations=commits),
        _game(3, NOV_5),
        _game(4, NOV_5),
    ]
    targets = pick_targets(summarize_categories(games, {"jump": 0.5}))
    assert [(t["category"], t["cost_per_game"]) for t in targets] == [
        ("whiffs", 0.25),
        ("last_back", 0.125),
    ]


def test_goals_on_kinds_no_situation_covers_count_on_top_of_the_measured_cost():
    """A given-back clear is judged by its situation, which hasn't been shown to
    cost goals. A missed clear by your net has none, so its goal counts at half."""
    flags = [
        _flag("clear_given_back", "clearing", cost_goal=True),
        _flag("missed_clear", "clearing", cost_goal=True),
    ]
    games = [_game(1, OCT_31, flags, situations=_clears(2, 2, 0, 0))]
    clearing = _by_category(summarize_categories(games, {"clear": 0.1}))["clearing"]
    assert clearing["cost_per_game"] == round(1 * UNMEASURED_SHARE, 3)
    assert clearing["cost_measured"] is True

"""Tests for the parser's demolitions."""

from __future__ import annotations

from rlcoach.events.demos import detect_demos
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import ParserDemoEvent
from tests.fixtures.builders import create_test_frame, create_test_player


def _frame(t, victim_at, *events):
    car = create_test_player("victim", 0, position=victim_at)
    return create_test_frame(t, [car], demos=list(events))


def _demo(t, attacker=None):
    return ParserDemoEvent(timestamp=t, victim_id="victim", attacker_id=attacker)


HERE = Vec3(500.0, 0.0, 17.0)
ELSEWHERE = Vec3(-2500.0, 0.0, 17.0)


def _found(frames):
    return [(d.t, d.victim, d.attacker) for d in detect_demos(frames)]


def test_a_demo_names_its_victim_and_attacker():
    assert _found([_frame(2.0, HERE, _demo(2.0, "attacker"))]) == [
        (2.0, "victim", "attacker")
    ]


def test_a_repeat_at_the_same_spot_counts_once_and_fills_in_the_attacker():
    frames = [
        _frame(2.0, HERE, _demo(2.0)),
        _frame(4.0, HERE, _demo(4.0, "attacker")),
        _frame(6.0, HERE, _demo(6.0, "someone")),
    ]
    assert _found(frames) == [(4.0, "victim", "attacker")]


def test_a_demo_elsewhere_or_later_is_a_new_one():
    frames = [
        _frame(2.0, HERE, _demo(2.0, "attacker")),
        _frame(4.0, ELSEWHERE, _demo(4.0, "attacker")),
        _frame(10.0, ELSEWHERE, _demo(10.0, "attacker")),
    ]
    assert [t for t, _, _ in _found(frames)] == [2.0, 4.0, 10.0]


def test_the_same_report_twice_counts_once():
    frames = [_frame(2.0, HERE, _demo(2.0, "attacker"), _demo(2.0, "attacker"))]
    assert len(_found(frames)) == 1

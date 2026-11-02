"""Tests for coaching insights."""

from typing import Any

from rlcoach.analysis.insights import generate_player_insights


def _waste_insight(waste: float) -> dict[str, Any] | None:
    """Return the boost waste insight for a player, if one was generated."""
    insights = generate_player_insights({"player_id": "p1", "boost": {"waste": waste}})
    matches = [i for i in insights if "boost_waste" in i.get("evidence", {})]
    return matches[0] if matches else None


def test_waste_insight_needs_more_than_200_units():
    assert _waste_insight(200.0) is None
    assert _waste_insight(200.1) is not None


def test_waste_insight_reports_an_estimate_with_its_evidence():
    insight = _waste_insight(330.4)

    assert insight is not None
    assert insight["contributing_factors"][0] == "Estimated 330 units of boost wasted"
    assert insight["evidence"] == {"boost_waste": 330.4}


def test_waste_insight_describes_spending_not_collecting():
    """Waste measures boost spent; pad collection is reported as overfill."""
    insight = _waste_insight(330.4)

    assert insight is not None
    text = " ".join([*insight["contributing_factors"], insight["recommendation"]])
    assert "top speed" in text
    for overfill_advice in ("collecting", "big boost", "small pads"):
        assert overfill_advice not in text.lower()

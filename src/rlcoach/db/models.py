"""The database's tables.

Times are stored in UTC. A game's play_date is the day it was played on in
your timezone, worked out when it loads.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import DateTime, Float


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), float: Float}


class Replay(Base):
    """One loaded game, seen from your side."""

    __tablename__ = "replays"

    replay_id: Mapped[str] = mapped_column(primary_key=True)  # The file's SHA-256
    source_file: Mapped[str]
    file_hash: Mapped[str] = mapped_column(index=True)
    ingested_at: Mapped[datetime | None] = mapped_column(default=_now)
    played_at_utc: Mapped[datetime]
    play_date: Mapped[date]
    map: Mapped[str]
    playlist: Mapped[str]  # See modes.py
    team_size: Mapped[int]
    duration_seconds: Mapped[float]
    overtime: Mapped[bool | None] = mapped_column(default=False)
    my_player_id: Mapped[str | None] = mapped_column(ForeignKey("players.player_id"))
    my_team: Mapped[str | None]  # "BLUE" or "ORANGE"
    my_score: Mapped[int | None]
    opponent_score: Mapped[int | None]
    result: Mapped[str | None]  # "WIN", "LOSS" or "DRAW"

    player_stats: Mapped[list[PlayerGameStats]] = relationship(
        back_populates="replay", cascade="all, delete-orphan"
    )
    review: Mapped[GameReview | None] = relationship(
        back_populates="replay", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_replays_play_date", text("play_date DESC")),
        Index("ix_replays_playlist", "playlist"),
        Index("ix_replays_result", "result"),
    )


class Player(Base):
    """Everyone you've played with or against, and you."""

    __tablename__ = "players"

    player_id: Mapped[str] = mapped_column(primary_key=True)  # See identity.py
    display_name: Mapped[str]  # From their most recent game
    platform: Mapped[str | None]
    is_me: Mapped[bool | None] = mapped_column(default=False, index=True)
    is_tagged_teammate: Mapped[bool | None] = mapped_column(default=False)
    teammate_notes: Mapped[str | None] = mapped_column(Text)
    # The first and last games they were in, by when they were played
    first_seen_utc: Mapped[datetime | None] = mapped_column(default=_now)
    last_seen_utc: Mapped[datetime | None] = mapped_column(default=_now)


class PlayerGameStats(Base):
    """One player's numbers in one game."""

    __tablename__ = "player_game_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    replay_id: Mapped[str] = mapped_column(
        ForeignKey("replays.replay_id", ondelete="CASCADE")
    )
    player_id: Mapped[str] = mapped_column(
        ForeignKey("players.player_id", ondelete="CASCADE")
    )
    team: Mapped[str]
    is_me: Mapped[bool | None] = mapped_column(default=False)

    goals: Mapped[int | None] = mapped_column(default=0)
    assists: Mapped[int | None] = mapped_column(default=0)
    saves: Mapped[int | None] = mapped_column(default=0)
    shots: Mapped[int | None] = mapped_column(default=0)
    shooting_pct: Mapped[float | None]
    score: Mapped[int | None] = mapped_column(default=0)
    demos_inflicted: Mapped[int | None] = mapped_column(default=0)
    demos_taken: Mapped[int | None] = mapped_column(default=0)
    # The game's own counts, empty for a replay that carries none. Its clear is a
    # touch from deep in front of your goal, narrower than the review's clears
    # from your half in game_reviews
    epic_saves: Mapped[int | None]
    clears: Mapped[int | None]
    centers: Mapped[int | None]
    aerial_hits: Mapped[int | None]

    bcpm: Mapped[float | None]  # Boost used per minute, Ballchasing's BCPM
    avg_boost: Mapped[float | None]
    time_zero_boost_s: Mapped[float | None]
    time_full_boost_s: Mapped[float | None]
    boost_collected: Mapped[float | None]
    boost_stolen: Mapped[float | None]

    avg_speed_kph: Mapped[float | None]
    time_supersonic_s: Mapped[float | None]

    behind_ball_pct: Mapped[float | None]
    first_man_pct: Mapped[float | None]
    second_man_pct: Mapped[float | None]
    third_man_pct: Mapped[float | None]

    replay: Mapped[Replay] = relationship(back_populates="player_stats")

    __table_args__ = (
        UniqueConstraint("replay_id", "player_id", name="uq_replay_player"),
        Index("ix_player_game_stats_replay", "replay_id"),
        Index("ix_player_game_stats_player", "player_id"),
        Index("ix_player_game_stats_is_me", "is_me"),
    )


class GameReview(Base):
    """The mistake detector's review of you in one game.

    `status` is "ok", "unsupported" for arenas the rules don't fit, or "error".
    """

    __tablename__ = "game_reviews"

    replay_id: Mapped[str] = mapped_column(
        ForeignKey("replays.replay_id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[str]
    status: Mapped[str]
    error: Mapped[str | None] = mapped_column(Text)
    clears: Mapped[int | None] = mapped_column(default=0)
    clears_given_back: Mapped[int | None] = mapped_column(default=0)
    reviewed_at: Mapped[datetime | None] = mapped_column(default=_now)

    replay: Mapped[Replay] = relationship(back_populates="review")
    mistakes: Mapped[list[ReviewMistake]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ReviewMistake.t",
    )
    goals: Mapped[list[ReviewGoal]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ReviewGoal.t",
    )
    kickoffs: Mapped[list[ReviewKickoff]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="ReviewKickoff.t",
    )


class ReviewMistake(Base):
    """One flagged moment from a game review."""

    __tablename__ = "review_mistakes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    replay_id: Mapped[str] = mapped_column(
        ForeignKey("game_reviews.replay_id", ondelete="CASCADE")
    )
    kind: Mapped[str]
    category: Mapped[str]
    t: Mapped[float]
    seconds_left: Mapped[float]
    clock: Mapped[str]
    score: Mapped[str]
    duration: Mapped[float | None] = mapped_column(default=0.0)
    what: Mapped[str] = mapped_column(Text)
    instead: Mapped[str] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(Text, default="")
    cost_goal: Mapped[bool | None] = mapped_column(default=False)

    review: Mapped[GameReview] = relationship(back_populates="mistakes")

    __table_args__ = (
        Index("ix_review_mistakes_replay", "replay_id"),
        Index("ix_review_mistakes_category", "category"),
    )


class ReviewGoal(Base):
    """One goal by either team, with the defending review for goals against."""

    __tablename__ = "review_goals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    replay_id: Mapped[str] = mapped_column(
        ForeignKey("game_reviews.replay_id", ondelete="CASCADE")
    )
    t: Mapped[float]
    seconds_left: Mapped[float]
    clock: Mapped[str]
    score: Mapped[str]  # Before the goal, your team first
    ours: Mapped[bool]
    scorer: Mapped[str]
    by_me: Mapped[bool | None] = mapped_column(default=False)
    assist_by_me: Mapped[bool | None] = mapped_column(default=False)
    winner: Mapped[bool | None] = mapped_column(default=False)
    equalizer: Mapped[bool | None] = mapped_column(default=False)
    # Goals against only
    on_me: Mapped[bool | None]
    summary: Mapped[str | None] = mapped_column(Text)
    lines: Mapped[str | None] = mapped_column(Text)  # JSON array

    review: Mapped[GameReview] = relationship(back_populates="goals")

    __table_args__ = (Index("ix_review_goals_replay", "replay_id"),)


class ReviewKickoff(Base):
    """One kickoff in a reviewed game, on the game clock.

    `ball_y_after` is where the ball was a second after the hit, with blue
    attacking toward +y. `events.kickoffs.kickoff_result` reads it as won, even
    or lost for a team.
    """

    __tablename__ = "review_kickoffs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    replay_id: Mapped[str] = mapped_column(
        ForeignKey("game_reviews.replay_id", ondelete="CASCADE")
    )
    t: Mapped[float]  # When the cars were released
    seconds_left: Mapped[float]
    clock: Mapped[str]
    score: Mapped[str]  # Before the kickoff, your team first
    phase: Mapped[str]  # "INITIAL", or "OT" for the one that starts overtime
    first_touch_player: Mapped[str | None]
    first_touch_team: Mapped[str | None]
    time_to_first_touch: Mapped[float | None]
    ball_y_after: Mapped[float | None]

    review: Mapped[GameReview] = relationship(back_populates="kickoffs")
    cars: Mapped[list[ReviewKickoffCar]] = relationship(
        back_populates="kickoff", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_review_kickoffs_replay", "replay_id"),)


class ReviewKickoffCar(Base):
    """How one car played one kickoff. See `events.kickoffs.KickoffPlayer`."""

    __tablename__ = "review_kickoff_cars"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kickoff_id: Mapped[int] = mapped_column(
        ForeignKey("review_kickoffs.id", ondelete="CASCADE")
    )
    player_id: Mapped[str]
    team: Mapped[int | None]
    is_me: Mapped[bool]
    role: Mapped[str]  # GO, CHEAT, WING or BACK
    spot: Mapped[str | None]  # DIAGONAL, OFF_CENTRE or BACK
    approach: Mapped[str]
    boost_used: Mapped[float]
    time_to_ball: Mapped[float | None]
    flip_lead: Mapped[float | None]  # Seconds before contact its flip began
    reach_time: Mapped[float | None]  # Seconds from the release to 1000 uu
    speed_at_contact: Mapped[float | None]

    kickoff: Mapped[ReviewKickoff] = relationship(back_populates="cars")

    __table_args__ = (
        Index("ix_review_kickoff_cars_kickoff", "kickoff_id"),
        Index("ix_review_kickoff_cars_player", "player_id"),
    )


class ReviewGrade(Base):
    """Your verdict on one call the review made: right or wrong.

    Grades sit apart from the review, so `rlcoach reviews --redo` keeps them.
    `ref` names the call: a flagged moment by its kind and time, a goal against
    by its time. `kind` and `label` record what the review said when you graded
    it, so a grade only applies while the review still says the same thing.
    """

    __tablename__ = "review_grades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    replay_id: Mapped[str] = mapped_column(
        ForeignKey("replays.replay_id", ondelete="CASCADE")
    )
    item: Mapped[str]  # "mistake" or "goal"
    ref: Mapped[str]
    kind: Mapped[str]
    label: Mapped[str] = mapped_column(Text)
    grade: Mapped[str]  # "right" or "wrong"
    graded_at: Mapped[datetime | None] = mapped_column(default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("replay_id", "item", "ref", name="uq_review_grade"),
        Index("ix_review_grades_replay", "replay_id"),
    )


class Benchmark(Base):
    """What players of one rank average for one stat in one playlist."""

    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric: Mapped[str]
    playlist: Mapped[str]
    rank_tier: Mapped[str]
    median_value: Mapped[float]
    p25_value: Mapped[float | None]
    p75_value: Mapped[float | None]
    elite_threshold: Mapped[float | None]
    source: Mapped[str]
    source_date: Mapped[date | None]
    notes: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime | None] = mapped_column(default=_now)

    __table_args__ = (
        UniqueConstraint("metric", "playlist", "rank_tier", name="uq_benchmark"),
        Index("ix_benchmarks_lookup", "metric", "playlist", "rank_tier"),
    )

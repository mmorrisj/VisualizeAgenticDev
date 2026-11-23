"""Storage (spec section 11.3): SQLAlchemy, SQLite by default, Postgres by URL.

The committed results file (L2) is the hand-off format; the site never reads
this database.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, create_engine, delete, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from . import LAB_ROOT

DEFAULT_URL = f"sqlite:///{LAB_ROOT / 'data' / 'lab.db'}"


class Base(DeclarativeBase):
    pass


class Run(Base):
    """One run: one task, one prompt variant, one model, one repeat."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                              default=lambda: datetime.now(timezone.utc))
    profile: Mapped[str] = mapped_column(String(32), default="adhoc")
    mode: Mapped[str] = mapped_column(String(16), default="one-shot")
    task: Mapped[str] = mapped_column(String(64), index=True)
    variant: Mapped[str] = mapped_column(String(64), index=True)
    model: Mapped[str] = mapped_column(String(64), index=True)
    gateway_id: Mapped[str] = mapped_column(String(128), default="")
    served_model: Mapped[str] = mapped_column(String(128), default="")
    repeat: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16))           # ok, refused, max_tokens, hit_limit, error
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    label: Mapped[str] = mapped_column(String(32), default="checked")
    check_details: Mapped[dict] = mapped_column(JSON, default=dict)
    tokens: Mapped[dict] = mapped_column(JSON, default=dict)  # tokens.Usage.to_dict()
    chars_sent: Mapped[int] = mapped_column(Integer, default=0)
    chars_received: Mapped[int] = mapped_column(Integer, default=0)
    requests: Mapped[int] = mapped_column(Integer, default=1)
    latency_s: Mapped[float] = mapped_column(Float, default=0.0)
    stop: Mapped[str] = mapped_column(String(32), default="")
    effort: Mapped[str] = mapped_column(String(16), default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    judge: Mapped[dict] = mapped_column(JSON, default=dict)   # judge.judge() result, plus "cross_check"
    session: Mapped[dict] = mapped_column(JSON, default=dict) # harness mode: requests, tool calls, transcript

    @property
    def key(self) -> str:
        """Stable identity across databases and exports."""
        return f"{self.task}--{self.variant}--{self.model}--{self.repeat}"


class CustomTest(Base):
    """Part C: one student's own test, through every step of spec section 10.3.

    Students may bring real work, so these rows expire (spec section 13) and are
    deleted with their runs by Store.purge_expired().
    """

    __tablename__ = "custom_tests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)        # random; also the page address
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                              default=lambda: datetime.now(timezone.utc))
    expires: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    student: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="new")    # new, assessed, ready, running, done, error
    prompt: Mapped[str] = mapped_column(Text)
    files: Mapped[dict] = mapped_column(JSON, default=dict)            # name -> text
    check: Mapped[dict] = mapped_column(JSON, default=dict)            # custom_checks.CustomCheck
    assessment: Mapped[dict] = mapped_column(JSON, default=dict)       # assess.Assessment
    assessment_call: Mapped[dict] = mapped_column(JSON, default=dict)  # model, attempts, tokens, error
    verdict: Mapped[dict] = mapped_column(JSON, default=dict)          # the student's agree / disagree
    rubric: Mapped[dict] = mapped_column(JSON, default=dict)           # assess.Rubric
    rubric_call: Mapped[dict] = mapped_column(JSON, default=dict)
    rubric_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)             # prompts, models, judge, repeats
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")

    @property
    def task_key(self) -> str:
        """The `task` value of this test's runs in the runs table."""
        return f"custom:{self.id}"


class Collected(Base):
    """A class results file a student submitted to the collector (spec section 10.2)."""

    __tablename__ = "collected"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    received: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                               default=lambda: datetime.now(timezone.utc))
    student: Mapped[str] = mapped_column(String(64), default="")
    document: Mapped[dict] = mapped_column(JSON)


class Store:
    def __init__(self, url: str | None = None):
        url = url or os.environ.get("PROMPTLAB_DB_URL") or DEFAULT_URL
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self._write_lock = threading.Lock()  # the app and the class kit write from worker threads

    def _add_missing_columns(self):
        """Columns added after a database was created (L3 added `session`).

        Additive only. A schema change that is not a new nullable column needs a
        real migration tool (Alembic) instead.
        """
        existing = {c["name"] for c in inspect(self.engine).get_columns(Run.__tablename__)}
        with self.engine.begin() as conn:
            for column in Run.__table__.columns:
                if column.name not in existing:
                    kind = column.type.compile(dialect=self.engine.dialect)
                    conn.execute(text(f'ALTER TABLE {Run.__tablename__} ADD COLUMN "{column.name}" {kind}'))

    def add(self, row):
        with self._write_lock, Session(self.engine, expire_on_commit=False) as session:
            session.add(row)
            session.commit()
        return row

    def update(self, row):
        with self._write_lock, Session(self.engine, expire_on_commit=False) as session:
            session.merge(row)
            session.commit()
        return row

    def get(self, model, key):
        with Session(self.engine, expire_on_commit=False) as session:
            return session.get(model, key)

    def all(self, model) -> list:
        with Session(self.engine) as session:
            return list(session.scalars(select(model)))

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete part C tests past their expiry date, with their runs. Returns how many tests."""
        now = now or datetime.now(timezone.utc)
        with Session(self.engine) as session:
            expired = [t for t in session.scalars(select(CustomTest))
                       if _aware(t.expires) <= now]
            for test in expired:
                session.execute(delete(Run).where(Run.task == test.task_key))
                session.delete(test)
            session.commit()
        return len(expired)

    def runs(self, **filters) -> list[Run]:
        with Session(self.engine) as session:
            query = select(Run).order_by(Run.id)
            for key, value in filters.items():
                query = query.where(getattr(Run, key) == value)
            return list(session.scalars(query))


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone-aware columns; they are stored in UTC."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

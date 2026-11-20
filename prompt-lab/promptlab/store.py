"""Storage (spec section 11.3): SQLAlchemy, SQLite by default, Postgres by URL.

The committed results file (L2) is the hand-off format; the site never reads
this database.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, create_engine, select
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
    status: Mapped[str] = mapped_column(String(16))           # ok, refused, max_tokens, error
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

    @property
    def key(self) -> str:
        """Stable identity across databases and exports."""
        return f"{self.task}--{self.variant}--{self.model}--{self.repeat}"


class Store:
    def __init__(self, url: str | None = None):
        url = url or os.environ.get("PROMPTLAB_DB_URL") or DEFAULT_URL
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url)
        Base.metadata.create_all(self.engine)

    def add(self, run: Run) -> Run:
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(run)
            session.commit()
        return run

    def update(self, run: Run) -> Run:
        with Session(self.engine, expire_on_commit=False) as session:
            session.merge(run)
            session.commit()
        return run

    def runs(self, **filters) -> list[Run]:
        with Session(self.engine) as session:
            query = select(Run).order_by(Run.id)
            for key, value in filters.items():
                query = query.where(getattr(Run, key) == value)
            return list(session.scalars(query))

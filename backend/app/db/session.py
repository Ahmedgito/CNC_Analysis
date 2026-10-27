"""Engine and session factory.

Synchronous SQLAlchemy over psycopg 3. FastAPI runs sync dependencies in its threadpool, and the
async answer pipeline hops to the threadpool for DB work. This keeps one driver for the API, the
ingest CLI and Alembic, and avoids psycopg's async mode, which does not run on Windows' default
event loop.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

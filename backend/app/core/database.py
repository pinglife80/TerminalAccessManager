import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

# Create async engine
# SQLite (aiosqlite) does not support connection-pool tuning arguments
# (pool_size/max_overflow/pool_timeout/pool_use_lifo), so conditionally exclude them.
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update({
        "pool_timeout": 60,
        "pool_use_lifo": True,
        "pool_size": 30,
        "max_overflow": 100,
    })

engine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs,
)

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Alias for use in background tasks (non-dependency injection)
async_session_factory = async_session_maker

# Base class for models
class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables.

    SQLite (development/tests) keeps ``create_all`` for convenience.

    PostgreSQL (production) delegates schema management entirely to Alembic:
    ``alembic upgrade head`` is idempotent (no-op when already at head), so it
    is safe to run on every startup. It is invoked as a subprocess rather than
    in-process because alembic/env.py calls ``asyncio.run()``, which would fail
    inside the running uvicorn event loop.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        logger.info(
            "init_db: SQLite backend detected, applying schema via create_all "
            "(development/test convenience)"
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("init_db: create_all completed for SQLite")
        return

    logger.info(
        "init_db: PostgreSQL backend detected, delegating schema management "
        "to Alembic (alembic upgrade head)"
    )

    # Drift pre-check: detect the "create_all bootstrap without Alembic stamp"
    # state (core schema exists but alembic_version is empty/missing) before
    # running `alembic upgrade head`, which would otherwise replay 001 from
    # base and fail with DuplicateTableError. Fail fast with actionable
    # guidance instead — this also protects environments that upgrade from a
    # version whose manage.sh lacks the drift guard.
    from sqlalchemy import text

    async with engine.connect() as conn:
        core_exists = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = 'data_sources'"
                )
            )
        ).scalar()
        version_tbl = (
            await conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.tables "
                    "WHERE table_name = 'alembic_version'"
                )
            )
        ).scalar()
        version_rows = 0
        if version_tbl:
            version_rows = (
                await conn.execute(text("SELECT COUNT(*) FROM alembic_version"))
            ).scalar()
        logger.info(
            "init_db: drift pre-check data_sources=%s alembic_version_rows=%s",
            core_exists,
            version_rows,
        )

    if core_exists and version_rows == 0:
        raise RuntimeError(
            "Database drift detected: schema already exists but 'alembic_version' "
            "is empty or missing (prior create_all bootstrap without Alembic "
            "tracking). Before upgrading, align the version stamp: "
            "python -m alembic stamp head  (verify: python -m alembic current)"
        )

    import os
    import subprocess
    import sys

    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    logger.info(
        "init_db: running 'alembic upgrade head' as subprocess (cwd=%s)",
        base_dir,
    )
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=base_dir,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        logger.error(
            "init_db: Alembic migration failed (exit=%s)\n"
            "--- stdout ---\n%s\n"
            "--- stderr ---\n%s",
            proc.returncode, proc.stdout, proc.stderr,
        )
        raise RuntimeError(f"Alembic migration failed:\n{proc.stdout}\n{proc.stderr}")

    # Alembic logs progress to stderr; surface it for migration troubleshooting.
    if proc.stdout.strip():
        logger.info("init_db: Alembic stdout:\n%s", proc.stdout.strip())
    if proc.stderr.strip():
        logger.info("init_db: Alembic stderr:\n%s", proc.stderr.strip())
    logger.info("init_db: Alembic upgrade head completed successfully (exit=0)")

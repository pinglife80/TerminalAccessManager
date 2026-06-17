from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Create async engine
# SQLite does not support pool_size/max_overflow, so conditionally exclude them
_engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

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
    """Initialize database tables

    Note: For production deployments, use Alembic migrations instead:
        alembic upgrade head

    This method is kept for development convenience only.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

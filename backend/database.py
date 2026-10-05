"""
Moteur SQLAlchemy asynchrone + fournisseur de sessions pour FastAPI (Depends).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from config import settings

# pool_size/max_overflow ne sont valides que pour le pool par défaut de
# Postgres (QueuePool) — SQLite (utilisé en tests, voir tests/conftest.py)
# utilise NullPool et rejette ces arguments. On les ajoute donc seulement
# quand la base cible n'est pas SQLite.
_engine_kwargs = {"echo": settings.ENVIRONMENT == "development", "pool_pre_ping": True}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Utilisé uniquement en dev rapide ; en pratique Alembic gère le schéma."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

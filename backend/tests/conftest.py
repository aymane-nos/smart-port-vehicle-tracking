"""
Configuration pytest commune à tous les tests backend.

Important : les tests tournent sur une base **SQLite de test dédiée**
(fichier local à ce dossier), PAS sur la base Postgres de développement.
`DATABASE_URL` est écrasée en tout premier, avant le moindre import de
`config`/`database`/`main`, pour que toute l'application (y compris les
routers) pointe vers cette base de test. Résultat : lancer `pytest` ne
touche jamais tes données de démo (seedées via scripts/seed_fake_data.py)
sur la vraie base Postgres.
"""
import os
from pathlib import Path

TEST_DB_PATH = Path(__file__).parent / "test_db.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_PATH}"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from database import AsyncSessionLocal, engine  # noqa: E402
from main import app  # noqa: E402
from models import DailyTrafficSummary, Detection, Vehicle  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _setup_test_schema():
    """Crée le schéma une fois pour toute la session de test, le supprime à la fin."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    await engine.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Isole chaque test : tables vides avant chaque test."""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Detection))
        await session.execute(delete(Vehicle))
        await session.execute(delete(DailyTrafficSummary))
        await session.commit()
    yield


@pytest_asyncio.fixture
async def client():
    """Client HTTP async branché directement sur l'app FastAPI (pas de vrai réseau)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Accès direct à une session BDD, pour les tests qui ne passent pas par l'API (ex: ETL)."""
    async with AsyncSessionLocal() as session:
        yield session

import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@db:5432/prices"
)

# Async engine for production
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine for testing and simple operations
sync_database_url = DATABASE_URL.replace("+asyncpg", "")
sync_engine = create_engine(sync_database_url, echo=False)
SessionLocal = sessionmaker(bind=sync_engine, class_=Session)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


def get_session():
    """Database dependency for FastAPI."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_session():
    """Async database dependency for FastAPI."""
    async with AsyncSessionLocal() as session:
        yield session

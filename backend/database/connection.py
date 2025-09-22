import os
import asyncio
from typing import AsyncGenerator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
import asyncpg
from contextlib import asynccontextmanager

from models.database import Base

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/trading_simulator"
)

# Supabase URL format: postgresql+asyncpg://postgres:[password]@[host]:5432/postgres
SUPABASE_URL = os.getenv("SUPABASE_DATABASE_URL")

# Use Supabase if available, otherwise fallback to local
FINAL_DATABASE_URL = SUPABASE_URL or DATABASE_URL

# Create async engine
engine = create_async_engine(
    FINAL_DATABASE_URL,
    poolclass=NullPool,  # Disable connection pooling for serverless
    echo=os.getenv("ENVIRONMENT") == "development",  # Log SQL in development
    future=True
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class DatabaseManager:
    """Database connection manager"""

    def __init__(self):
        self.engine = engine
        self.session_factory = AsyncSessionLocal
        self._initialized = False

    async def init_database(self):
        """Initialize database with tables"""
        if self._initialized:
            return

        try:
            print("🔄 Initializing database...")

            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            print("✅ Database tables created/verified")
            self._initialized = True

        except Exception as e:
            print(f"❌ Database initialization failed: {e}")
            raise

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session with automatic cleanup"""
        async with self.session_factory() as session:
            try:
                yield session
            except Exception as e:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def health_check(self) -> bool:
        """Check database connectivity"""
        try:
            async with self.get_session() as session:
                result = await session.execute(text("SELECT 1"))
                return result.scalar() == 1
        except Exception as e:
            print(f"❌ Database health check failed: {e}")
            return False

    async def close(self):
        """Close database connections"""
        await self.engine.dispose()

# Global database manager instance
db_manager = DatabaseManager()

# Dependency for FastAPI routes
async def get_database() -> AsyncSession:
    """FastAPI dependency for database sessions"""
    if not db_manager._initialized:
        await db_manager.init_database()

    async with db_manager.get_session() as session:
        yield session

# Initialize database function for startup
async def init_database():
    """Initialize database on startup"""
    await db_manager.init_database()

# Direct database access for services
async def get_db_session():
    """Get database session for services"""
    if not db_manager._initialized:
        await db_manager.init_database()

    return db_manager.get_session()

# Connection string builder for Supabase
def build_supabase_url(
    host: str,
    database: str,
    username: str,
    password: str,
    port: int = 5432
) -> str:
    """Build Supabase connection URL"""
    return f"postgresql+asyncpg://{username}:{password}@{host}:{port}/{database}"

# Environment-specific configurations
def get_database_config():
    """Get database configuration based on environment"""
    env = os.getenv("ENVIRONMENT", "development")

    if env == "production":
        # Production (Supabase)
        if not SUPABASE_URL:
            raise ValueError("SUPABASE_DATABASE_URL must be set in production")
        return {
            "url": SUPABASE_URL,
            "pool_size": 5,
            "max_overflow": 10,
            "echo": False
        }
    elif env == "testing":
        # Testing database
        return {
            "url": os.getenv(
                "TEST_DATABASE_URL",
                "postgresql+asyncpg://postgres:password@localhost:5432/trading_simulator_test"
            ),
            "pool_size": 1,
            "max_overflow": 0,
            "echo": False
        }
    else:
        # Development
        return {
            "url": DATABASE_URL,
            "pool_size": 5,
            "max_overflow": 5,
            "echo": True
        }

# Test database connection
async def test_connection():
    """Test database connection"""
    try:
        print("🔄 Testing database connection...")
        is_healthy = await db_manager.health_check()

        if is_healthy:
            print(f"✅ Database connected successfully: {FINAL_DATABASE_URL.split('@')[1] if '@' in FINAL_DATABASE_URL else 'localhost'}")
            return True
        else:
            print("❌ Database connection failed")
            return False

    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

if __name__ == "__main__":
    # Test connection when run directly
    asyncio.run(test_connection())
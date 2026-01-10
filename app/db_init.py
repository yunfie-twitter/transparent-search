"""Database initialization and migration utilities"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost/search_engine"
)

async def init_db():
    """Initialize database with schema from init.sql"""
    engine = create_async_engine(DATABASE_URL, echo=False)
    
    try:
        async with engine.begin() as conn:
            # Read and execute init.sql
            with open('/code/db/init.sql', 'r') as f:
                sql_content = f.read()
            
            # Execute each statement separately to handle multiple statements
            statements = sql_content.split(';')
            for statement in statements:
                statement = statement.strip()
                if statement:
                    try:
                        await conn.execute(text(statement))
                    except Exception as e:
                        # Log but continue for idempotent operations
                        print(f"Warning: {e}")
            
            await conn.commit()
            print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise
    finally:
        await engine.dispose()

async def run_migrations():
    """Run pending database migrations"""
    await init_db()

if __name__ == "__main__":
    asyncio.run(run_migrations())

from fastapi import FastAPI
from contextlib import asynccontextmanager
from .routers import search, suggest, click, images, admin, advanced_search
from .db_init import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Initializing database...")
    try:
        await init_db()
        print("✅ Database initialization complete")
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
    yield
    # Shutdown
    print("🛑 Shutting down...")

app = FastAPI(
    title="Transparent Search API",
    lifespan=lifespan
)

app.include_router(search.router)
app.include_router(suggest.router)
app.include_router(click.router)
app.include_router(images.router, prefix="/search") # /search/images
app.include_router(admin.router, prefix="/admin")
app.include_router(advanced_search.router, prefix="/search")  # /search/fuzzy

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

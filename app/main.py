from fastapi import FastAPI
from .routers import search, suggest, click, images, admin

app = FastAPI(title="Transparent Search API")

app.include_router(search.router)
app.include_router(suggest.router)
app.include_router(click.router)
app.include_router(images.router, prefix="/search") # /search/images
app.include_router(admin.router, prefix="/admin")

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

from fastapi import FastAPI
from .routers import search, suggest, click

app = FastAPI(title="Transparent Search API")

app.include_router(search.router)
app.include_router(suggest.router)
app.include_router(click.router)

@app.get("/")
async def root():
    return {"message": "Transparent Search API is running"}

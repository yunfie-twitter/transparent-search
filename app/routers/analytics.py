from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class SearchEventPayload(BaseModel):
    query: str
    results_count: int
    took_ms: int

@router.post("/events/search")
async def record_search(payload: SearchEventPayload):
    return {"status": "recorded"}

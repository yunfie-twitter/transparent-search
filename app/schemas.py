from pydantic import BaseModel

class ClickEvent(BaseModel):
    query_id: int
    page_id: int

from fastapi import APIRouter
from .endpoints import summaries, tags, sentiment

api_router = APIRouter()

api_router.include_router(summaries.router)
api_router.include_router(tags.router, prefix="/tags")
api_router.include_router(sentiment.router, prefix="/sentiment")

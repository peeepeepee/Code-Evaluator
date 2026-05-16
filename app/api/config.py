from fastapi import APIRouter
from app.api.auth_api import router as auth_router
from app.api.evaluation_api import router as evaluation_router
# Main API router that includes all other routers
api_router = APIRouter()

# Include all API routers here
api_router.include_router(auth_router)
api_router.include_router(evaluation_router)


"""
Admin API package — combines all admin sub-routers into a single router.

Usage in main.py:
    from app.api.admin import router as admin_router
    app.include_router(admin_router)
"""
from fastapi import APIRouter

from app.api.admin.documents import router as documents_router
from app.api.admin.users import router as users_router
from app.api.admin.queries import router as queries_router
from app.api.admin.evaluation import router as evaluation_router

router = APIRouter(prefix="/api/admin", tags=["Admin"])

router.include_router(documents_router)
router.include_router(users_router)
router.include_router(queries_router)
router.include_router(evaluation_router)

from fastapi import APIRouter

from app.api import audit_logs, auth, collaboration, export, pointclouds, tasks, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(pointclouds.router)
api_router.include_router(tasks.router)
api_router.include_router(users.router)
api_router.include_router(audit_logs.router)
api_router.include_router(collaboration.router)
api_router.include_router(export.router)

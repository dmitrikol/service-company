from fastapi import APIRouter
from .clients import router as clients_router
from .services import router as services_router
from .cars import router as cars_router
from .appointments import router as appointments_router
from .contacts import router as contacts_router
from .admin import router as admin_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(clients_router)
api_router.include_router(services_router)
api_router.include_router(cars_router)
api_router.include_router(appointments_router)
api_router.include_router(contacts_router)
api_router.include_router(admin_router)
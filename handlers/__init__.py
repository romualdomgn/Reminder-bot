from aiogram import Router

from .menu import router as menu_router
from .info import router as info_router
from .settings import router as settings_router
from .users import router as users_router
from .notifications import router as notifications_router
from .reminders_edit import router as reminders_edit_router
from .reminders_create import router as reminders_create_router

router = Router()

router.include_router(menu_router)
router.include_router(info_router)
router.include_router(settings_router)
router.include_router(users_router)
router.include_router(notifications_router)
router.include_router(reminders_edit_router)
router.include_router(reminders_create_router)

__all__ = ["router"]

from fastapi import APIRouter

from .auth import router as auth_router
from .chat import router as chat_router
from .chatbot import router as chatbot_router
from .contact import router as contact_router
from .friends import router as friends_router
from .group_chat import router as group_chat_router
from .main_page import router as main_page_router
from .online import router as online_router
from .profile import router as profile_router
from .search import router as search_router

router = APIRouter()

router.include_router(main_page_router)
router.include_router(auth_router)
router.include_router(contact_router)
router.include_router(search_router)
router.include_router(friends_router)
router.include_router(profile_router)
router.include_router(chat_router)
router.include_router(chatbot_router)
router.include_router(online_router)
router.include_router(group_chat_router)

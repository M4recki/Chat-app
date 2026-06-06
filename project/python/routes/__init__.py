# Re-exports for backward compatibility with tests
from ..chatbot_utils import chatbot_response
from ..settings import settings
from .chat import generate_channel_id
from .email import send_email
from .helpers import (authentication_in_header, csrf_context,
                      generate_csrf_token, get_current_user,
                      get_current_user_id, get_user,
                      get_user_from_request, is_authenticated,
                      is_csrf_token_valid, validate_csrf)
from .template import (DEFAULT_AVATAR_PATH, PROJECT_DIR, current_year,
                       encode_avatar, render_template, templates, user_image,
                       user_name)

from fastapi import APIRouter

router = APIRouter()

from .auth import router as auth_router
from .chat import router as chat_router
from .chatbot import router as chatbot_router
from .contact import router as contact_router
from .friends import router as friends_router
from .main_page import router as main_page_router
from .online import router as online_router
from .profile import router as profile_router
from .search import router as search_router

router.include_router(main_page_router)
router.include_router(auth_router)
router.include_router(contact_router)
router.include_router(search_router)
router.include_router(friends_router)
router.include_router(profile_router)
router.include_router(chat_router)
router.include_router(chatbot_router)
router.include_router(online_router)

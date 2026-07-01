from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..connection_manager import manager
from .helpers import is_authenticated

router = APIRouter()


@router.get("/online-users", dependencies=[Depends(is_authenticated)])
async def online_users():
    """Return the set of currently online user IDs as JSON.


    Returns:
        JSONResponse: A JSON object with online user IDs
    """
    return JSONResponse(content={"online_user_ids": list(manager.get_online_users())})

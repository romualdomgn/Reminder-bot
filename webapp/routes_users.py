from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException

from database import (
    add_bot_user,
    get_admin_my_users,
    get_admin_other_users,
    get_all_bot_users,
    get_bot_user,
    get_bot_user_names_map,
    get_invited_users,
    get_user_language,
    get_user_now,
    is_admin_id,
    remove_bot_user_with_cleanup,
    update_bot_user_name,
    update_invited_bot_user_name,
)
from i18n import t
from .auth import WebAppUser, get_current_user
from .schemas import UserCreateRequest, UserUpdateRequest
from .tg_sync import cleanup_chat_message, notify_admins_new_user, notify_user_removed, send_welcome_invite

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(user: WebAppUser = Depends(get_current_user)) -> dict:
    no_name = t(user.lang, "no_name")
    if not user.is_admin:
        invited = await get_invited_users(user.user_id)
        return {
            "is_admin": False,
            "invited_users": [{"user_id": u.user_id, "name": u.name or no_name, "is_admin": False} for u in invited],
        }
    _, offset_mins = await get_user_now(user.user_id)
    delta = timedelta(minutes=offset_mins)
    all_users = await get_all_bot_users()
    my_users = await get_admin_my_users()
    other_users = await get_admin_other_users()
    inviter_names = await get_bot_user_names_map({u.invited_by for u in other_users if u.invited_by is not None})
    return {
        "is_admin": True,
        "all_access": [{"user_id": u.user_id, "name": u.name or no_name, "is_admin": bool(u.is_admin), "created_at": (u.created_at + delta).strftime("%d.%m.%Y %H:%M")} for u in all_users],
        "my_users": [{"user_id": u.user_id, "name": u.name or no_name, "is_admin": False, "created_at": (u.created_at + delta).strftime("%d.%m.%Y %H:%M")} for u in my_users],
        "other_users": [
            {"user_id": u.user_id, "name": u.name or no_name, "is_admin": False, "created_at": (u.created_at + delta).strftime("%d.%m.%Y %H:%M"),
             "invited_by": u.invited_by, "inviter_name": inviter_names.get(u.invited_by, "") if u.invited_by else ""}
            for u in other_users
        ],
    }


@router.post("")
async def create_user(payload: UserCreateRequest, user: WebAppUser = Depends(get_current_user)) -> dict:
    if await get_bot_user(payload.user_id):
        raise HTTPException(status_code=409, detail=t(user.lang, "api_user_exists", uid=payload.user_id))
    clean_name = payload.name.strip()
    if not await add_bot_user(payload.user_id, clean_name, invited_by=user.user_id):
        raise HTTPException(status_code=409, detail=t(user.lang, "api_user_exists_short"))
    await send_welcome_invite(payload.user_id, lang=user.lang)
    if not user.is_admin:
        inviter = await get_bot_user(user.user_id)
        inviter_name = (inviter.name if inviter and inviter.name else user.first_name) or ""
        await notify_admins_new_user(new_user_id=payload.user_id, new_name=clean_name, inviter_id=user.user_id, inviter_name=inviter_name)
    return {"ok": True}


@router.patch("/{target_user_id}")
async def rename_user(target_user_id: int, payload: UserUpdateRequest, user: WebAppUser = Depends(get_current_user)) -> dict:
    clean_name = payload.name.strip()
    updated = await update_bot_user_name(target_user_id, clean_name) if user.is_admin else await update_invited_bot_user_name(user.user_id, target_user_id, clean_name)
    if not updated:
        raise HTTPException(status_code=404, detail=t(user.lang, "api_user_not_found"))
    return {"ok": True}


@router.delete("/{target_user_id}")
async def delete_user(target_user_id: int, user: WebAppUser = Depends(get_current_user)) -> dict:
    if is_admin_id(target_user_id):
        raise HTTPException(status_code=400, detail=t(user.lang, "api_cannot_del_admin"))
    target_lang = await get_user_language(target_user_id)
    removed, old_msg_ids = await remove_bot_user_with_cleanup(target_user_id, inviter_id=None if user.is_admin else user.user_id)
    if not removed:
        raise HTTPException(status_code=404, detail=t(user.lang, "api_user_not_found"))
    for mid in old_msg_ids:
        await cleanup_chat_message(target_user_id, mid, track_on_failure=False)
    await notify_user_removed(target_user_id, lang=target_lang)
    return {"ok": True}

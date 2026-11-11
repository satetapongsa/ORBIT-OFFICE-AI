"""Authentication endpoints (cookie-based browser sessions)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    MetaDep,
    SettingsDep,
    get_rate_limiter,
    get_reset_notifier,
    verify_csrf,
)
from app.core.config import Settings
from app.core.errors import UnauthenticatedError, error_response
from app.core.security import (
    ACCESS_COOKIE,
    ACCESS_COOKIE_PATH,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    InvalidTokenError,
    decode_access_token,
)
from app.models.identity import User
from app.repositories import users as user_repo
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    MessageResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    SessionInfo,
)
from app.schemas.common import ErrorResponse
from app.schemas.identity import UserOut
from app.services import auth as auth_service
from app.services.auth import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    secure = settings.secure_cookies
    access_max_age = settings.access_token_ttl_minutes * 60
    response.set_cookie(
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=access_max_age,
        path=ACCESS_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        expires=tokens.refresh_expires_at,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=secure,
        samesite="lax",
    )
    # Readable by the frontend so it can echo it in the X-CSRF-Token header.
    response.set_cookie(
        CSRF_COOKIE,
        tokens.csrf_token,
        expires=tokens.refresh_expires_at,
        path="/",
        httponly=False,
        secure=secure,
        samesite="lax",
    )


def _clear_session_cookies(response: Response, settings: Settings) -> None:
    secure = settings.secure_cookies
    response.delete_cookie(
        ACCESS_COOKIE, path=ACCESS_COOKIE_PATH, secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, secure=secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="lax")


async def _me(db: DbDep, user: User, tokens: IssuedTokens | None = None) -> MeResponse:
    permissions = sorted(await user_repo.permissions_for_user(db, user.id))
    fresh = await user_repo.get_by_id(db, user.id)
    return MeResponse(
        user=UserOut.model_validate(fresh or user),
        permissions=permissions,
        session=SessionInfo(access_expires_at=tokens.access_expires_at) if tokens else None,
    )


@router.post("/login", response_model=MeResponse, summary="Sign in with e-mail and password")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbDep,
    settings: SettingsDep,
    meta: MetaDep,
) -> MeResponse:
    result = await auth_service.login(
        db,
        settings,
        get_rate_limiter(request),
        email=payload.email,
        password=payload.password,
        meta=meta,
    )
    _set_session_cookies(response, settings, result.tokens)
    return await _me(db, result.user, result.tokens)


@router.post(
    "/refresh",
    response_model=MeResponse,
    summary="Rotate the refresh token",
    responses={401: {"model": ErrorResponse}},
)
async def refresh(
    request: Request, response: Response, db: DbDep, settings: SettingsDep, meta: MetaDep
) -> MeResponse | JSONResponse:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise UnauthenticatedError()  # no session at all: nothing to protect with CSRF
    verify_csrf(request)
    try:
        result = await auth_service.refresh(db, settings, refresh_token=token, meta=meta)
    except auth_service.SessionRefreshConflictError:
        raise  # keep cookies: another tab already holds the rotated session
    except UnauthenticatedError as exc:
        failed = error_response(exc)
        _clear_session_cookies(failed, settings)
        return failed
    _set_session_cookies(response, settings, result.tokens)
    return await _me(db, result.user, result.tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out this session")
async def logout(request: Request, db: DbDep, settings: SettingsDep, meta: MetaDep) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE)
    access_token = request.cookies.get(ACCESS_COOKIE)
    if refresh_token or access_token:
        verify_csrf(request)
    family_id = actor_id = None
    if access_token:
        try:
            claims = decode_access_token(settings, access_token)
            family_id, actor_id = claims.session_family_id, claims.user_id
        except InvalidTokenError:
            pass
    await auth_service.logout(
        db, refresh_token=refresh_token, family_id=family_id, actor_id=actor_id, meta=meta
    )
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_session_cookies(response, settings)
    return response


@router.get("/me", response_model=MeResponse, summary="Current user, roles and permissions")
async def me(user: CurrentUserDep, db: DbDep) -> MeResponse:
    db_user = await user_repo.get_by_id(db, user.id)
    if db_user is None:
        raise UnauthenticatedError()
    return MeResponse(user=UserOut.model_validate(db_user), permissions=sorted(user.permissions))


@router.post("/change-password", response_model=MeResponse, summary="Change own password")
async def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    meta: MetaDep,
) -> MeResponse:
    result = await auth_service.change_password(
        db,
        settings,
        principal=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        meta=meta,
    )
    _set_session_cookies(response, settings, result.tokens)
    return await _me(db, result.user, result.tokens)


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password-reset link",
)
async def request_password_reset(
    payload: PasswordResetRequest, request: Request, db: DbDep, settings: SettingsDep, meta: MetaDep
) -> MessageResponse:
    await auth_service.request_password_reset(
        db,
        settings,
        get_reset_notifier(request),
        get_rate_limiter(request),
        email=payload.email,
        meta=meta,
    )
    return MessageResponse(message="หากอีเมลนี้มีอยู่ในระบบ เราได้ส่งลิงก์สำหรับตั้งรหัสผ่านใหม่แล้ว")


@router.post(
    "/password-reset/confirm", response_model=MessageResponse, summary="Set a new password"
)
async def confirm_password_reset(
    payload: PasswordResetConfirm, db: DbDep, settings: SettingsDep, meta: MetaDep
) -> MessageResponse:
    await auth_service.confirm_password_reset(
        db, settings, token=payload.token, new_password=payload.new_password, meta=meta
    )
    return MessageResponse(message="ตั้งรหัสผ่านใหม่เรียบร้อยแล้ว กรุณาเข้าสู่ระบบ")

import datetime as dt

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import auth as auth_utils
from .. import models, schemas
from ..deps import get_session
from ..errors import api_error

router = APIRouter()


async def _register_login_attempt(
    session: AsyncSession,
    *,
    username: str,
    success: bool,
    user_id: str | None,
    detail: str | None = None,
) -> None:
    session.add(
        models.Audit(
            entity="auth",
            entity_id=username,
            action="login_success" if success else "login_failed",
            payload_json={"username": username, "success": success, "detail": detail},
            user_id=user_id,
            ts=dt.datetime.utcnow(),
        )
    )
    await session.commit()


@router.post("/login", response_model=schemas.Token)
async def login(payload: schemas.LoginRequest, session: AsyncSession = Depends(get_session)) -> schemas.Token:
    result = await session.execute(select(models.User).where(models.User.username == payload.username))
    user = result.scalar_one_or_none()
    if user is None or not auth_utils.verify_password(payload.password, user.password_hash):
        await _register_login_attempt(
            session,
            username=payload.username,
            success=False,
            user_id=None,
            detail="Credenciales inválidas",
        )
        raise api_error(status.HTTP_401_UNAUTHORIZED, "auth.invalid_credentials", "Credenciales inválidas")
    if not user.active:
        await _register_login_attempt(
            session,
            username=payload.username,
            success=False,
            user_id=str(user.id),
            detail="Usuario inactivo",
        )
        raise api_error(status.HTTP_403_FORBIDDEN, "auth.inactive_user", "Usuario inactivo")
    token = auth_utils.create_access_token({"sub": str(user.id), "role": user.role})
    await _register_login_attempt(
        session,
        username=payload.username,
        success=True,
        user_id=str(user.id),
    )
    return schemas.Token(access_token=token)


@router.post("/refresh", response_model=schemas.Token)
async def refresh(user: models.User = Depends(auth_utils.get_current_user)) -> schemas.Token:
    token = auth_utils.create_access_token({"sub": str(user.id), "role": user.role})
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserProfile)
async def me(user: models.User = Depends(auth_utils.get_current_user)) -> schemas.UserProfile:
    return schemas.UserProfile(
        id=user.id,
        username=user.username,
        role=user.role,
        active=user.active,
        created_at=user.created_at,
    )


@router.post("/logout", status_code=204)
async def logout() -> None:  # pragma: no cover - placeholder
    return None

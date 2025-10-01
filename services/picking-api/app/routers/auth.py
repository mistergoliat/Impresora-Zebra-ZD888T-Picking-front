from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import auth as auth_utils
from .. import models, schemas
from ..deps import get_session

router = APIRouter()


def _parse_login_payload(data: Mapping[str, Any]) -> schemas.LoginRequest:
    try:
        return schemas.LoginRequest(**data)
    except ValidationError as exc:  # pragma: no cover - validated in tests
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc


async def _get_login_credentials(request: Request) -> schemas.LoginRequest:
    content_type = request.headers.get("content-type", "").split(";")[0].strip()
    if content_type == "application/json":
        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON inválido",
            ) from exc
        if not isinstance(payload, Mapping):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="JSON inválido",
            )
        return _parse_login_payload(payload)
    form_data = await request.form()
    return _parse_login_payload({
        "username": form_data.get("username"),
        "password": form_data.get("password"),
    })


async def _authenticate_user(
    session: AsyncSession, username: str, password: str
) -> models.User:
    result = await session.execute(select(models.User).where(models.User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not auth_utils.verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo")
    return user


@router.post("/login", response_model=schemas.Token)
async def login(request: Request, session: AsyncSession = Depends(get_session)) -> schemas.Token:
    credentials = await _get_login_credentials(request)
    user = await _authenticate_user(session, credentials.username, credentials.password)
    token = auth_utils.create_access_token({"sub": str(user.id), "role": user.role})
    return schemas.Token(access_token=token)


@router.post("/logout", status_code=204)
async def logout() -> None:  # pragma: no cover - placeholder
    return None

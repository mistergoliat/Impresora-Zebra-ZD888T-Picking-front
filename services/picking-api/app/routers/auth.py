from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import auth as auth_utils
from .. import models, schemas
from ..deps import get_session

router = APIRouter()


@router.post("/login", response_model=schemas.Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)
) -> schemas.Token:
    result = await session.execute(select(models.User).where(models.User.username == form_data.username))
    user = result.scalar_one_or_none()
    if user is None or not auth_utils.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales inválidas")
    if not user.active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo")
    token = auth_utils.create_access_token({"sub": str(user.id), "role": user.role})
    return schemas.Token(access_token=token)


@router.post("/logout", status_code=204)
async def logout() -> None:  # pragma: no cover - placeholder
    return None

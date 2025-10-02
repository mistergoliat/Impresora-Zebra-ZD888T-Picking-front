from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import get_current_user
from ..deps import get_session
from ..rbac import require_role

router = APIRouter()


@router.get("/", response_model=list[schemas.StockEntry])
async def list_stock(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> list[schemas.StockEntry]:
    require_role(user, "operator")
    result = await session.execute(
        select(models.Stock).order_by(models.Stock.location.asc(), models.Stock.item_code.asc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        schemas.StockEntry(
            id=row.id,
            item_code=row.item_code,
            location=row.location,
            lot=row.lot,
            serial=row.serial,
            expiry=row.expiry,
            qty=row.qty,
        )
        for row in rows
    ]

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import get_current_user
from ..deps import get_session
from ..rbac import require_role

router = APIRouter()


@router.get("/", response_model=list[schemas.AuditEntry])
async def list_audit(
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> list[schemas.AuditEntry]:
    require_role(user, "supervisor")
    result = await session.execute(
        select(models.Audit).order_by(models.Audit.ts.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        schemas.AuditEntry(
            id=row.id,
            entity=row.entity,
            entity_id=row.entity_id,
            action=row.action,
            payload_json=row.payload_json,
            user_id=row.user_id,
            ts=row.ts,
        )
        for row in rows
    ]

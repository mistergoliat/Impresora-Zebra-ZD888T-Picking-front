import datetime as dt
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas, zpl
from ..auth import get_current_user
from ..deps import get_session
from ..rbac import require_role

router = APIRouter()

DEFAULT_PRINTER = os.getenv("PRINTER_NAME", "ZDesigner ZD888t")


@router.post("/product", response_model=schemas.PrintJobResponse)
async def enqueue_product_label(
    payload: schemas.PrintProductRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.PrintJobResponse:
    require_role(user, "operator")
    zpl_payload = zpl.render_product_label(
        item_code=payload.item_code,
        item_name=payload.item_name,
        fecha_ingreso=payload.fecha_ingreso.strftime("%d-%m-%Y"),
    )
    job = models.PrintJob(
        printer_name=DEFAULT_PRINTER,
        payload_zpl=zpl_payload,
        copies=payload.copies,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return schemas.PrintJobResponse(
        id=job.id,
        printer_name=job.printer_name,
        status=job.status,
        copies=job.copies,
        payload_zpl=job.payload_zpl,
        attempts=job.attempts,
        last_error=job.last_error,
        created_at=job.created_at,
    )


@router.get("/jobs")
async def get_jobs(
    status: str = Query("queued"),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    require_role(user, "operator")
    result = await session.execute(
        select(models.PrintJob).where(models.PrintJob.status == status).order_by(models.PrintJob.created_at.asc()).limit(limit)
    )
    jobs = result.scalars().all()
    return [
        schemas.PrintJobResponse(
            id=j.id,
            printer_name=j.printer_name,
            status=j.status,
            copies=j.copies,
            payload_zpl=j.payload_zpl,
            attempts=j.attempts,
            last_error=j.last_error,
            created_at=j.created_at,
        )
        for j in jobs
    ]


@router.post("/jobs/{job_id}/ack")
async def ack_job(
    job_id: str,
    payload: schemas.PrintAckRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
):
    require_role(user, "operator")
    result = await session.execute(select(models.PrintJob).where(models.PrintJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Trabajo no encontrado")
    job.status = payload.status
    job.last_error = payload.error
    job.attempts = job.attempts + 1 if payload.status in {"error", "retry"} else job.attempts
    job.updated_at = dt.datetime.utcnow()
    await session.commit()
    return {"status": job.status}

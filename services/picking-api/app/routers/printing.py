import datetime as dt
import os

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas, zpl
from ..auth import get_current_user
from ..deps import get_session
from ..errors import api_error
from ..rbac import require_role

router = APIRouter()

DEFAULT_PRINTER = os.getenv("PRINTER_NAME", "ZDesigner ZD888t")


@router.get("/probe", response_model=schemas.PrintProbeResponse)
async def probe() -> schemas.PrintProbeResponse:
    return schemas.PrintProbeResponse(status="ok", printer_name=DEFAULT_PRINTER)


@router.post("/product", response_model=schemas.PrintJobResponse)
async def enqueue_product_label(
    payload: schemas.PrintProductRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.PrintJobResponse:
    require_role(user, "operator")
    if payload.item_name is None:
        result = await session.execute(select(models.Product).where(models.Product.item_code == payload.item_code))
        product = result.scalar_one_or_none()
        if product is None:
            raise api_error(status.HTTP_404_NOT_FOUND, "product.not_found", "Producto no encontrado")
        item_name = product.item_name
    else:
        item_name = payload.item_name

    fecha = payload.fecha_ingreso or dt.date.today()
    zpl_payload = zpl.render_product_label(
        item_code=payload.item_code,
        item_name=item_name,
        fecha_ingreso=fecha.strftime("%d-%m-%Y"),
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


@router.post("/from-local", response_model=schemas.PrintJobResponse)
async def enqueue_from_local(
    payload: schemas.PrintFromLocalRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.PrintJobResponse:
    require_role(user, "operator")
    printer_name = payload.printer_name or DEFAULT_PRINTER
    job = models.PrintJob(
        printer_name=printer_name,
        payload_zpl=payload.payload_zpl,
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


@router.get("/jobs", response_model=list[schemas.PrintJobResponse])
async def get_jobs(
    status_filter: str = Query("queued"),
    limit: int = Query(25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> list[schemas.PrintJobResponse]:
    require_role(user, "operator")
    result = await session.execute(
        select(models.PrintJob)
        .where(models.PrintJob.status == status_filter)
        .order_by(models.PrintJob.created_at.asc())
        .limit(limit)
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


@router.post("/jobs/{job_id}/ack", response_model=schemas.PrintAckResponse)
async def ack_job(
    job_id: str,
    payload: schemas.PrintAckRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.PrintAckResponse:
    require_role(user, "operator")
    result = await session.execute(select(models.PrintJob).where(models.PrintJob.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "print.job_not_found", "Trabajo no encontrado")
    job.status = payload.status
    job.last_error = payload.error
    job.attempts = job.attempts + 1 if payload.status in {"error", "retry"} else job.attempts
    job.updated_at = dt.datetime.utcnow()
    await session.commit()
    await session.refresh(job)
    return schemas.PrintAckResponse(status=job.status)

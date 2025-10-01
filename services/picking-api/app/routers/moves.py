"""Routers for move operations covering PO/SO/TR/RT flows."""

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import models, schemas
from ..auth import get_current_user
from ..deps import get_session
from ..rbac import require_role

router = APIRouter()


MOVE_TYPE_MAPPING: dict[str, tuple[str, Literal[1, -1]]] = {
    "PO": ("inbound", 1),
    "SO": ("outbound", -1),
    "TR": ("transfer", -1),
    "RT": ("return", 1),
}


def _resolve_move_type(doc_type: str) -> tuple[str, int]:
    try:
        return MOVE_TYPE_MAPPING[doc_type]
    except KeyError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail="Tipo de documento inválido") from exc


async def _ensure_product(session: AsyncSession, item_code: str) -> None:
    result = await session.execute(select(models.Product).where(models.Product.item_code == item_code))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Producto {item_code} no existe")


async def _get_move(session: AsyncSession, move_id: str) -> models.Move:
    result = await session.execute(
        select(models.Move)
        .where(models.Move.id == move_id)
        .options(selectinload(models.Move.lines))
    )
    move = result.scalar_one_or_none()
    if move is None:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")
    return move


def _build_move_response(move: models.Move) -> schemas.MoveResponse:
    return schemas.MoveResponse(
        id=move.id,
        doc_type=move.doc_type,
        doc_number=move.doc_number,
        status=move.status,
        type=move.type,
        created_at=move.created_at,
        updated_at=move.updated_at,
        lines=[
            schemas.MoveLineResponse(
                id=line.id,
                item_code=line.item_code,
                qty=line.qty,
                qty_confirmed=line.qty_confirmed,
                location_from=line.location_from,
                location_to=line.location_to,
            )
            for line in move.lines
        ],
    )


@router.post("/", response_model=schemas.MoveResponse, status_code=status.HTTP_201_CREATED)
async def create_move(
    payload: schemas.MoveCreateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.MoveResponse:
    require_role(user, "operator")
    move_type, _ = _resolve_move_type(payload.doc_type)
    move = models.Move(
        type=move_type,
        doc_type=payload.doc_type,
        doc_number=payload.doc_number,
        status="pending",
        created_by=user.id,
        updated_at=dt.datetime.utcnow(),
    )
    session.add(move)
    session.add(
        models.Audit(
            entity="move",
            entity_id=str(move.id),
            action="created",
            payload_json={
                "doc_type": payload.doc_type,
                "doc_number": payload.doc_number,
                "user_id": str(user.id),
            },
            user_id=user.id,
        )
    )
    await session.commit()
    await session.refresh(move)
    return _build_move_response(move)


@router.get("/{move_id}", response_model=schemas.MoveResponse)
async def get_move(
    move_id: str,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.MoveResponse:
    require_role(user, "operator")
    move = await _get_move(session, move_id)
    return _build_move_response(move)


@router.post("/{move_id}/confirm", response_model=schemas.MoveResponse)
async def confirm_move(
    move_id: str,
    payload: schemas.MoveConfirmRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.MoveResponse:
    require_role(user, "operator")
    move = await _get_move(session, move_id)
    if move.status == "approved":
        raise HTTPException(status_code=400, detail="El movimiento ya fue aprobado")

    move_type, direction = _resolve_move_type(move.doc_type)
    if not payload.lines:
        raise HTTPException(status_code=400, detail="Debes enviar al menos una línea")
    if move.lines:
        raise HTTPException(status_code=409, detail="Las líneas ya fueron registradas para este movimiento")

    confirmed_all = True
    audit_lines: list[dict[str, Any]] = []
    for line_payload in payload.lines:
        await _ensure_product(session, line_payload.item_code)
        qty_confirmed = line_payload.qty_confirmed if line_payload.qty_confirmed is not None else line_payload.qty
        if qty_confirmed > line_payload.qty:
            raise HTTPException(status_code=400, detail="La cantidad confirmada no puede superar la cantidad solicitada")
        if qty_confirmed < line_payload.qty:
            confirmed_all = False

        adjustments: list[dict[str, Any]] = []

        if move.doc_type == "TR":
            if line_payload.location_from == line_payload.location_to:
                raise HTTPException(status_code=400, detail="El origen y destino no pueden ser iguales para una transferencia")

            source_query = select(models.Stock).where(
                models.Stock.item_code == line_payload.item_code,
                models.Stock.location == line_payload.location_from,
            )
            source_result = await session.execute(source_query)
            source_stock = source_result.scalar_one_or_none()
            if source_stock is None or source_stock.qty < qty_confirmed:
                raise HTTPException(status_code=400, detail=f"Stock insuficiente para {line_payload.item_code} en {line_payload.location_from}")
            source_stock.qty -= qty_confirmed
            adjustments.append({"location": line_payload.location_from, "delta": -qty_confirmed})

            dest_query = select(models.Stock).where(
                models.Stock.item_code == line_payload.item_code,
                models.Stock.location == line_payload.location_to,
            )
            dest_result = await session.execute(dest_query)
            dest_stock = dest_result.scalar_one_or_none()
            if dest_stock is None:
                dest_stock = models.Stock(
                    item_code=line_payload.item_code,
                    qty=0,
                    location=line_payload.location_to,
                )
                session.add(dest_stock)
            dest_stock.qty += qty_confirmed
            adjustments.append({"location": line_payload.location_to, "delta": qty_confirmed})
        else:
            target_location = line_payload.location_to if direction > 0 else line_payload.location_from
            stock_query = select(models.Stock).where(
                models.Stock.item_code == line_payload.item_code,
                models.Stock.location == target_location,
            )
            result = await session.execute(stock_query)
            stock = result.scalar_one_or_none()

            if direction > 0:
                if stock is None:
                    stock = models.Stock(item_code=line_payload.item_code, qty=0, location=target_location)
                    session.add(stock)
                stock.qty += qty_confirmed
                adjustments.append({"location": target_location, "delta": qty_confirmed})
            else:
                if stock is None or stock.qty < qty_confirmed:
                    raise HTTPException(status_code=400, detail=f"Stock insuficiente para {line_payload.item_code}")
                stock.qty -= qty_confirmed
                adjustments.append({"location": target_location, "delta": -qty_confirmed})

        session.add(
            models.MoveLine(
                move_id=move.id,
                item_code=line_payload.item_code,
                qty=line_payload.qty,
                qty_confirmed=qty_confirmed,
                location_from=line_payload.location_from,
                location_to=line_payload.location_to,
            )
        )
        audit_lines.append(
            {
                "item_code": line_payload.item_code,
                "qty": line_payload.qty,
                "qty_confirmed": qty_confirmed,
                "location_from": line_payload.location_from,
                "location_to": line_payload.location_to,
                "adjustments": adjustments,
            }
        )

    move.type = move_type
    move.status = "approved" if confirmed_all else "pending"
    move.updated_at = dt.datetime.utcnow()

    session.add(
        models.Audit(
            entity="move",
            entity_id=str(move.id),
            action="confirmed",
            payload_json={
                "lines": audit_lines,
                "user_id": str(user.id),
            },
            user_id=user.id,
        )
    )

    await session.commit()
    refreshed = await _get_move(session, move_id)
    return _build_move_response(refreshed)

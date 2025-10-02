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
    seen_lines: set[tuple[str, str, str]] = set()
    move_lines: list[models.MoveLine] = []
    for line_payload in payload.lines:
        await _ensure_product(session, line_payload.item_code)
        line_key = (
            line_payload.item_code,
            line_payload.location_from,
            line_payload.location_to,
        )
        if line_key in seen_lines:
            raise HTTPException(status_code=400, detail="La línea del producto ya fue agregada")
        seen_lines.add(line_key)
        move_lines.append(
            models.MoveLine(
                item_code=line_payload.item_code,
                qty=line_payload.qty,
                qty_confirmed=0,
                location_from=line_payload.location_from,
                location_to=line_payload.location_to,
            )
        )

    move = models.Move(
        type=move_type,
        doc_type=payload.doc_type,
        doc_number=payload.doc_number,
        status="draft",
        created_by=user.id,
        updated_at=dt.datetime.utcnow(),
    )
    for line in move_lines:
        move.lines.append(line)
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
    refreshed = await _get_move(session, str(move.id))
    return _build_move_response(refreshed)


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
    if not move.lines:
        raise HTTPException(status_code=409, detail="El movimiento no tiene líneas registradas")

    line_index: dict[tuple[str, str, str], models.MoveLine] = {
        (line.item_code, line.location_from, line.location_to): line for line in move.lines
    }

    confirmed_any = False
    audit_lines: list[dict[str, Any]] = []
    for line_payload in payload.lines:
        line_key = (
            line_payload.item_code,
            line_payload.location_from,
            line_payload.location_to,
        )
        line = line_index.get(line_key)
        if line is None:
            raise HTTPException(
                status_code=404,
                detail=f"Producto {line_payload.item_code} no está registrado en el movimiento",
            )

        if line_payload.qty > line.qty:
            raise HTTPException(status_code=400, detail="La cantidad solicitada excede la cantidad registrada")

        qty_to_confirm = (
            line_payload.qty_confirmed
            if line_payload.qty_confirmed is not None
            else line_payload.qty
        )
        if line_payload.qty_confirmed is not None and line_payload.qty_confirmed > line_payload.qty:
            raise HTTPException(status_code=400, detail="La cantidad confirmada no puede superar la cantidad solicitada")
        if qty_to_confirm <= 0:
            raise HTTPException(status_code=400, detail="La cantidad confirmada debe ser mayor a cero")

        pending_qty = line.qty - line.qty_confirmed
        if qty_to_confirm > pending_qty:
            raise HTTPException(status_code=400, detail="La cantidad confirmada excede la cantidad pendiente")

        confirmed_any = True

        target_location = line.location_to if direction > 0 else line.location_from
        stock_query = select(models.Stock).where(
            models.Stock.item_code == line.item_code,
            models.Stock.location == target_location,
        )
        result = await session.execute(stock_query)
        stock = result.scalar_one_or_none()

        if direction > 0:
            if stock is None:
                stock = models.Stock(item_code=line.item_code, qty=0, location=target_location)
                session.add(stock)
            stock.qty += qty_to_confirm
        else:
            if stock is None or stock.qty < qty_to_confirm:
                raise HTTPException(status_code=400, detail=f"Stock insuficiente para {line.item_code}")
            stock.qty -= qty_to_confirm

        line.qty_confirmed += qty_to_confirm

        audit_lines.append(
            {
                "item_code": line.item_code,
                "qty": line_payload.qty,
                "qty_confirmed": qty_to_confirm,
                "qty_confirmed_total": line.qty_confirmed,
                "location_from": line.location_from,
                "location_to": line.location_to,
            }
        )

    if not confirmed_any:
        raise HTTPException(status_code=400, detail="Debes confirmar al menos una cantidad")

    move.type = move_type
    confirmed_all = all(line.qty_confirmed == line.qty for line in move.lines)
    if confirmed_all:
        move.status = "approved"
        move.approved_by = user.id
    else:
        move.status = "pending"
        move.approved_by = None
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

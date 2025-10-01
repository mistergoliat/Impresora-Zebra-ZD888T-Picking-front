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
    existing_lines: dict[tuple[str, str, str], list[models.MoveLine]] = {}
    for line in move.lines:
        key = (line.item_code, line.location_from, line.location_to)
        existing_lines.setdefault(key, []).append(line)

    audit_lines: list[dict[str, Any]] = []
    for line_payload in payload.lines:
        await _ensure_product(session, line_payload.item_code)
        qty_to_confirm = line_payload.qty_confirmed if line_payload.qty_confirmed is not None else line_payload.qty
        if qty_to_confirm > line_payload.qty:
            raise HTTPException(status_code=400, detail="La cantidad confirmada no puede superar la cantidad solicitada")

        key = (line_payload.item_code, line_payload.location_from, line_payload.location_to)
        lines_for_key = existing_lines.get(key, [])
        total_available = sum(max(line.qty - line.qty_confirmed, 0) for line in lines_for_key)

        if total_available > 0:
            if qty_to_confirm > total_available:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "La cantidad confirmada excede la cantidad pendiente para "
                        f"{line_payload.item_code}. Pendiente: {total_available}"
                    ),
                )
            remaining_to_confirm = qty_to_confirm
            for candidate in lines_for_key:
                available = max(candidate.qty - candidate.qty_confirmed, 0)
                if available <= 0:
                    continue
                to_apply = min(available, remaining_to_confirm)
                candidate.qty_confirmed += to_apply
                remaining_to_confirm -= to_apply
                if remaining_to_confirm == 0:
                    break
            if remaining_to_confirm != 0:
                raise HTTPException(status_code=500, detail="No se pudo aplicar la confirmación solicitada")
        else:
            new_line = models.MoveLine(
                move_id=move.id,
                item_code=line_payload.item_code,
                qty=line_payload.qty,
                qty_confirmed=qty_to_confirm,
                location_from=line_payload.location_from,
                location_to=line_payload.location_to,
            )
            session.add(new_line)
            move.lines.append(new_line)
            lines_for_key = existing_lines.setdefault(key, [])
            lines_for_key.append(new_line)

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
            stock.qty += qty_to_confirm
        else:
            if stock is None or stock.qty < qty_to_confirm:
                raise HTTPException(status_code=400, detail=f"Stock insuficiente para {line_payload.item_code}")
            stock.qty -= qty_to_confirm

        total_qty = sum(line.qty for line in lines_for_key)
        total_confirmed = sum(line.qty_confirmed for line in lines_for_key)
        audit_lines.append(
            {
                "item_code": line_payload.item_code,
                "qty": total_qty,
                "qty_confirmed": qty_to_confirm,
                "qty_confirmed_total": total_confirmed,
                "qty_pending_total": max(total_qty - total_confirmed, 0),
                "location_from": line_payload.location_from,
                "location_to": line_payload.location_to,
            }
        )

    move.type = move_type
    move.status = "approved" if move.lines and all(line.qty_confirmed >= line.qty for line in move.lines) else "pending"
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

import datetime as dt
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models, schemas
from ..auth import get_current_user
from ..deps import get_session
from ..errors import api_error
from ..rbac import require_role

router = APIRouter()

ABCXYZ_FILE = "abcxyz_results.xlsx"
DEFAULT_OUTPUT_DIR = os.getenv("ABCXYZ_OUTPUT_DIR", "/data/abcxyz")


async def _upsert_products(session: AsyncSession, items: list[schemas.ProductUpsert]) -> int:
    count = 0
    for item in items:
        payload = item.dict(exclude_none=True)
        payload.setdefault("updated_at", dt.datetime.utcnow())
        stmt = pg_insert(models.Product).values(**payload)
        update_cols = {column: stmt.excluded[column] for column in payload if column != "item_code"}
        update_cols["updated_at"] = dt.datetime.utcnow()
        stmt = stmt.on_conflict_do_update(index_elements=[models.Product.item_code], set_=update_cols)
        await session.execute(stmt)
        count += 1
    await session.commit()
    return count


@router.get("/probe", response_model=schemas.ProbeResponse)
async def probe() -> schemas.ProbeResponse:
    file_path = Path(DEFAULT_OUTPUT_DIR) / ABCXYZ_FILE
    return schemas.ProbeResponse(available=file_path.exists(), path=str(file_path))


@router.post("/", response_model=schemas.ProductImportResult)
async def import_payload(
    payload: schemas.ProductImportRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.ProductImportResult:
    require_role(user, "supervisor")
    if not payload.items:
        raise api_error(status.HTTP_400_BAD_REQUEST, "import.empty", "Debes enviar al menos un producto")
    imported = await _upsert_products(session, payload.items)
    return schemas.ProductImportResult(imported=imported)


@router.post("/from-local", response_model=schemas.ProductImportResult)
async def import_from_local(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_current_user),
) -> schemas.ProductImportResult:
    require_role(user, "supervisor")
    file_path = Path(DEFAULT_OUTPUT_DIR) / ABCXYZ_FILE
    if not file_path.exists():
        raise api_error(status.HTTP_404_NOT_FOUND, "import.file_not_found", "Archivo no encontrado")

    try:
        df = pd.read_excel(file_path)
    except Exception as exc:  # pragma: no cover - depends on pandas engine
        raise api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "import.read_failed", "No se pudo leer el archivo") from exc

    df = df.where(pd.notnull(df), None)
    field_names = list(schemas.ProductUpsert.model_fields.keys())
    items: list[schemas.ProductUpsert] = []
    for record in df.to_dict(orient="records"):
        payload = {name: record.get(name) for name in field_names}
        if not payload.get("item_code") or not payload.get("item_name"):
            continue
        items.append(schemas.ProductUpsert(**payload))

    if not items:
        raise api_error(status.HTTP_400_BAD_REQUEST, "import.empty_file", "El archivo no contiene registros válidos")

    imported = await _upsert_products(session, items)
    return schemas.ProductImportResult(imported=imported)

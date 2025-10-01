import datetime as dt
import pathlib
import sys
import uuid

import pytest
from pydantic import ValidationError

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app import models, schemas  # noqa: E402
from app.routers import moves  # noqa: E402


def test_move_create_request_requires_lines() -> None:
    with pytest.raises(ValidationError):
        schemas.MoveCreateRequest(doc_type="PO", doc_number="123", lines=[])


def test_build_move_response_includes_lines() -> None:
    now = dt.datetime.utcnow()
    move = models.Move(
        id=uuid.uuid4(),
        type="inbound",
        doc_type="PO",
        doc_number="PO-123",
        status="draft",
        created_by=uuid.uuid4(),
        created_at=now,
        updated_at=now,
    )
    line = models.MoveLine(
        id=uuid.uuid4(),
        item_code="ITEM-1",
        qty=5,
        qty_confirmed=0,
        location_from="A1",
        location_to="B1",
    )
    line.move = move

    response = moves._build_move_response(move)

    assert response.status == "draft"
    assert len(response.lines) == 1
    response_line = response.lines[0]
    assert response_line.item_code == "ITEM-1"
    assert response_line.qty == 5
    assert response_line.qty_confirmed == 0
    assert response_line.location_from == "A1"
    assert response_line.location_to == "B1"

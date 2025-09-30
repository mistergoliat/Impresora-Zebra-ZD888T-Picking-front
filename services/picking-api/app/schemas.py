import datetime as dt
import uuid
from typing import Optional

from pydantic import BaseModel, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    username: str
    password: str


class ProductImportResult(BaseModel):
    imported: int


class ProbeResponse(BaseModel):
    available: bool
    path: str | None = None


class DocScanRequest(BaseModel):
    scan: str


class DocScanResponse(BaseModel):
    doc_type: str
    doc_number: str


class PrintProductRequest(BaseModel):
    item_code: str
    item_name: Optional[str] = None
    fecha_ingreso: dt.date | None = None
    copies: int = Field(ge=1, le=10, default=1)


class PrintJobResponse(BaseModel):
    id: uuid.UUID
    printer_name: str
    status: str
    copies: int
    payload_zpl: str
    attempts: int
    last_error: Optional[str]
    created_at: dt.datetime


class PrintAckRequest(BaseModel):
    status: str
    error: Optional[str] = None


class MoveCreateRequest(BaseModel):
    doc_type: str = Field(regex="^(PO|SO|TR|RT)$")
    doc_number: str = Field(min_length=1, max_length=64)


class MoveLineInput(BaseModel):
    item_code: str
    qty: int = Field(gt=0)
    qty_confirmed: Optional[int] = Field(default=None, ge=0)
    location_from: str = Field(default="MAIN", max_length=64)
    location_to: str = Field(default="MAIN", max_length=64)


class MoveConfirmRequest(BaseModel):
    lines: list[MoveLineInput]


class MoveLineResponse(BaseModel):
    id: uuid.UUID
    item_code: str
    qty: int
    qty_confirmed: int
    location_from: str
    location_to: str


class MoveResponse(BaseModel):
    id: uuid.UUID
    doc_type: str
    doc_number: str
    status: str
    type: str
    created_at: dt.datetime
    updated_at: dt.datetime
    lines: list[MoveLineResponse] = Field(default_factory=list)

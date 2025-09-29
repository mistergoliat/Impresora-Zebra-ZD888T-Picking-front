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
    item_name: str
    fecha_ingreso: dt.date
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

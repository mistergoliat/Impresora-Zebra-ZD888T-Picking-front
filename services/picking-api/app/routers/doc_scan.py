from fastapi import APIRouter, status

from .. import schemas
from ..barcodes import BarcodeError, parse_hid_scan
from ..errors import api_error

router = APIRouter()


@router.post("/scan", response_model=schemas.DocScanResponse)
async def scan_document(payload: schemas.DocScanRequest) -> schemas.DocScanResponse:
    try:
        data = parse_hid_scan(payload.scan)
    except BarcodeError as exc:
        raise api_error(status.HTTP_400_BAD_REQUEST, "doc.invalid_scan", str(exc)) from exc
    return schemas.DocScanResponse(**data)

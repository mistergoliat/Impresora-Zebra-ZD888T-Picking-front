"""FastAPI application entrypoint for the Picking API."""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .deps import engine
from .models import Base
from .routers import audit, auth, doc_scan, import_abcxyz, moves, printing, stock

logger = logging.getLogger("picking-api")

app = FastAPI(title="Picking API", version="0.1.0")

cors_origins_env = os.getenv(
    "PICKING_API_CORS_ORIGINS",
    "http://localhost:8080,http://localhost:8000,http://ui:8000",
)
allow_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _create_tables() -> None:
    """Ensure the database schema exists before serving requests."""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    logger.info("Database schema ensured")


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:  # pragma: no cover - integration glue
    detail = exc.detail
    if isinstance(detail, dict):
        payload: dict[str, Any] = {
            "detail": str(detail.get("detail", "Error interno")),
            "code": str(detail.get("code", f"http.{exc.status_code}")),
        }
    elif isinstance(detail, str):
        payload = {"detail": detail, "code": f"http.{exc.status_code}"}
    else:
        payload = {"detail": "Error inesperado", "code": "http.unexpected"}
    if exc.headers:
        return JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:  # pragma: no cover - integration glue
    payload = {"detail": "Error de validación", "code": "validation_error", "errors": exc.errors()}
    return JSONResponse(status_code=422, content=payload)


app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(import_abcxyz.router, prefix="/import/abcxyz", tags=["abcxyz"])
app.include_router(doc_scan.router, prefix="/doc", tags=["doc"])
app.include_router(moves.router, prefix="/moves", tags=["moves"])
app.include_router(printing.router, prefix="/print", tags=["print"])
app.include_router(stock.router, prefix="/stock", tags=["stock"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

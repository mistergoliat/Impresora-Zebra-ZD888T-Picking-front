from fastapi import FastAPI

from .routers import auth, import_abcxyz, doc_scan, moves, printing, stock, audit

app = FastAPI(title="Picking API", version="0.1.0")

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(import_abcxyz.router, prefix="/import/abcxyz", tags=["abcxyz"])
app.include_router(doc_scan.router, prefix="/doc", tags=["doc"])
app.include_router(moves.router, prefix="/moves", tags=["moves"])
app.include_router(printing.router, prefix="/print", tags=["print"])
app.include_router(stock.router, prefix="/stock", tags=["stock"])
app.include_router(audit.router, prefix="/audit", tags=["audit"])


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}

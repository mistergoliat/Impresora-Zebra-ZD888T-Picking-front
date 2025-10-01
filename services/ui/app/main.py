import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
API_BASE_URL = os.getenv("PICKING_API_URL", "http://picking-api:8000")
API_TIMEOUT = float(os.getenv("PICKING_API_TIMEOUT", "10"))

app = FastAPI(title="Picking UI", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


OPERATIONS = [
    {
        "slug": "po",
        "doc_type": "PO",
        "name": "Entrada (PO)",
        "description": "Registra el ingreso de mercadería al inventario y actualiza existencias.",
        "cta": "Crear entrada",
        "href": "/moves/new?type=PO",
        "status": "Disponible",
    },
    {
        "slug": "so",
        "doc_type": "SO",
        "name": "Salida (SO)",
        "description": "Confirma pedidos de salida y descuenta stock en tiempo real.",
        "cta": "Crear salida",
        "href": "/moves/new?type=SO",
        "status": "Disponible",
    },
    {
        "slug": "tr",
        "doc_type": "TR",
        "name": "Traslado (TR)",
        "description": "Gestiona traslados entre ubicaciones manteniendo trazabilidad de los movimientos.",
        "cta": "Crear traslado",
        "href": "/moves/new?type=TR",
        "status": "Disponible",
    },
    {
        "slug": "rt",
        "doc_type": "RT",
        "name": "Devolución (RT)",
        "description": "Procesa devoluciones de clientes y reincorpora los productos al stock.",
        "cta": "Crear devolución",
        "href": "/moves/new?type=RT",
        "status": "Disponible",
    },
]


async def _api_request(method: str, path: str, token: str | None, **kwargs: Any) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=API_TIMEOUT) as client:
        response = await client.request(method, path, headers=headers, **kwargs)
    return response


def _require_token(request: Request) -> str | None:
    token = request.cookies.get("auth_token")
    if not token:
        return None
    return token


def _safe_detail(response: httpx.Response, default: str) -> str:
    try:
        data = response.json()
    except ValueError:
        return default
    detail = data.get("detail") if isinstance(data, dict) else None
    return detail if isinstance(detail, str) else default


def _dashboard_context(request: Request) -> dict:
    return {
        "request": request,
        "operations": OPERATIONS,
        "username": request.cookies.get("username"),
    }


@app.get("/", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request):
    if _require_token(request) is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse("dashboard.html", _dashboard_context(request))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_alias(request: Request):
    return await dashboard(request)


@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "form_error": None,
            "username": request.cookies.get("username", ""),
        },
    )


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not username or not password:
        context = {
            "request": request,
            "form_error": "Completa usuario y contraseña para continuar.",
            "username": username,
        }
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_400_BAD_REQUEST)

    try:
        api_response = await _api_request(
            "POST",
            "/auth/login",
            token=None,
            data={"username": username, "password": password},
        )
    except httpx.RequestError:
        context = {
            "request": request,
            "form_error": "No se pudo contactar la API de picking.",
            "username": username,
        }
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_502_BAD_GATEWAY)

    if api_response.status_code != 200:
        default_message = "Credenciales inválidas" if api_response.status_code in {400, 401} else "Error autenticando"
        message = _safe_detail(api_response, default_message)
        context = {
            "request": request,
            "form_error": message,
            "username": username,
        }
        return templates.TemplateResponse("login.html", context, status_code=status.HTTP_401_UNAUTHORIZED)

    token = api_response.json().get("access_token")
    if not token:
        raise HTTPException(status_code=500, detail="Token inválido devuelto por la API")

    response = RedirectResponse(url=request.url_for("dashboard"), status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie("auth_token", token, httponly=True, samesite="lax")
    response.set_cookie("username", username, samesite="lax")
    return response


@app.get("/moves/new", response_class=HTMLResponse)
async def moves_new(request: Request):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)
    selected_type = request.query_params.get("type")
    selected = next((op for op in OPERATIONS if op["doc_type"] == selected_type), None)
    context = {
        "request": request,
        "operations": OPERATIONS,
        "selected": selected,
        "form_error": None,
        "doc_number": "",
    }
    return templates.TemplateResponse("moves_new.html", context)


@app.post("/moves/new")
async def moves_create(
    request: Request,
    doc_type: str = Form(...),
    doc_number: str = Form(...),
):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)

    payload = {"doc_type": doc_type, "doc_number": doc_number}
    api_response = await _api_request("POST", "/moves", token, json=payload)
    if api_response.status_code != status.HTTP_201_CREATED:
        selected = next((op for op in OPERATIONS if op["doc_type"] == doc_type), None)
        context = {
            "request": request,
            "operations": OPERATIONS,
            "selected": selected,
            "form_error": _safe_detail(api_response, "No se pudo crear el movimiento"),
            "doc_number": doc_number,
        }
        return templates.TemplateResponse("moves_new.html", context, status_code=api_response.status_code)

    move = api_response.json()
    return RedirectResponse(
        url=request.url_for("move_detail", move_id=move["id"]),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/moves/{move_id}", response_class=HTMLResponse, name="move_detail")
async def move_detail(request: Request, move_id: str):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)

    api_response = await _api_request("GET", f"/moves/{move_id}", token)
    if api_response.status_code == 404:
        context = {
            "request": request,
            "move": None,
            "error": "Movimiento no encontrado",
        }
        return templates.TemplateResponse("move_detail.html", context, status_code=404)
    if api_response.status_code != 200:
        context = {
            "request": request,
            "move": None,
            "error": "No se pudo cargar el movimiento",
        }
        return templates.TemplateResponse("move_detail.html", context, status_code=api_response.status_code)

    move = api_response.json()
    context = {
        "request": request,
        "move": move,
        "error": None,
        "success_message": request.query_params.get("success"),
    }
    return templates.TemplateResponse("move_detail.html", context)


@app.post("/moves/{move_id}/confirm")
async def move_confirm(request: Request, move_id: str):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)

    move_response = await _api_request("GET", f"/moves/{move_id}", token)
    if move_response.status_code != 200:
        return templates.TemplateResponse(
            "move_detail.html",
            {
                "request": request,
                "move": None,
                "error": "Movimiento no encontrado",
            },
            status_code=move_response.status_code,
        )
    move_payload = move_response.json() if move_response.status_code == 200 else None

    form = await request.form()
    item_codes = form.getlist("item_code")
    qtys = form.getlist("qty")
    qty_confirmeds = form.getlist("qty_confirmed")

    lines: list[dict[str, Any]] = []
    for idx, code in enumerate(item_codes):
        code = code.strip()
        if not code:
            continue
        try:
            qty = int(qtys[idx])
            qty_confirmed = int(qty_confirmeds[idx]) if qty_confirmeds[idx] else qty
        except (ValueError, IndexError):
            qty = None  # type: ignore[assignment]
            qty_confirmed = 0
        if qty is None or qty <= 0:
            error_context = {
                "request": request,
                "move": move_payload,
                "error": "Las cantidades deben ser enteros positivos.",
            }
            return templates.TemplateResponse("move_detail.html", error_context, status_code=400)
        line_payload = {
            "item_code": code,
            "qty": qty,
            "qty_confirmed": max(0, min(qty_confirmed, qty)),
            "location_from": form.get("location_from", "MAIN"),
            "location_to": form.get("location_to", "MAIN"),
        }
        lines.append(line_payload)

    if not lines:
        context = {
            "request": request,
            "move": move_payload,
            "error": "Agrega al menos una línea antes de confirmar.",
        }
        return templates.TemplateResponse("move_detail.html", context, status_code=400)

    api_response = await _api_request("POST", f"/moves/{move_id}/confirm", token, json={"lines": lines})
    if api_response.status_code != 200:
        context = {
            "request": request,
            "move": move_payload,
            "error": _safe_detail(api_response, "No se pudo confirmar el movimiento"),
        }
        return templates.TemplateResponse("move_detail.html", context, status_code=api_response.status_code)

    return RedirectResponse(
        url=f"{request.url_for('move_detail', move_id=move_id)}?success=Movimiento%20confirmado",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/print", response_class=HTMLResponse)
async def print_labels(request: Request):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)

    jobs_response = await _api_request("GET", "/print/jobs", token)
    jobs = jobs_response.json() if jobs_response.status_code == 200 else []
    context = {
        "request": request,
        "jobs": jobs,
        "error": None,
        "success": request.query_params.get("success"),
    }
    return templates.TemplateResponse("print_labels.html", context)


@app.post("/print")
async def print_labels_submit(request: Request, codes: str = Form(...), copies: int = Form(1)):
    token = _require_token(request)
    if token is None:
        return RedirectResponse(url=request.url_for("login"), status_code=status.HTTP_303_SEE_OTHER)

    if copies < 1:
        copies = 1
    if copies > 10:
        copies = 10

    parsed_codes = [line.strip() for line in codes.splitlines() if line.strip()]
    if not parsed_codes:
        jobs_response = await _api_request("GET", "/print/jobs", token)
        context = {
            "request": request,
            "jobs": jobs_response.json() if jobs_response.status_code == 200 else [],
            "error": "Ingresa al menos un código de producto.",
        }
        return templates.TemplateResponse("print_labels.html", context, status_code=400)

    failures: list[str] = []
    for code in parsed_codes:
        response = await _api_request(
            "POST",
            "/print/product",
            token,
            json={"item_code": code, "copies": copies},
        )
        if response.status_code not in {200, 201}:
            detail = _safe_detail(response, "Error al encolar impresión")
            failures.append(f"{code}: {detail}")

    if failures:
        jobs_response = await _api_request("GET", "/print/jobs", token)
        context = {
            "request": request,
            "jobs": jobs_response.json() if jobs_response.status_code == 200 else [],
            "error": "\n".join(failures),
        }
        return templates.TemplateResponse("print_labels.html", context, status_code=400)

    return RedirectResponse(
        url=f"{request.url_for('print_labels')}?success=Etiquetas%20encoladas",
        status_code=status.HTTP_303_SEE_OTHER,
    )

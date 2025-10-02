# Picking App Overview

Este documento resume los componentes principales de la solución de picking basada en FastAPI, Postgres y una interfaz HTMX/Jinja.

## Servicios

- **picking-api**: Servicio FastAPI que maneja autenticación JWT, movimientos de inventario, importación ABC–XYZ y cola de impresión.
- **ui**: Frontend FastAPI + Jinja2 que consume la API utilizando `PICKING_API_URL` y muestra el estado del backend en la cabecera.
- **db**: Postgres 15 inicializado con `db/init.sql`, incluye usuario admin (contraseña `admin`).
- **print-agent**: Cliente Windows que consume `/print/jobs` y envía ZPL a la Zebra ZD888t.

## Puesta en marcha con Docker Compose

1. Copia el archivo de ejemplo y ajusta los valores necesarios:

   ```bash
   cp ops/.env.example ops/.env
   ```

2. Levanta la solución completa:

   ```bash
   docker compose --env-file ops/.env -f ops/docker-compose.yml up --build
   ```

3. Accede a la UI en `http://localhost:8000` e inicia sesión con `admin`/`admin`.

El contenedor `picking-api` queda expuesto en `http://localhost:8001`. El badge en la UI consulta `/health` de la API para verificar conectividad.

## Ejecución local sin Docker

1. Inicia Postgres (puedes reutilizar el contenedor):

   ```bash
   docker run --rm -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app -e POSTGRES_DB=picking \
     -p 5432:5432 -v $(pwd)/db/init.sql:/docker-entrypoint-initdb.d/init.sql postgres:15
   ```

2. Exporta variables mínimas:

   ```bash
   export DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/picking
   export JWT_SECRET=change_me
   ```

3. Inicia la API:

   ```bash
   uvicorn services.picking-api.app.main:app --reload --port 8001
   ```

4. Inicia la UI apuntando al backend local:

   ```bash
   PICKING_API_URL=http://localhost:8001 uvicorn services.ui.app.main:app --reload --port 8000
   ```

## Importación ABC–XYZ

- El directorio `samples/abcxyz/` se monta como `/data/abcxyz` en el servicio `picking-api` dentro de Docker.
- Usa `POST /import/abcxyz/from-local` para leer el archivo Excel `abcxyz_results.xlsx`.
- Alternativamente, envía datos JSON a `POST /import/abcxyz` para realizar _upsert_ de productos.

## Colección Postman

En `postman/` encontrarás `Picking.postman_collection.json` y `Picking.postman_environment.json`. La colección cubre los flujos de autenticación, movimientos, impresión y escaneo de documentos; incluye scripts para guardar el token JWT.

## Seguridad y auditoría

- Autenticación JWT con expiración configurable (`JWT_EXP_HOURS`).
- Auditoría centralizada (`audit`) para login, creación y confirmación de movimientos.
- Control de acceso basado en roles (`operator`, `supervisor`, `admin`).

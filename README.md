# Simusol — visor comparativo de sólidos geológicos

Aplicación web para comparar dos periodos de modelos 3D de sólidos geológicos (`.obj`): carga progresiva por periodo, correspondencia por nombre, control de calidad de las mallas, visor 3D superpuesto y plantilla CSV de orientación de referencia.

Estado: **prototipo** en revisión con el área usuaria. Las métricas de cambio (volumen, IoU, clasificación) todavía no están implementadas: dependen de una política sobre mallas con orientación invertida que se debe acordar primero.

## Qué incluye

| Parte | Ubicación | Tecnología |
|---|---|---|
| API y motor geométrico | `backend/` | Python 3.12, FastAPI, trimesh, PyMeshLab, SQLite |
| Interfaz web | `web/` | React, TypeScript, Vite, Three.js |
| Despliegue | `compose.yaml`, `deploy/` | Docker, GitHub Actions, GHCR |

Principios: los archivos originales nunca se modifican ni se reparan; un valor que no se pudo calcular se informa como no disponible, nunca como cero; el consumo de memoria está acotado (una malla a la vez, revisión en un proceso aislado).

## Ejecutar en local

```bash
docker compose up --build        # http://127.0.0.1:8088
```

Sin Docker:

```bash
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
SOLIDS_DATA_DIR=./data .venv/bin/uvicorn solids.api.main:app --app-dir src --port 8000
cd web && npm ci && npm run dev  # http://localhost:5173 (proxy /api -> :8000)
```

## Pruebas

```bash
docker build --target test backend   # pytest dentro de la imagen
docker build --target test web       # tsc + vitest
```

Las pruebas con muestras reales se omiten si no existe `docs/Pruebas/` (datos del cliente, fuera del repositorio).

## Publicación y despliegue

1. Cada `push` a `main` ejecuta las pruebas y publica `ghcr.io/<usuario>/simusol-api` y `simusol-web` con las etiquetas `latest` y `sha-<commit>`.
2. En el servidor, `deploy/deploy.sh` descarga las imágenes y recrea los contenedores; no se compila nada allí.
3. Reversión: `TAG=sha-1a2b3c4 ./deploy.sh`.

Copie `deploy/.env.example` a `.env` en el servidor y cree una vez la red del proxy: `docker network create simusol-proxy`.

## Datos y confidencialidad

Los modelos de los clientes (`docs/Pruebas/`, `*.rmproj`) y la documentación interna no se versionan. Los resultados de cada ejecución se guardan en el volumen `/data` del contenedor.

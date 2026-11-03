# syntax=docker/dockerfile:1
# Layers are ordered so that a code change rebuilds only the last small layer:
# system libraries and Python dependencies are cached until pyproject.toml changes.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# PyMeshLab links against OpenGL/Qt system libraries that the slim image does not ship.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxkbcommon0 libfontconfig1 libdbus-1-3 libcom-err2 libp11-kit0 libgpg-error0 \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt

# `docker build --target test backend` runs the test suite inside the same image the app runs in.
FROM base AS test
RUN pip install pytest==9.2.0 httpx==0.28.1
COPY src ./src
COPY tests ./tests
RUN python -m pytest -q -rf --tb=short

FROM base AS runtime
ENV SOLIDS_DATA_DIR=/data
COPY src ./src
RUN pip install --no-deps . && useradd --system --uid 10001 solids && mkdir -p /data && chown solids /data
USER solids
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/datasets', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "solids.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

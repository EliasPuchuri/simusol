"""ASGI entry point: ``uvicorn solids.api.main:app``."""

import os
from pathlib import Path

from .app import DEFAULT_MAX_FILE_BYTES, create_app

app = create_app(
    Path(os.environ.get("SOLIDS_DATA_DIR", "data")),
    max_file_bytes=int(os.environ.get("SOLIDS_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES)),
)

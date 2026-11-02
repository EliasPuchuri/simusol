"""HTTP API: model registry, progressive OBJ upload, inventory and matching."""

from __future__ import annotations

import hashlib
import re
import threading
import uuid
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from solids.domain.inventory import Inventory, InventoryEntry
from solids.domain.matching import match_inventories
from solids.geometry.scene import common_origin, export_glb, load_obj, to_scene_coordinates
from solids.domain.naming import normalize_key
from solids.domain.orientation_reference import Issue, parse_orientation_reference, template_csv
from solids.domain.orientation_compare import compare_orientation
from solids.exports.characterization_csv import characterization_csv
from solids.exports.qc_csv import qc_csv
from solids.geometry import characterization as char_mod
from solids.geometry.qc import QC_VERSION, failed_result as qc_failed_result
from solids.infrastructure.catalog import Catalog, Conflict, Invalid, NotFound
from solids.infrastructure.qc_runner import DEFAULT_TARGET, DEFAULT_TIMEOUT
from solids.infrastructure.analysis_service import AnalysisService
from solids.infrastructure.obj_probe import ObjProbe

CHUNK = 1024 * 1024
DEFAULT_MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_BYTES = 1024 * 1024
ASSET_NAME = re.compile(r"^[0-9a-f]{64}_-?\d+_-?\d+_-?\d+\.glb$")


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    period_label: str = Field(min_length=1, max_length=100)
    period_kind: Literal["annual", "monthly"]
    is_demo: bool = False
    spatial_reference: str | None = None
    units: str | None = None


def _safe_filename(raw: str | None) -> str:
    name = PurePosixPath((raw or "").replace("\\", "/")).name
    return name


def _inventory_payload(inventory: Inventory, period: str) -> dict:
    return {
        "incidents": [asdict(i) for i in inventory.duplicate_incidents(period)],
        "counts": {"files": len(inventory.entries), "keys": len(inventory.by_key())},
    }


def _issues(issues: tuple[Issue, ...]) -> list[dict]:
    return [asdict(i) for i in issues]


def create_app(data_dir: Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES, qc_target: str = DEFAULT_TARGET,
               qc_timeout: float = DEFAULT_TIMEOUT,
               char_target: str = "solids.geometry.characterization:characterize_mesh",
               char_timeout: float = DEFAULT_TIMEOUT) -> FastAPI:
    data_dir = Path(data_dir)
    files_dir = data_dir / "originals"
    files_dir.mkdir(parents=True, exist_ok=True)
    derived_dir = data_dir / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    # Geometry work is bounded: one scene is prepared at a time so memory stays predictable on a shared host.
    scene_slot = threading.Semaphore(1)
    catalog = Catalog(data_dir / "catalog.sqlite3")
    catalog.interrupt_stale_runs()  # a run cannot survive a restart: report it instead of leaving it 'running'
    heavy_slot = threading.Lock()  # QC and characterization never run at the same time
    qc = AnalysisService(catalog, files_dir, kind="qc", target=qc_target, version=QC_VERSION,
                         timeout=qc_timeout, failure=qc_failed_result, slot=heavy_slot)
    characterization = AnalysisService(catalog, files_dir, kind="characterization", target=char_target,
                                       version=char_mod.CHAR_VERSION, timeout=char_timeout,
                                       failure=char_mod.failed_result, slot=heavy_slot)
    router = APIRouter(prefix="/api/v1")

    def dataset_or_404(dataset_id: str) -> dict:
        try:
            return catalog.get_dataset(dataset_id)
        except NotFound:
            raise HTTPException(404, "dataset not found") from None

    @router.post("/datasets", status_code=201)
    def create_dataset(body: DatasetCreate) -> dict:
        return catalog.create_dataset(**body.model_dump())

    @router.get("/datasets")
    def list_datasets() -> list[dict]:
        return catalog.list_datasets()

    @router.get("/datasets/{dataset_id}")
    def get_dataset(dataset_id: str) -> dict:
        dataset = dataset_or_404(dataset_id)
        inventory = catalog.inventory(dataset_id)
        return {
            **dataset,
            "files": [asdict(e) for e in inventory.entries],
            "orientation_reference_count": len(catalog.orientation_reference(dataset_id)),
            **_inventory_payload(inventory, dataset["period_label"]),
        }

    @router.post("/datasets/{dataset_id}/files", status_code=201)
    async def upload_file(dataset_id: str, file: UploadFile) -> dict:
        dataset = dataset_or_404(dataset_id)
        if dataset["state"] != "open":
            raise HTTPException(409, "dataset is closed; create another revision to change it")
        filename = _safe_filename(file.filename)
        if not filename.lower().endswith(".obj"):
            raise HTTPException(422, "only .obj files are accepted")

        stored_name = uuid.uuid4().hex + ".obj"
        target = files_dir / stored_name
        digest, probe, size = hashlib.sha256(), ObjProbe(), 0
        try:
            with target.open("wb") as out:
                while chunk := await file.read(CHUNK):
                    size += len(chunk)
                    if size > max_file_bytes:
                        raise HTTPException(413, f"file exceeds {max_file_bytes} bytes")
                    digest.update(chunk)
                    probe.feed(chunk)
                    out.write(chunk)
            probe.finish()
            if size == 0 or not probe.is_obj:
                raise HTTPException(422, "content is not a valid OBJ (needs vertices and faces)")
            entry = InventoryEntry(filename, normalize_key(filename), digest.hexdigest(), size)
            try:
                catalog.add_file(dataset_id, entry, stored_name)
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return asdict(entry)

    @router.post("/datasets/{dataset_id}/finalize")
    def finalize(dataset_id: str) -> dict:
        dataset_or_404(dataset_id)
        try:
            return catalog.close_dataset(dataset_id)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except Invalid as exc:
            raise HTTPException(422, str(exc)) from None

    @router.get("/templates/orientation-reference")
    def orientation_template() -> Response:
        return Response(
            template_csv(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="plantilla_orientacion_referencia.csv"'},
        )

    @router.get("/datasets/{dataset_id}/orientation-reference")
    def get_orientation_reference(dataset_id: str) -> dict:
        dataset_or_404(dataset_id)
        rows = catalog.orientation_reference(dataset_id)
        return {"count": len(rows), "rows": rows}

    @router.post("/datasets/{dataset_id}/orientation-reference")
    async def upload_orientation_reference(dataset_id: str, file: UploadFile) -> dict:
        dataset_or_404(dataset_id)
        raw = await file.read(MAX_REFERENCE_BYTES + 1)
        if len(raw) > MAX_REFERENCE_BYTES:
            raise HTTPException(413, "reference table exceeds 1 MiB")
        known = {e.key for e in catalog.inventory(dataset_id).entries}
        report = parse_orientation_reference(raw, known)
        if report.errors:
            raise HTTPException(
                422,
                {"errors": _issues(report.errors), "warnings": _issues(report.warnings),
                 "ignored_examples": report.ignored_examples},
            )
        catalog.replace_orientation_reference(dataset_id, list(report.rows))
        return {"saved": len(report.rows), "ignored_examples": report.ignored_examples,
                "warnings": _issues(report.warnings)}

    @router.get("/scene")
    def scene(previous: str, current: str, key: str) -> dict:
        """Manifest of the 3D scene of one solid: one layer per period, one shared origin."""
        if previous == current:
            raise HTTPException(422, "previous and current must be different revisions")
        dataset_or_404(previous)
        dataset_or_404(current)
        sources: list[tuple[str, dict]] = []
        for role, dataset_id in (("previous", previous), ("current", current)):
            found = catalog.files_by_key(dataset_id, key)
            if len(found) > 1:
                raise HTTPException(409, f"several files share the key '{key}'; resolve it before viewing")
            if found:
                sources.append((role, found[0]))
        if not sources:
            raise HTTPException(404, "the solid is not in either period")

        with scene_slot:
            return _build_scene(key, sources)

    def _build_scene(key: str, sources: list[tuple[str, dict]]) -> dict:
        # Pass 1: bounds only, one mesh in memory at a time.
        bounds, failures = [], {}
        for role, src in sources:
            try:
                vertices, _ = load_obj(files_dir / src["stored_name"])
                bounds.append((vertices.min(axis=0), vertices.max(axis=0)))
            except Exception as exc:  # a bad mesh must not hide the other layer
                failures[role] = str(exc) or exc.__class__.__name__
        origin = None
        if bounds:
            origin = tuple(round(v, 3) for v in common_origin(bounds))

        layers = []
        for role, src in sources:
            layer = {"role": role, "filename": src["filename"]}
            if role in failures:
                layers.append({**layer, "status": "failed", "reason": failures[role]})
                continue
            tag = "_".join(str(round(v * 1000)) for v in origin)
            asset = f"{src['sha256']}_{tag}.glb"
            try:
                vertices, faces = load_obj(files_dir / src["stored_name"])
                target = derived_dir / asset
                if not target.exists():
                    export_glb(to_scene_coordinates(vertices, origin), faces, target)
                layers.append({**layer, "status": "ok", "url": f"/api/v1/scene/assets/{asset}",
                               "vertices": int(len(vertices)), "triangles": int(len(faces))})
            except Exception as exc:
                layers.append({**layer, "status": "failed", "reason": str(exc) or exc.__class__.__name__})
        return {
            "key": key,
            "origin": None if origin is None else {"east": origin[0], "north": origin[1], "elevation": origin[2]},
            "axes": "y_up: x=East, y=Elevation, z=-North",
            "layers": layers,
        }

    @router.get("/scene/assets/{name}")
    def scene_asset(name: str) -> FileResponse:
        path = derived_dir / name
        if not ASSET_NAME.fullmatch(name) or not path.is_file():
            raise HTTPException(404, "asset not found")
        return FileResponse(path, media_type="model/gltf-binary")

    def qc_rows(dataset_id: str) -> list[dict]:
        rows = []
        for entry in catalog.files(dataset_id):
            rows.append({**{k: entry[k] for k in ("filename", "key", "sha256", "size_bytes")},
                         "result": catalog.get_qc_cached(entry["sha256"], QC_VERSION)})
        return rows

    @router.post("/datasets/{dataset_id}/qc", status_code=202)
    def start_qc(dataset_id: str, response: Response) -> dict:
        dataset_or_404(dataset_id)
        if not catalog.files(dataset_id):
            raise HTTPException(422, "the period has no files to review")
        run, created = qc.submit(dataset_id)
        response.status_code = 202 if created else 200
        return run

    @router.get("/datasets/{dataset_id}/qc")
    def get_qc(dataset_id: str) -> dict:
        dataset_or_404(dataset_id)
        results, summary = [], {"ok": 0, "with_issues": 0, "failed": 0, "pending": 0}
        for row in qc_rows(dataset_id):
            result = row["result"]
            status = result["status"] if result else "pending"
            summary[status] += 1
            results.append({"filename": row["filename"], "key": row["key"], "size_bytes": row["size_bytes"],
                            **(result or {"problems": [], "error": None}), "status": status})
        return {"run": catalog.latest_qc_run(dataset_id), "summary": summary, "results": results}

    @router.get("/datasets/{dataset_id}/qc.csv")
    def get_qc_csv(dataset_id: str) -> Response:
        dataset = dataset_or_404(dataset_id)
        return Response(
            qc_csv(dataset["period_label"], qc_rows(dataset_id)),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="reporte_parte0.csv"'},
        )

    def characterization_rows(dataset_id: str) -> list[dict]:
        references = {r["key"]: r for r in catalog.orientation_reference(dataset_id)}
        rows = []
        for entry in catalog.files(dataset_id):
            result = catalog.get_cached("characterization", entry["sha256"], char_mod.CHAR_VERSION)
            qc_result = catalog.get_qc_cached(entry["sha256"], QC_VERSION)
            volume = (qc_result or {}).get("volume_m3") or {"value": None, "reason": "qc_pendiente"}
            ref = references.get(entry["key"])
            reference = None
            if ref:
                reference = {k: ref[k] for k in ("filename", "orientation_type", "azimuth", "dip", "method", "observations")}
                reference["comparison"] = (
                    compare_orientation(result["orientation"], {"type": ref["orientation_type"], "azimuth": ref["azimuth"], "dip": ref["dip"]})
                    if result and result.get("status") == "ok" else {"comparable": False, "reason": "not_characterized"}
                )
            rows.append({**{k: entry[k] for k in ("filename", "key", "sha256", "size_bytes")},
                         "result": result, "volume": volume, "reference": reference})
        return rows

    @router.post("/datasets/{dataset_id}/characterization", status_code=202)
    def start_characterization(dataset_id: str, response: Response) -> dict:
        dataset_or_404(dataset_id)
        if not catalog.files(dataset_id):
            raise HTTPException(422, "the period has no files to characterize")
        run, created = characterization.submit(dataset_id)
        response.status_code = 202 if created else 200
        return run

    @router.get("/datasets/{dataset_id}/characterization")
    def get_characterization(dataset_id: str) -> dict:
        dataset_or_404(dataset_id)
        results, summary = [], {"ok": 0, "failed": 0, "pending": 0}
        for row in characterization_rows(dataset_id):
            result = row["result"]
            status = result["status"] if result else "pending"
            summary[status] += 1
            results.append({"filename": row["filename"], "key": row["key"], "size_bytes": row["size_bytes"],
                            **(result or {"error": None}), "status": status,
                            "volume_m3": row["volume"], "reference": row["reference"]})
        return {"run": catalog.latest_run("characterization", dataset_id), "summary": summary, "results": results}

    @router.get("/datasets/{dataset_id}/characterization.csv")
    def get_characterization_csv(dataset_id: str) -> Response:
        dataset = dataset_or_404(dataset_id)
        return Response(
            characterization_csv(dataset["period_label"], characterization_rows(dataset_id)),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="reporte_parte1.csv"'},
        )

    @router.get("/matches")
    def matches(previous: str, current: str) -> dict:
        if previous == current:
            raise HTTPException(422, "previous and current must be different revisions")
        dataset_or_404(previous)
        dataset_or_404(current)
        try:
            result = match_inventories(catalog.inventory(previous), catalog.inventory(current))
        except ValueError:
            raise HTTPException(409, "both revisions must be closed before comparing") from None
        return {
            "pairs": [
                {"key": p.key, "previous": asdict(p.previous), "current": asdict(p.current)}
                for p in result.pairs
            ],
            "only_previous": [asdict(e) for e in result.only_previous],
            "only_current": [asdict(e) for e in result.only_current],
            "incidents": [asdict(i) for i in result.incidents],
        }

    app = FastAPI(title="Visor comparativo de sólidos", version="0.1.0")
    app.include_router(router)
    return app

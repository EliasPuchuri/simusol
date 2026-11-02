"""SQLite catalog of datasets (model revisions) and their uploaded files."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from solids.domain.inventory import Inventory, InventoryEntry
from solids.domain.orientation_reference import ReferenceRow


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


class Invalid(Exception):
    pass


_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, period_label TEXT NOT NULL,
    period_kind TEXT NOT NULL, revision INTEGER NOT NULL, is_demo INTEGER NOT NULL,
    spatial_reference TEXT, units TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id),
    filename TEXT NOT NULL, filename_lower TEXT NOT NULL, key TEXT NOT NULL,
    sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, stored_name TEXT NOT NULL,
    UNIQUE (dataset_id, filename_lower)
);
CREATE TABLE IF NOT EXISTS qc_cache (
    sha256 TEXT NOT NULL, qc_version TEXT NOT NULL, status TEXT NOT NULL,
    result_json TEXT NOT NULL, computed_at TEXT NOT NULL, PRIMARY KEY (sha256, qc_version)
);
CREATE TABLE IF NOT EXISTS qc_runs (
    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id), state TEXT NOT NULL,
    total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, error TEXT,
    created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS characterization_cache (
    sha256 TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
    result_json TEXT NOT NULL, computed_at TEXT NOT NULL, PRIMARY KEY (sha256, version)
);
CREATE TABLE IF NOT EXISTS characterization_runs (
    id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES datasets(id), state TEXT NOT NULL,
    total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, error TEXT,
    created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS pair_cache (
    sha_previous TEXT NOT NULL, sha_current TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
    result_json TEXT NOT NULL, computed_at TEXT NOT NULL, PRIMARY KEY (sha_previous, sha_current, version)
);
CREATE TABLE IF NOT EXISTS comparison_runs (
    id TEXT PRIMARY KEY, previous_id TEXT NOT NULL REFERENCES datasets(id), current_id TEXT NOT NULL REFERENCES datasets(id),
    state TEXT NOT NULL, total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, error TEXT,
    created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
    previous_id TEXT NOT NULL, current_id TEXT NOT NULL, key TEXT NOT NULL, reviewer TEXT NOT NULL,
    agrees INTEGER NOT NULL, expected_state TEXT, expected_body_type TEXT, expected_azimuth REAL, expected_dip REAL,
    comment TEXT NOT NULL, system_state TEXT, system_subtype TEXT, system_description TEXT, profile TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, PRIMARY KEY (previous_id, current_id, key, reviewer)
);
CREATE TABLE IF NOT EXISTS orientation_refs (
    dataset_id TEXT NOT NULL REFERENCES datasets(id), key TEXT NOT NULL, filename TEXT NOT NULL,
    orientation_type TEXT NOT NULL, azimuth REAL, dip REAL, method TEXT NOT NULL,
    observations TEXT NOT NULL, source_line INTEGER NOT NULL, PRIMARY KEY (dataset_id, key)
);
"""


class Catalog:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(datasets)")}
            if "archived" not in columns:  # additive migration: existing data is untouched
                conn.execute("ALTER TABLE datasets ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn

    # datasets -------------------------------------------------------------
    def create_dataset(
        self, *, name: str, period_label: str, period_kind: str, is_demo: bool,
        spatial_reference: str | None, units: str | None,
    ) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM datasets WHERE name = ? AND period_label = ?",
                (name, period_label),
            ).fetchone()
            record = {
                "id": uuid.uuid4().hex, "name": name, "period_label": period_label,
                "period_kind": period_kind, "revision": row[0] + 1, "is_demo": int(is_demo),
                "spatial_reference": spatial_reference, "units": units, "state": "open",
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            conn.execute(
                "INSERT INTO datasets (id, name, period_label, period_kind, revision, is_demo, spatial_reference, units, state, created_at) "
                "VALUES (:id,:name,:period_label,:period_kind,:revision,"
                ":is_demo,:spatial_reference,:units,:state,:created_at)", record,
            )
        return self._dataset_dict(record)

    @staticmethod
    def _dataset_dict(row) -> dict:
        data = dict(row)
        data["is_demo"] = bool(data["is_demo"])
        data["archived"] = bool(data.get("archived", 0))
        return data

    def get_dataset(self, dataset_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row is None:
            raise NotFound(dataset_id)
        return self._dataset_dict(row)

    def list_datasets(self, include_archived: bool = False) -> list[dict]:
        where = "" if include_archived else "WHERE d.archived = 0 "
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT d.*, (SELECT COUNT(*) FROM files f WHERE f.dataset_id = d.id) AS file_count "
                f"FROM datasets d {where}ORDER BY d.created_at DESC, d.revision DESC"
            ).fetchall()
        return [self._dataset_dict(r) for r in rows]

    def set_archived(self, dataset_id: str, archived: bool) -> dict:
        self.get_dataset(dataset_id)
        with self._conn() as conn:
            conn.execute("UPDATE datasets SET archived = ? WHERE id = ?", (int(archived), dataset_id))
        return self.get_dataset(dataset_id)

    def close_dataset(self, dataset_id: str) -> dict:
        dataset = self.get_dataset(dataset_id)
        if dataset["state"] == "closed":
            raise Conflict("dataset is already closed")
        with self._conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM files WHERE dataset_id = ?", (dataset_id,)).fetchone()[0] == 0:
                raise Invalid("an empty inventory cannot be closed")
            conn.execute("UPDATE datasets SET state = 'closed' WHERE id = ?", (dataset_id,))
        return self.get_dataset(dataset_id)

    # files ----------------------------------------------------------------
    def add_file(self, dataset_id: str, entry: InventoryEntry, stored_name: str) -> None:
        if self.get_dataset(dataset_id)["state"] != "open":
            raise Conflict("dataset is closed; create another revision to change it")
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO files VALUES (?,?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, dataset_id, entry.filename, entry.filename.lower(),
                     entry.key, entry.sha256, entry.size_bytes, stored_name),
                )
        except sqlite3.IntegrityError as exc:
            raise Conflict(f"file '{entry.filename}' already exists in this dataset") from exc

    def inventory(self, dataset_id: str) -> Inventory:
        dataset = self.get_dataset(dataset_id)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT filename, key, sha256, size_bytes FROM files WHERE dataset_id = ?", (dataset_id,)
            ).fetchall()
        entries = [InventoryEntry(r["filename"], r["key"], r["sha256"], r["size_bytes"]) for r in rows]
        return Inventory.from_entries(entries, closed=dataset["state"] == "closed")

    # orientation reference --------------------------------------------------
    def replace_orientation_reference(self, dataset_id: str, rows: list[ReferenceRow]) -> None:
        """Atomically replace the whole table of a dataset."""
        self.get_dataset(dataset_id)
        with self._conn() as conn:
            conn.execute("DELETE FROM orientation_refs WHERE dataset_id = ?", (dataset_id,))
            conn.executemany(
                "INSERT INTO orientation_refs VALUES (?,?,?,?,?,?,?,?,?)",
                [(dataset_id, r.key, r.filename, r.orientation_type, r.azimuth, r.dip,
                  r.method, r.observations, r.line) for r in rows],
            )

    def orientation_reference(self, dataset_id: str) -> list[dict]:
        self.get_dataset(dataset_id)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT key, filename, orientation_type, azimuth, dip, method, observations "
                "FROM orientation_refs WHERE dataset_id = ? ORDER BY key", (dataset_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def files_by_key(self, dataset_id: str, key: str) -> list[dict]:
        self.get_dataset(dataset_id)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT filename, key, sha256, size_bytes, stored_name FROM files "
                "WHERE dataset_id = ? AND key = ? ORDER BY filename", (dataset_id, key)
            ).fetchall()
        return [dict(r) for r in rows]

    # quality control ----------------------------------------------------------
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def files(self, dataset_id: str) -> list[dict]:
        self.get_dataset(dataset_id)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT filename, key, sha256, size_bytes, stored_name FROM files "
                "WHERE dataset_id = ? ORDER BY filename", (dataset_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    # analysis runs and caches (kind: "qc" or "characterization") -----------------------------
    _KINDS = {
        "qc": ("qc_cache", "qc_version", "qc_runs"),
        "characterization": ("characterization_cache", "version", "characterization_runs"),
    }

    def _t(self, kind: str) -> tuple[str, str, str]:
        return self._KINDS[kind]  # table names come from this whitelist only

    def create_run(self, kind: str, dataset_id: str, total: int, state: str = "queued") -> dict:
        _, _, runs = self._t(kind)
        run = {"id": uuid.uuid4().hex, "dataset_id": dataset_id, "state": state, "total": total,
               "done": 0, "error": None, "created_at": self._now(), "finished_at": None}
        with self._conn() as conn:
            conn.execute(f"INSERT INTO {runs} VALUES (:id,:dataset_id,:state,:total,:done,:error,:created_at,:finished_at)", run)
        return run

    def update_run(self, kind: str, run_id: str, **fields) -> None:
        assert set(fields) <= {"state", "done", "error", "finished_at"}
        _, _, runs = self._t(kind)
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        with self._conn() as conn:
            conn.execute(f"UPDATE {runs} SET {sets} WHERE id = :id", {**fields, "id": run_id})

    def get_run(self, kind: str, run_id: str) -> dict:
        _, _, runs = self._t(kind)
        with self._conn() as conn:
            row = conn.execute(f"SELECT * FROM {runs} WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFound(run_id)
        return dict(row)

    def active_run(self, kind: str, dataset_id: str) -> dict | None:
        _, _, runs = self._t(kind)
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {runs} WHERE dataset_id = ? AND state IN ('queued','running') "
                "ORDER BY created_at DESC LIMIT 1", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def latest_run(self, kind: str, dataset_id: str) -> dict | None:
        _, _, runs = self._t(kind)
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {runs} WHERE dataset_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1", (dataset_id,)
            ).fetchone()
        return dict(row) if row else None

    def interrupt_stale_runs(self) -> None:
        with self._conn() as conn:
            for _, _, runs in self._KINDS.values():
                conn.execute(
                    f"UPDATE {runs} SET state = 'failed', error = 'interrupted by a restart', finished_at = ? "
                    "WHERE state IN ('queued','running')", (self._now(),)
                )
            conn.execute(
                "UPDATE comparison_runs SET state = 'failed', error = 'interrupted by a restart', finished_at = ? "
                "WHERE state IN ('queued','running')", (self._now(),)
            )

    def get_cached(self, kind: str, sha256: str, version: str) -> dict | None:
        cache, column, _ = self._t(kind)
        with self._conn() as conn:
            row = conn.execute(f"SELECT result_json FROM {cache} WHERE sha256 = ? AND {column} = ?", (sha256, version)).fetchone()
        return json.loads(row["result_json"]) if row else None

    def put_cached(self, kind: str, sha256: str, version: str, result: dict) -> None:
        cache, _, _ = self._t(kind)
        with self._conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {cache} VALUES (?,?,?,?,?)",
                (sha256, version, result.get("status", "failed"), json.dumps(result, allow_nan=False), self._now()),
            )

    # qc-named shortcuts kept for readability at call sites
    def create_qc_run(self, dataset_id: str, total: int, state: str = "queued") -> dict:
        return self.create_run("qc", dataset_id, total, state)

    def get_qc_cached(self, sha256: str, version: str) -> dict | None:
        return self.get_cached("qc", sha256, version)

    def latest_qc_run(self, dataset_id: str) -> dict | None:
        return self.latest_run("qc", dataset_id)

    # pair comparison ----------------------------------------------------------------------
    def get_pair(self, sha_previous: str, sha_current: str, version: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT result_json FROM pair_cache WHERE sha_previous = ? AND sha_current = ? AND version = ?",
                (sha_previous, sha_current, version),
            ).fetchone()
        return json.loads(row["result_json"]) if row else None

    def put_pair(self, sha_previous: str, sha_current: str, version: str, result: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pair_cache VALUES (?,?,?,?,?,?)",
                (sha_previous, sha_current, version, result.get("status", "failed"),
                 json.dumps(result, allow_nan=False), self._now()),
            )

    def create_comparison_run(self, previous_id: str, current_id: str, total: int, state: str = "queued") -> dict:
        run = {"id": uuid.uuid4().hex, "previous_id": previous_id, "current_id": current_id, "state": state,
               "total": total, "done": 0, "error": None, "created_at": self._now(), "finished_at": None}
        with self._conn() as conn:
            conn.execute("INSERT INTO comparison_runs VALUES (:id,:previous_id,:current_id,:state,:total,:done,:error,:created_at,:finished_at)", run)
        return run

    def update_comparison_run(self, run_id: str, **fields) -> None:
        assert set(fields) <= {"state", "done", "error", "finished_at"}
        sets = ", ".join(f"{k} = :{k}" for k in fields)
        with self._conn() as conn:
            conn.execute(f"UPDATE comparison_runs SET {sets} WHERE id = :id", {**fields, "id": run_id})

    def get_comparison_run(self, run_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM comparison_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFound(run_id)
        return dict(row)

    def active_comparison_run(self, previous_id: str, current_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM comparison_runs WHERE previous_id = ? AND current_id = ? AND state IN ('queued','running') "
                "ORDER BY created_at DESC LIMIT 1", (previous_id, current_id)
            ).fetchone()
        return dict(row) if row else None

    def latest_comparison_run(self, previous_id: str, current_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM comparison_runs WHERE previous_id = ? AND current_id = ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT 1", (previous_id, current_id)
            ).fetchone()
        return dict(row) if row else None

    # area reviews ---------------------------------------------------------------------------
    def upsert_review(self, review: dict) -> None:
        now = self._now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO reviews (previous_id, current_id, key, reviewer, agrees, expected_state, expected_body_type,
                       expected_azimuth, expected_dip, comment, system_state, system_subtype, system_description, profile,
                       created_at, updated_at)
                   VALUES (:previous_id,:current_id,:key,:reviewer,:agrees,:expected_state,:expected_body_type,
                       :expected_azimuth,:expected_dip,:comment,:system_state,:system_subtype,:system_description,:profile,:now,:now)
                   ON CONFLICT(previous_id, current_id, key, reviewer) DO UPDATE SET
                       agrees=excluded.agrees, expected_state=excluded.expected_state,
                       expected_body_type=excluded.expected_body_type, expected_azimuth=excluded.expected_azimuth,
                       expected_dip=excluded.expected_dip, comment=excluded.comment, system_state=excluded.system_state,
                       system_subtype=excluded.system_subtype, system_description=excluded.system_description,
                       profile=excluded.profile, updated_at=excluded.updated_at""",
                {**review, "agrees": int(review["agrees"]), "now": now},
            )

    def list_reviews(self, previous_id: str, current_id: str, reviewer: str | None = None) -> list[dict]:
        sql = "SELECT * FROM reviews WHERE previous_id = ? AND current_id = ?"
        args: list = [previous_id, current_id]
        if reviewer:
            sql += " AND reviewer = ?"
            args.append(reviewer)
        with self._conn() as conn:
            rows = conn.execute(sql + " ORDER BY key, reviewer", args).fetchall()
        return [{**dict(r), "agrees": bool(r["agrees"])} for r in rows]

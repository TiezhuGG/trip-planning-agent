from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.schemas.planning import PlanningJob


class PlanningJobStore(Protocol):
    def get_by_id(self, job_id: str) -> PlanningJob | None: ...

    def list_recent(self, limit: int = 10, trip_id: str | None = None) -> list[PlanningJob]: ...

    def save(self, job: PlanningJob) -> None: ...

    def delete(self, job_id: str) -> None: ...


class JsonPlanningJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_by_id(self, job_id: str) -> PlanningJob | None:
        payload = self._load()
        item = payload.get(job_id)
        if item is None:
            return None
        return PlanningJob.model_validate(item)

    def list_recent(self, limit: int = 10, trip_id: str | None = None) -> list[PlanningJob]:
        items = [
            PlanningJob.model_validate(item)
            for item in self._load().values()
        ]
        if trip_id:
            items = [item for item in items if item.trip_id == trip_id]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.model_copy(deep=True) for item in items[: max(1, int(limit))]]

    def save(self, job: PlanningJob) -> None:
        payload = self._load()
        payload[job.id] = job.model_dump(mode="json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete(self, job_id: str) -> None:
        payload = self._load()
        if job_id not in payload:
            return
        payload.pop(job_id, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}


class SqlitePlanningJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_by_id(self, job_id: str) -> PlanningJob | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload_json FROM planning_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return PlanningJob.model_validate(json.loads(row["payload_json"]))

    def list_recent(self, limit: int = 10, trip_id: str | None = None) -> list[PlanningJob]:
        sql = """
            SELECT payload_json FROM planning_jobs
        """
        params: list[object] = []
        if trip_id:
            sql += " WHERE trip_id = ?"
            params.append(trip_id)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with closing(self._connect()) as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            PlanningJob.model_validate(json.loads(row["payload_json"]))
            for row in rows
        ]

    def save(self, job: PlanningJob) -> None:
        payload_json = json.dumps(
            job.model_dump(mode="json"),
            ensure_ascii=False,
        )
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO planning_jobs (
                    id,
                    trip_id,
                    status,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    trip_id = excluded.trip_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    job.id,
                    job.trip_id,
                    job.status,
                    job.updated_at.isoformat(),
                    payload_json,
                ),
            )
            conn.commit()

    def delete(self, job_id: str) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                "DELETE FROM planning_jobs WHERE id = ?",
                (job_id,),
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS planning_jobs (
                    id TEXT PRIMARY KEY,
                    trip_id TEXT,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_planning_jobs_trip_id_updated_at
                ON planning_jobs(trip_id, updated_at DESC)
                """
            )
            conn.commit()


def create_planning_job_store(settings: Settings) -> PlanningJobStore:
    path = _resolve_store_path(settings.planner_job_store_path)
    driver = (settings.planner_job_store_driver or "auto").strip().lower()
    if driver == "auto":
        driver = "json" if path.suffix.lower() == ".json" else "sqlite"
    if driver == "json":
        return JsonPlanningJobStore(path)
    if driver == "sqlite":
        return SqlitePlanningJobStore(path)
    raise ValueError(f"Unsupported planner_job_store_driver: {settings.planner_job_store_driver}")


def _resolve_store_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path

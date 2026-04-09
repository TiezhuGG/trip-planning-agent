from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.schemas.planning import TripWorkspace


class TripWorkspaceStore(Protocol):
    def get_by_id(self, trip_id: str) -> TripWorkspace | None: ...

    def get_by_share_token(self, share_token: str) -> TripWorkspace | None: ...

    def save(self, workspace: TripWorkspace) -> None: ...


class JsonTripWorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_by_id(self, trip_id: str) -> TripWorkspace | None:
        payload = self._load()
        item = payload.get(trip_id)
        if item is None:
            return None
        return TripWorkspace.model_validate(item)

    def get_by_share_token(self, share_token: str) -> TripWorkspace | None:
        payload = self._load()
        for item in payload.values():
            workspace = TripWorkspace.model_validate(item)
            if workspace.share_token == share_token:
                return workspace
        return None

    def save(self, workspace: TripWorkspace) -> None:
        payload = self._load()
        payload[workspace.id] = workspace.model_dump(mode="json")
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


class SqliteTripWorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def get_by_id(self, trip_id: str) -> TripWorkspace | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload_json FROM trip_workspaces WHERE id = ?",
                (trip_id,),
            ).fetchone()
        if row is None:
            return None
        return TripWorkspace.model_validate(json.loads(row["payload_json"]))

    def get_by_share_token(self, share_token: str) -> TripWorkspace | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT payload_json FROM trip_workspaces WHERE share_token = ?",
                (share_token,),
            ).fetchone()
        if row is None:
            return None
        return TripWorkspace.model_validate(json.loads(row["payload_json"]))

    def save(self, workspace: TripWorkspace) -> None:
        payload_json = json.dumps(
            workspace.model_dump(mode="json"),
            ensure_ascii=False,
        )
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO trip_workspaces (
                    id,
                    share_token,
                    status,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    share_token = excluded.share_token,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    workspace.id,
                    workspace.share_token,
                    workspace.status,
                    workspace.updated_at.isoformat(),
                    payload_json,
                ),
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
                CREATE TABLE IF NOT EXISTS trip_workspaces (
                    id TEXT PRIMARY KEY,
                    share_token TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trip_workspaces_share_token
                ON trip_workspaces(share_token)
                """
            )
            conn.commit()


def create_trip_workspace_store(settings: Settings) -> TripWorkspaceStore:
    path = _resolve_store_path(settings.planner_trip_store_path)
    driver = (settings.planner_trip_store_driver or "auto").strip().lower()
    if driver == "auto":
        driver = "json" if path.suffix.lower() == ".json" else "sqlite"
    if driver == "json":
        return JsonTripWorkspaceStore(path)
    if driver == "sqlite":
        return SqliteTripWorkspaceStore(path)
    raise ValueError(f"Unsupported planner_trip_store_driver: {settings.planner_trip_store_driver}")


def _resolve_store_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[2] / path

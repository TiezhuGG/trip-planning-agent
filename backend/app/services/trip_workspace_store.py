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

    def list_recent(self, limit: int = 10) -> list[TripWorkspace]: ...

    def get_version(self, trip_id: str, version: int) -> TripWorkspace | None: ...

    def list_versions(self, trip_id: str, limit: int = 20, offset: int = 0) -> list[TripWorkspace]: ...

    def count_versions(self, trip_id: str) -> int: ...

    def save(self, workspace: TripWorkspace) -> None: ...

    def save_version_snapshot(self, workspace: TripWorkspace) -> None: ...

    def delete_version(self, trip_id: str, version: int) -> None: ...


class JsonTripWorkspaceStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_by_id(self, trip_id: str) -> TripWorkspace | None:
        payload = self._load()
        item = payload["workspaces"].get(trip_id)
        if item is None:
            return None
        return TripWorkspace.model_validate(item)

    def get_by_share_token(self, share_token: str) -> TripWorkspace | None:
        payload = self._load()
        for item in payload["workspaces"].values():
            workspace = TripWorkspace.model_validate(item)
            if workspace.share_token == share_token:
                return workspace
        return None

    def get_version(self, trip_id: str, version: int) -> TripWorkspace | None:
        payload = self._load()
        item = payload["history"].get(trip_id, {}).get(str(version))
        if item is not None:
            return TripWorkspace.model_validate(item)
        current = payload["workspaces"].get(trip_id)
        if current is None:
            return None
        workspace = TripWorkspace.model_validate(current)
        return workspace if workspace.version == version else None

    def list_versions(self, trip_id: str, limit: int = 20, offset: int = 0) -> list[TripWorkspace]:
        payload = self._load()
        items = [
            TripWorkspace.model_validate(item)
            for item in payload["history"].get(trip_id, {}).values()
        ]
        if not items:
            current = self.get_by_id(trip_id)
            return [current] if current is not None else []
        items.sort(key=lambda item: item.version, reverse=True)
        start = max(0, int(offset))
        end = start + max(1, int(limit))
        return [item.model_copy(deep=True) for item in items[start:end]]

    def count_versions(self, trip_id: str) -> int:
        payload = self._load()
        items = payload["history"].get(trip_id, {})
        current = payload["workspaces"].get(trip_id)
        if current is None:
            return 0
        return len(items) if isinstance(items, dict) else 1

    def save(self, workspace: TripWorkspace) -> None:
        payload = self._load()
        snapshot = workspace.model_dump(mode="json")
        payload["workspaces"][workspace.id] = snapshot
        payload["history"].setdefault(workspace.id, {})[str(workspace.version)] = snapshot
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def save_version_snapshot(self, workspace: TripWorkspace) -> None:
        payload = self._load()
        snapshot = workspace.model_dump(mode="json")
        payload["history"].setdefault(workspace.id, {})[str(workspace.version)] = snapshot
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def delete_version(self, trip_id: str, version: int) -> None:
        payload = self._load()
        history = payload["history"].get(trip_id)
        if isinstance(history, dict):
            history.pop(str(version), None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_recent(self, limit: int = 10) -> list[TripWorkspace]:
        items = [
            TripWorkspace.model_validate(item)
            for item in self._load()["workspaces"].values()
        ]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.model_copy(deep=True) for item in items[: max(1, int(limit))]]

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {"workspaces": {}, "history": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"workspaces": {}, "history": {}}
        if "workspaces" in raw or "history" in raw:
            workspaces = raw.get("workspaces", {})
            history = raw.get("history", {})
            return {
                "workspaces": workspaces if isinstance(workspaces, dict) else {},
                "history": history if isinstance(history, dict) else {},
            }
        return {
            "workspaces": raw,
            "history": {},
        }


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

    def get_version(self, trip_id: str, version: int) -> TripWorkspace | None:
        with closing(self._connect()) as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM trip_workspace_versions
                WHERE trip_id = ? AND version = ?
                """,
                (trip_id, version),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT payload_json FROM trip_workspaces WHERE id = ?",
                    (trip_id,),
                ).fetchone()
        if row is None:
            return None
        workspace = TripWorkspace.model_validate(json.loads(row["payload_json"]))
        return workspace if workspace.version == version else None

    def list_versions(self, trip_id: str, limit: int = 20, offset: int = 0) -> list[TripWorkspace]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM trip_workspace_versions
                WHERE trip_id = ?
                ORDER BY version DESC
                LIMIT ?
                OFFSET ?
                """,
                (trip_id, max(1, int(limit)), max(0, int(offset))),
            ).fetchall()
        if not rows:
            current = self.get_by_id(trip_id)
            return [current] if current is not None else []
        return [
            TripWorkspace.model_validate(json.loads(row["payload_json"]))
            for row in rows
        ]

    def count_versions(self, trip_id: str) -> int:
        with closing(self._connect()) as conn:
            current = conn.execute(
                "SELECT 1 FROM trip_workspaces WHERE id = ?",
                (trip_id,),
            ).fetchone()
            if current is None:
                return 0
            row = conn.execute(
                """
                SELECT COUNT(*) AS version_count FROM trip_workspace_versions
                WHERE trip_id = ?
                """,
                (trip_id,),
            ).fetchone()
        return int(row["version_count"]) if row is not None else 0

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
            conn.execute(
                """
                INSERT INTO trip_workspace_versions (
                    trip_id,
                    version,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trip_id, version) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    workspace.id,
                    workspace.version,
                    workspace.updated_at.isoformat(),
                    payload_json,
                ),
            )
            conn.commit()

    def save_version_snapshot(self, workspace: TripWorkspace) -> None:
        payload_json = json.dumps(
            workspace.model_dump(mode="json"),
            ensure_ascii=False,
        )
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO trip_workspace_versions (
                    trip_id,
                    version,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(trip_id, version) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (
                    workspace.id,
                    workspace.version,
                    workspace.updated_at.isoformat(),
                    payload_json,
                ),
            )
            conn.commit()

    def delete_version(self, trip_id: str, version: int) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                DELETE FROM trip_workspace_versions
                WHERE trip_id = ? AND version = ?
                """,
                (trip_id, version),
            )
            conn.commit()

    def list_recent(self, limit: int = 10) -> list[TripWorkspace]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM trip_workspaces
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()
        return [
            TripWorkspace.model_validate(json.loads(row["payload_json"]))
            for row in rows
        ]

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trip_workspace_versions (
                    trip_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (trip_id, version)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trip_workspace_versions_trip_updated
                ON trip_workspace_versions(trip_id, updated_at DESC)
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

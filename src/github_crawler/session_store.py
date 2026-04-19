import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


METADATA_FILE = "session.json"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip("-._")
    return cleaned or "repo"


@dataclass(frozen=True)
class CrawlSession:
    session_id: str
    session_dir: str
    clone_root: str
    artifact_dir: str
    archive_root: str
    metadata_path: str

    def repo_clone_dir(self, repo_full_name: str) -> str:
        return os.path.join(self.clone_root, _slugify(repo_full_name))


def _sessions_root(output_dir: str) -> str:
    return os.path.join(output_dir, "sessions")


def _archives_root(output_dir: str) -> str:
    return os.path.join(output_dir, "archives")


def create_session(output_dir: str, repository_request: str, property_query: str) -> CrawlSession:
    session_id = f"session-{_timestamp()}-{uuid4().hex[:8]}"
    session_dir = os.path.join(_sessions_root(output_dir), session_id)
    clone_root = os.path.join(session_dir, "clones")
    artifact_dir = os.path.join(session_dir, "artifacts")
    archive_root = _archives_root(output_dir)
    metadata_path = os.path.join(session_dir, METADATA_FILE)

    os.makedirs(clone_root, exist_ok=False)
    os.makedirs(artifact_dir, exist_ok=False)
    os.makedirs(archive_root, exist_ok=True)

    session = CrawlSession(
        session_id=session_id,
        session_dir=session_dir,
        clone_root=clone_root,
        artifact_dir=artifact_dir,
        archive_root=archive_root,
        metadata_path=metadata_path,
    )
    update_session_metadata(
        session,
        {
            "session_id": session_id,
            "created_at": _timestamp(),
            "session_dir": session_dir,
            "clone_root": clone_root,
            "artifact_dir": artifact_dir,
            "repository_request": repository_request,
            "property_query": property_query,
            "status": "created",
            "repositories": [],
            "artifacts": {},
        },
    )
    return session


def update_session_metadata(session: CrawlSession, data: Dict[str, Any]) -> Dict[str, Any]:
    current = read_session_metadata(session.metadata_path)
    current.update(data)
    with open(session.metadata_path, "w", encoding="utf-8") as handle:
        json.dump(current, handle, indent=2, sort_keys=True)
    return current


def read_session_metadata(metadata_path: str) -> Dict[str, Any]:
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def list_sessions(output_dir: str) -> List[Dict[str, Any]]:
    sessions_root = _sessions_root(output_dir)
    if not os.path.isdir(sessions_root):
        return []

    sessions: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(sessions_root), reverse=True):
        session_dir = os.path.join(sessions_root, name)
        metadata_path = os.path.join(session_dir, METADATA_FILE)
        if not os.path.isdir(session_dir) or not os.path.exists(metadata_path):
            continue
        metadata = read_session_metadata(metadata_path)
        if metadata:
            sessions.append(metadata)
    return sessions


def delete_session(output_dir: str, session_id: str, persist_archive: bool = False) -> Optional[str]:
    session_dir = os.path.join(_sessions_root(output_dir), session_id)
    if not os.path.isdir(session_dir):
        raise FileNotFoundError(f"Session '{session_id}' was not found.")

    archive_path = None
    if persist_archive:
        archive_root = _archives_root(output_dir)
        os.makedirs(archive_root, exist_ok=True)
        archive_base = os.path.join(archive_root, session_id)
        archive_path = shutil.make_archive(archive_base, "zip", root_dir=session_dir)

    shutil.rmtree(session_dir)
    return archive_path

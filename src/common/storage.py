import json
from datetime import datetime, timezone
from typing import Any

from .models import Task

VALID_STATUSES = {"pending", "done", "archived"}


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def normalize_priority(value: Any) -> int:
    priority = int(value if value is not None else 3)
    if priority < 1 or priority > 5:
        raise ValueError("priority deve estar entre 1 e 5")
    return priority


def normalize_status(value: Any) -> str:
    status = str(value or "pending").lower()
    if status not in VALID_STATUSES:
        raise ValueError("status deve ser pending, done ou archived")
    return status


def create_task(session, payload: dict[str, Any], protocol: str) -> Task:
    task = Task(
        protocol=protocol.upper(),
        title=str(payload["title"]).strip(),
        description=str(payload.get("description", "")),
        status=normalize_status(payload.get("status")),
        priority=normalize_priority(payload.get("priority")),
        created_at=parse_timestamp(payload.get("created_at")),
        updated_at=parse_timestamp(payload.get("updated_at")),
        raw_payload=json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )
    if not task.title:
        raise ValueError("title é obrigatório")
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def update_task(session, task: Task, payload: dict[str, Any], protocol: str) -> Task:
    if "title" in payload:
        title = str(payload["title"]).strip()
        if not title:
            raise ValueError("title não pode ser vazio")
        task.title = title
    if "description" in payload:
        task.description = str(payload.get("description", ""))
    if "status" in payload:
        task.status = normalize_status(payload.get("status"))
    if "priority" in payload:
        task.priority = normalize_priority(payload.get("priority"))
    task.protocol = protocol.upper()
    task.updated_at = datetime.now(timezone.utc)
    task.raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    session.commit()
    session.refresh(task)
    return task


def task_to_dict(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "protocol": task.protocol,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }

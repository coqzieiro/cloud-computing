from time import perf_counter
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.common.db import SessionLocal, init_db
from src.common.models import Task
from src.common.settings import SERVICE_NAME
from src.common.storage import create_task, task_to_dict, update_task

REQUESTS = Counter("http_requests_total", "Total de requisições", ["service", "protocol", "endpoint", "status"])
LATENCY = Histogram("request_latency_seconds", "Latência de requisições", ["service", "protocol", "endpoint"])

app = FastAPI(title="Grupo 03 Task Manager REST API", version="1.0.0")


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    status: str = Field(default="pending", pattern="^(pending|done|archived)$")
    priority: int = Field(default=3, ge=1, le=5)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|done|archived)$")
    priority: int | None = Field(default=None, ge=1, le=5)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME, "protocol": "REST", "domain": "tasks"}


@app.post("/v1/tasks", status_code=201)
def create_task_endpoint(payload: TaskIn, db: Annotated[Session, Depends(get_db)]) -> dict:
    start = perf_counter()
    status = "201"
    try:
        task = create_task(db, payload.model_dump(), protocol="REST")
        return {"status": "created", "task": task_to_dict(task)}
    except Exception:
        status = "500"
        raise
    finally:
        REQUESTS.labels(SERVICE_NAME, "REST", "/v1/tasks", status).inc()
        LATENCY.labels(SERVICE_NAME, "REST", "/v1/tasks").observe(perf_counter() - start)


@app.get("/v1/tasks/{task_id}")
def get_task_endpoint(task_id: int, db: Annotated[Session, Depends(get_db)]) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    return {"task": task_to_dict(task)}


@app.put("/v1/tasks/{task_id}")
def update_task_endpoint(task_id: int, payload: TaskUpdate, db: Annotated[Session, Depends(get_db)]) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    updated = update_task(db, task, payload.model_dump(exclude_none=True), protocol="REST")
    return {"status": "updated", "task": task_to_dict(updated)}


@app.delete("/v1/tasks/{task_id}")
def delete_task_endpoint(task_id: int, db: Annotated[Session, Depends(get_db)]) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="tarefa não encontrada")
    db.delete(task)
    db.commit()
    return {"status": "deleted", "id": task_id}


@app.get("/v1/tasks")
def list_tasks(db: Annotated[Session, Depends(get_db)], limit: int = 10) -> dict:
    rows = (
        db.query(Task)
        .order_by(desc(Task.updated_at))
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return {"items": [task_to_dict(row) for row in rows]}


@app.get("/v1/stats")
def stats(db: Annotated[Session, Depends(get_db)]) -> dict:
    by_protocol = dict(db.query(Task.protocol, func.count(Task.id)).group_by(Task.protocol).all())
    by_status = dict(db.query(Task.status, func.count(Task.id)).group_by(Task.status).all())
    total = sum(by_protocol.values())
    last = db.query(func.max(Task.updated_at)).scalar()
    return {"total_tasks": total, "by_protocol": by_protocol, "by_status": by_status, "last_updated_at": last.isoformat() if last else None}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

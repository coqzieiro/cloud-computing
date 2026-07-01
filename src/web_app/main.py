import csv
import io
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from src.common.db import SessionLocal, init_db
from src.common.models import Task
from src.common.storage import task_to_dict

PAGE_VIEWS = Counter("web_page_views_total", "Visualizações do dashboard", ["endpoint"])

app = FastAPI(title="Grupo 03 Task Manager Dashboard", version="1.0.0")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    PAGE_VIEWS.labels("/").inc()
    return """
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Grupo 03 · Task Manager SOAP vs REST</title>
  <style>
    body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #0f172a; color: #e2e8f0; }
    header { padding: 32px; background: linear-gradient(135deg, #1d4ed8, #7c3aed); }
    main { padding: 24px; max-width: 1100px; margin: auto; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .card { background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 20px; box-shadow: 0 8px 24px #0004; }
    .metric { font-size: 2rem; font-weight: 800; margin: 8px 0; }
    table { width: 100%; border-collapse: collapse; margin-top: 16px; }
    th, td { border-bottom: 1px solid #334155; padding: 10px; text-align: left; }
    a { color: #93c5fd; }
  </style>
</head>
<body>
  <header>
    <h1>Grupo 03 · Task Manager SOAP vs REST</h1>
    <p>Gerenciador de tarefas distribuído com broker MQTT, PostgreSQL, REST, SOAP, Prometheus e Grafana.</p>
  </header>
  <main>
    <section class="grid">
      <div class="card"><span>Total de tarefas</span><div id="total" class="metric">...</div></div>
      <div class="card"><span>REST</span><div id="rest" class="metric">...</div></div>
      <div class="card"><span>SOAP</span><div id="soap" class="metric">...</div></div>
      <div class="card"><span>Última atualização</span><div id="last" class="metric" style="font-size:1rem">...</div></div>
    </section>
    <section class="card" style="margin-top:16px">
      <h2>Tarefas recentes</h2>
      <p><a href="/data/export.csv">Exportar CSV</a> · <a href="http://localhost:3000" target="_blank">Grafana</a> · <a href="http://localhost:9090" target="_blank">Prometheus</a></p>
      <table><thead><tr><th>ID</th><th>Protocolo</th><th>Título</th><th>Status</th><th>Prioridade</th><th>Descrição</th><th>Atualizada em</th></tr></thead><tbody id="rows"></tbody></table>
    </section>
  </main>
<script>
async function refresh() {
  const data = await fetch('/api/state').then(r => r.json());
  document.getElementById('total').textContent = data.total_tasks;
  document.getElementById('rest').textContent = data.by_protocol.REST || 0;
  document.getElementById('soap').textContent = data.by_protocol.SOAP || 0;
  document.getElementById('last').textContent = data.last_updated_at || 'sem dados';
  document.getElementById('rows').innerHTML = data.latest.map(row => `<tr><td>${row.id}</td><td>${row.protocol}</td><td>${row.title}</td><td>${row.status}</td><td>${row.priority}</td><td>${row.description}</td><td>${row.updated_at}</td></tr>`).join('');
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
    """


@app.get("/api/state")
def state(db: Annotated[Session, Depends(get_db)]) -> dict:
    by_protocol = dict(db.query(Task.protocol, func.count(Task.id)).group_by(Task.protocol).all())
    by_status = dict(db.query(Task.status, func.count(Task.id)).group_by(Task.status).all())
    rows = db.query(Task).order_by(desc(Task.updated_at)).limit(20).all()
    last = db.query(func.max(Task.updated_at)).scalar()
    return {
        "total_tasks": sum(by_protocol.values()),
        "by_protocol": by_protocol,
        "by_status": by_status,
        "last_updated_at": last.isoformat() if last else None,
        "latest": [task_to_dict(row) for row in rows],
    }


@app.get("/data/export.csv")
def export_csv(db: Annotated[Session, Depends(get_db)]) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    columns = [
        "id",
        "protocol",
        "title",
        "description",
        "status",
        "priority",
        "created_at",
        "updated_at",
    ]
    writer.writerow(columns)
    for row in db.query(Task).order_by(Task.id).all():
        item = task_to_dict(row)
        writer.writerow([item[column] for column in columns])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=grupo03_tasks.csv"},
    )


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

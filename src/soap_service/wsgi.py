import json
from time import perf_counter

from prometheus_client import Counter, Histogram, make_wsgi_app
from spyne import Application, Integer, ServiceBase, Unicode, rpc
from spyne.protocol.soap import Soap11
from spyne.server.wsgi import WsgiApplication
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from src.common.db import SessionLocal, init_db
from src.common.models import Task
from src.common.settings import SERVICE_NAME
from src.common.storage import create_task, task_to_dict, update_task

REQUESTS = Counter("http_requests_total", "Total de requisições", ["service", "protocol", "endpoint", "status"])
LATENCY = Histogram("request_latency_seconds", "Latência de requisições", ["service", "protocol", "endpoint"])

init_db()


class TaskSoapService(ServiceBase):
    @rpc(Unicode, _returns=Unicode)
    def create_task(ctx, payload_json):
        start = perf_counter()
        status = "200"
        session = SessionLocal()
        try:
            payload = json.loads(payload_json)
            task = create_task(session, payload, protocol="SOAP")
            return json.dumps({"status": "created", "task": task_to_dict(task)}, ensure_ascii=False)
        except Exception as exc:
            status = "500"
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
        finally:
            session.close()
            REQUESTS.labels(SERVICE_NAME, "SOAP", "create_task", status).inc()
            LATENCY.labels(SERVICE_NAME, "SOAP", "create_task").observe(perf_counter() - start)

    @rpc(Integer, _returns=Unicode)
    def get_task(ctx, task_id):
        session = SessionLocal()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return json.dumps({"status": "not_found", "message": "tarefa não encontrada"}, ensure_ascii=False)
            return json.dumps({"status": "ok", "task": task_to_dict(task)}, ensure_ascii=False)
        finally:
            session.close()

    @rpc(Integer, Unicode, _returns=Unicode)
    def update_task(ctx, task_id, payload_json):
        session = SessionLocal()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return json.dumps({"status": "not_found", "message": "tarefa não encontrada"}, ensure_ascii=False)
            payload = json.loads(payload_json)
            updated = update_task(session, task, payload, protocol="SOAP")
            return json.dumps({"status": "updated", "task": task_to_dict(updated)}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)
        finally:
            session.close()

    @rpc(Integer, _returns=Unicode)
    def delete_task(ctx, task_id):
        session = SessionLocal()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return json.dumps({"status": "not_found", "message": "tarefa não encontrada"}, ensure_ascii=False)
            session.delete(task)
            session.commit()
            return json.dumps({"status": "deleted", "id": task_id}, ensure_ascii=False)
        finally:
            session.close()

    @rpc(Integer, _returns=Unicode)
    def list_tasks(ctx, limit):
        session = SessionLocal()
        try:
            rows = session.query(Task).order_by(Task.updated_at.desc()).limit(max(1, min(limit, 200))).all()
            return json.dumps({"items": [task_to_dict(row) for row in rows]}, ensure_ascii=False)
        finally:
            session.close()


soap_app = Application(
    [TaskSoapService],
    tns="urn:grupo03.soap.tasks",
    in_protocol=Soap11(validator="lxml"),
    out_protocol=Soap11(),
)

application = DispatcherMiddleware(WsgiApplication(soap_app), {"/metrics": make_wsgi_app()})

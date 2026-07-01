import csv
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
import requests
from zeep import Client

RUNNING = True


def stop(_signum, _frame):
    global RUNNING
    RUNNING = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def env(name: str, default: str) -> str:
    return os.getenv(name, default)


DATA_DIR = Path(env("DATA_DIR", "/app/data"))
RAW_DIR = DATA_DIR / "raw"
INTERVAL = int(env("COLLECT_INTERVAL_SECONDS", "30"))
MQTT_HOST = env("MQTT_HOST", "localhost")
MQTT_PORT = int(env("MQTT_PORT", "1883"))
MQTT_TOPIC = env("MQTT_TOPIC", "grupo03/tasks/events")
REST_URL = env("REST_URL", "http://localhost:8000/v1/tasks")
SOAP_WSDL = env("SOAP_WSDL", "http://localhost:8001/?wsdl")
FORWARD_PROTOCOL = env("FORWARD_PROTOCOL", "both").lower()
TASK_PREFIX = env("TASK_PREFIX", "Experimento G03")


def generate_task(sequence: int) -> dict[str, Any]:
    priorities = [1, 2, 3, 4, 5]
    statuses = ["pending", "pending", "done", "archived"]
    return {
        "title": f"{TASK_PREFIX} #{sequence:04d}",
        "description": "Tarefa sintética gerada para comparar o mesmo domínio funcional via REST e SOAP.",
        "status": statuses[sequence % len(statuses)],
        "priority": priorities[sequence % len(priorities)],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sample_id": sequence,
    }


def append_raw(payload: dict[str, Any]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "task_events.csv"
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(payload.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(payload)


def publish_mqtt(client: mqtt.Client, payload: dict[str, Any]) -> None:
    result = client.publish(MQTT_TOPIC, json.dumps(payload, ensure_ascii=False), qos=1)
    result.wait_for_publish(timeout=5)


def forward_rest(payload: dict[str, Any]) -> None:
    response = requests.post(REST_URL, json=payload, timeout=10)
    response.raise_for_status()


def forward_soap(payload: dict[str, Any]) -> None:
    client = Client(SOAP_WSDL)
    result = client.service.create_task(json.dumps(payload, ensure_ascii=False))
    body = json.loads(result)
    if body.get("status") != "created":
        raise RuntimeError(body)


def main() -> None:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="grupo03-collector")
    mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    mqtt_client.loop_start()
    sequence = 1

    while RUNNING:
        try:
            payload = generate_task(sequence)
            append_raw(payload)
            publish_mqtt(mqtt_client, payload)
            if FORWARD_PROTOCOL in {"rest", "both"}:
                forward_rest(payload)
            if FORWARD_PROTOCOL in {"soap", "both"}:
                forward_soap(payload)
            print(json.dumps({"event": "task_generated", "payload": payload}, ensure_ascii=False), flush=True)
            sequence += 1
        except Exception as exc:
            print(json.dumps({"event": "collector_error", "error": str(exc)}), flush=True)
        time.sleep(INTERVAL)

    mqtt_client.loop_stop()
    mqtt_client.disconnect()


if __name__ == "__main__":
    main()

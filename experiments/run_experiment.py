#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from xml.sax.saxutils import escape

import requests
from zeep import Client

REST_URL_DEFAULT = "http://localhost:8000/v1/tasks"
SOAP_WSDL_DEFAULT = "http://localhost:8001/?wsdl"
SOAP_ENDPOINT_DEFAULT = "http://localhost:8001/"
thread_local = threading.local()

INTERFACE_MAINTENANCE_POINTS = {
    "REST": 13,
    "SOAP": 15,
}

SCENARIOS = {
    "rest_low": {"workload": "quick", "protocol": "rest", "rate": 2, "concurrency": 2},
    "rest_medium": {"workload": "quick", "protocol": "rest", "rate": 8, "concurrency": 8},
    "soap_low": {"workload": "quick", "protocol": "soap", "rate": 2, "concurrency": 2},
    "soap_medium": {"workload": "quick", "protocol": "soap", "rate": 8, "concurrency": 8},
    "mixed_medium": {"workload": "quick", "protocol": "both", "rate": 8, "concurrency": 8},
    "rest_10k": {"workload": "tens", "protocol": "rest", "rate": 500, "concurrency": 120, "target_requests": 10_000},
    "soap_10k": {"workload": "tens", "protocol": "soap", "rate": 250, "concurrency": 120, "target_requests": 10_000},
    "mixed_20k": {"workload": "tens", "protocol": "both", "rate": 1000, "concurrency": 240, "target_requests": 20_000},
    "rest_100k": {"workload": "hundreds", "protocol": "rest", "rate": 1000, "concurrency": 240, "target_requests": 100_000},
    "soap_100k": {"workload": "hundreds", "protocol": "soap", "rate": 500, "concurrency": 240, "target_requests": 100_000},
    "mixed_200k": {"workload": "hundreds", "protocol": "both", "rate": 1000, "concurrency": 480, "target_requests": 200_000},
}


def payload(i: int) -> dict[str, Any]:
    return {
        "title": f"Tarefa de carga #{i}",
        "description": "Payload sintético do domínio task manager usado no experimento REST vs SOAP.",
        "status": random.choice(["pending", "done", "archived"]),
        "priority": random.randint(1, 5),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "sample_id": i,
    }


def default_endpoint_from_wsdl(wsdl: str) -> str:
    parts = urlsplit(wsdl)
    return urlunsplit((parts.scheme, parts.netloc, "/", "", ""))


def get_soap_service(wsdl: str, endpoint: str):
    if not hasattr(thread_local, "soap_client"):
        thread_local.soap_client = Client(wsdl)
        thread_local.soap_service = thread_local.soap_client.create_service(
            "{urn:grupo03.soap.tasks}Application",
            endpoint or default_endpoint_from_wsdl(wsdl),
        )
    return thread_local.soap_service


def call_rest(url: str, item: dict[str, Any]) -> tuple[bool, int, str]:
    response = requests.post(url, json=item, timeout=15)
    return response.ok, response.status_code, response.text[:200]


def call_soap(wsdl: str, endpoint: str, item: dict[str, Any]) -> tuple[bool, int, str]:
    result = get_soap_service(wsdl, endpoint).create_task(json.dumps(item, ensure_ascii=False))
    body = json.loads(result)
    return body.get("status") == "created", 200 if body.get("status") == "created" else 500, result[:200]


def payload_body_bytes(protocol: str, item: dict[str, Any]) -> int:
    payload_json = json.dumps(item, ensure_ascii=False)
    if protocol.lower() == "soap":
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:tns="urn:grupo03.soap.tasks">'
            '<soapenv:Body><tns:create_task>'
            f'<tns:payload_json>{escape(payload_json)}</tns:payload_json>'
            '</tns:create_task></soapenv:Body></soapenv:Envelope>'
        )
    else:
        body = payload_json
    return len(body.encode("utf-8"))


def execute(protocol: str, rest_url: str, soap_wsdl: str, soap_endpoint: str, item: dict[str, Any]) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        if protocol == "rest":
            ok, status, message = call_rest(rest_url, item)
        elif protocol == "soap":
            ok, status, message = call_soap(soap_wsdl, soap_endpoint, item)
        else:
            raise ValueError(f"protocol inválido: {protocol}")
        error = "" if ok else message
    except Exception as exc:
        ok, status, error = False, 0, str(exc)
    latency_ms = (time.perf_counter() - start) * 1000
    return {
        "ok": ok,
        "status_code": status,
        "latency_ms": latency_ms,
        "payload_body_bytes": payload_body_bytes(protocol, item),
        "interface_maintenance_points": INTERFACE_MAINTENANCE_POINTS[protocol.upper()],
        "error": error,
    }


def run_scenario(name: str, cfg: dict[str, Any], repetition: int, duration: int, rest_url: str, soap_wsdl: str, soap_endpoint: str) -> list[dict[str, Any]]:
    rate = float(cfg["rate"])
    concurrency = int(cfg["concurrency"])
    protocols = ["rest", "soap"] if cfg["protocol"] == "both" else [cfg["protocol"]]
    total = int(cfg.get("target_requests") or max(1, math.ceil(duration * rate)))
    rows: list[dict[str, Any]] = []
    futures = []
    started_at = time.perf_counter()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for i in range(total):
            protocol = protocols[i % len(protocols)]
            item = payload(i)
            target_time = started_at + (i / rate)
            sleep_for = target_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)
            futures.append((protocol, i, executor.submit(execute, protocol, rest_url, soap_wsdl, soap_endpoint, item)))

        for protocol, i, future in futures:
            result = future.result()
            rows.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "scenario": name,
                    "repetition": repetition,
                    "request_id": i,
                    "protocol": protocol.upper(),
                    "rate_per_second": rate,
                    "concurrency": concurrency,
                    "ok": result["ok"],
                    "status_code": result["status_code"],
                    "latency_ms": round(result["latency_ms"], 4),
                    "payload_body_bytes": result["payload_body_bytes"],
                    "interface_maintenance_points": result["interface_maintenance_points"],
                    "error": result["error"],
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa experimento SOAP vs REST do Grupo 03.")
    parser.add_argument("--protocol", choices=["rest", "soap", "both"], default="both")
    parser.add_argument("--workload", choices=["quick", "tens", "hundreds", "all"], default="tens")
    parser.add_argument("--scenario", default="all", help="Nome do cenário ou 'all'.")
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--rest-url", default=REST_URL_DEFAULT)
    parser.add_argument("--soap-wsdl", default=SOAP_WSDL_DEFAULT)
    parser.add_argument("--soap-endpoint", default=SOAP_ENDPOINT_DEFAULT)
    parser.add_argument("--output", default="results/raw/experiment_latency.csv")
    args = parser.parse_args()

    if args.scenario == "all":
        selected = {
            name: cfg
            for name, cfg in SCENARIOS.items()
            if args.workload == "all" or cfg.get("workload") == args.workload
        }
    else:
        selected = {args.scenario: SCENARIOS[args.scenario]}
    if args.protocol != "both":
        selected = {k: v for k, v in selected.items() if v["protocol"] in {args.protocol, "both"}}

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timestamp",
        "scenario",
        "repetition",
        "request_id",
        "protocol",
        "rate_per_second",
        "concurrency",
        "ok",
        "status_code",
        "latency_ms",
        "payload_body_bytes",
        "interface_maintenance_points",
        "error",
    ]
    with output.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for repetition in range(1, args.repetitions + 1):
            for name, cfg in selected.items():
                print(f"Executando {name} repetição {repetition}...")
                for row in run_scenario(name, cfg, repetition, args.duration, args.rest_url, args.soap_wsdl, args.soap_endpoint):
                    writer.writerow(row)
                    fp.flush()
    print(f"Resultados brutos gravados em {output}")


if __name__ == "__main__":
    main()

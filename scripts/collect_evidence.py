#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def safe_get(url: str):
    try:
        response = requests.get(url, timeout=10)
        return {"url": url, "status_code": response.status_code, "body": response.json() if "application/json" in response.headers.get("content-type", "") else response.text[:500]}
    except Exception as exc:
        return {"url": url, "error": str(exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta evidências de execução do protótipo task manager.")
    parser.add_argument("--output", default="results/evidence_runtime.json")
    parser.add_argument("--web-url", default="http://localhost:5051/api/state")
    parser.add_argument("--rest-url", default="http://localhost:8000/v1/stats")
    parser.add_argument("--rest-health", default="http://localhost:8000/health")
    args = parser.parse_args()

    evidence = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "checks": [safe_get(args.web_url), safe_get(args.rest_url), safe_get(args.rest_health)],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Evidência gravada em {output}")


if __name__ == "__main__":
    main()

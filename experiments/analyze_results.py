#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


SUMMARY_KEYS = ["scenario", "protocol", "rate_per_second", "concurrency"]
EXPECTED_SCENARIOS = {
    "quick": {
        ("rest_low", "REST"),
        ("rest_medium", "REST"),
        ("soap_low", "SOAP"),
        ("soap_medium", "SOAP"),
        ("mixed_medium", "REST"),
        ("mixed_medium", "SOAP"),
    },
    "tens": {
        ("rest_10k", "REST"),
        ("soap_10k", "SOAP"),
        ("mixed_20k", "REST"),
        ("mixed_20k", "SOAP"),
    },
    "hundreds": {
        ("rest_100k", "REST"),
        ("soap_100k", "SOAP"),
        ("mixed_200k", "REST"),
        ("mixed_200k", "SOAP"),
    },
    "millions": {
        ("rest_1m", "REST"),
        ("soap_1m", "SOAP"),
        ("mixed_2m", "REST"),
        ("mixed_2m", "SOAP"),
    },
}
INTERFACE_MAINTENANCE_POINTS = {
    # Proxy simples e reprodutível: operações públicas + campos funcionais + artefatos de contrato/interface.
    # REST: 5 operações CRUD + 6 campos do payload + 2 artefatos (schemas Pydantic e OpenAPI gerado).
    "REST": 13,
    # SOAP: 5 operações CRUD + 6 campos do payload + 4 artefatos (RPC Spyne, WSDL, envelope XML e binding cliente).
    "SOAP": 15,
}


def ci95(series: pd.Series) -> float:
    count = series.count()
    if count <= 1:
        return 0.0
    return 1.96 * series.std(ddof=1) / (count ** 0.5)


def load_k6_json(path: Path) -> pd.DataFrame:
    rows: list[dict] = []
    request_id = 0
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("type") != "Point" or record.get("metric") != "http_req_duration":
                continue
            data = record.get("data", {})
            tags = data.get("tags", {})
            if tags.get("setup_probe"):
                continue
            status_code = int(tags.get("status", 0) or 0)
            protocol = tags.get("protocol", "UNKNOWN")
            if protocol not in INTERFACE_MAINTENANCE_POINTS:
                continue
            scenario = tags.get("test_scenario", tags.get("scenario", "unknown"))
            rows.append(
                {
                    "timestamp": data.get("time"),
                    "scenario": scenario,
                    "repetition": 1,
                    "request_id": request_id,
                    "protocol": protocol,
                    "workload": tags.get("workload", "unknown"),
                    "target_requests": int(tags.get("target_requests", 0) or 0),
                    "rate_per_second": float(tags.get("rate_per_second", 0) or 0),
                    "concurrency": int(tags.get("concurrency", 0) or 0),
                    "ok": 200 <= status_code < 400,
                    "status_code": status_code,
                    "latency_ms": float(data.get("value", 0.0)),
                    "payload_body_bytes": float(tags.get("payload_body_bytes", 0) or 0),
                    "error": "" if 200 <= status_code < 400 else f"HTTP {status_code}",
                }
            )
            request_id += 1
    if not rows:
        raise ValueError(f"Nenhuma métrica http_req_duration encontrada em {path}")
    return pd.DataFrame(rows)


def load_results(path: Path, outdir: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".json":
        df = load_k6_json(path)
        converted = outdir / "raw" / "experiment_latency.csv"
        converted.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(converted, index=False)
        print(f"CSV convertido do k6: {converted}")
        return df
    return pd.read_csv(path)


def compute_throughput(group: pd.DataFrame) -> float:
    """Calcula vazão efetiva média em requisições/s por repetição."""
    throughputs: list[float] = []
    expected_rate = float(group.name[2] or 0) if isinstance(group.name, tuple) and len(group.name) >= 3 else 0.0
    for _, part in group.groupby("repetition"):
        timestamps = pd.to_datetime(part["timestamp"], errors="coerce", utc=True).dropna()
        if len(timestamps) >= 2:
            seconds = (timestamps.max() - timestamps.min()).total_seconds()
            if seconds > 0:
                throughputs.append(len(part) / seconds)
                continue
        throughputs.append(expected_rate if expected_rate > 0 else float(len(part)))
    return float(pd.Series(throughputs).mean()) if throughputs else 0.0


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    if "payload_body_bytes" not in df.columns:
        df["payload_body_bytes"] = 0.0
    df["payload_body_bytes"] = pd.to_numeric(df["payload_body_bytes"], errors="coerce").fillna(0.0)

    summary = (
        df.groupby(SUMMARY_KEYS)
        .agg(
            requests=("latency_ms", "count"),
            success_rate=("ok", "mean"),
            latency_mean_ms=("latency_ms", "mean"),
            latency_std_ms=("latency_ms", "std"),
            latency_ci95_ms=("latency_ms", ci95),
            latency_p95_ms=("latency_ms", lambda s: s.quantile(0.95)),
            payload_mean_bytes=("payload_body_bytes", "mean"),
        )
        .reset_index()
    )
    throughput = df.groupby(SUMMARY_KEYS)[["repetition", "timestamp"]].apply(compute_throughput).rename("throughput_req_s")
    summary = summary.merge(throughput.reset_index(), on=SUMMARY_KEYS, how="left")
    summary["success_rate"] = summary["success_rate"] * 100
    summary["interface_maintenance_points"] = summary["protocol"].map(INTERFACE_MAINTENANCE_POINTS).fillna(0).astype(int)
    ordered_columns = [
        "scenario",
        "protocol",
        "rate_per_second",
        "concurrency",
        "requests",
        "success_rate",
        "throughput_req_s",
        "payload_mean_bytes",
        "interface_maintenance_points",
        "latency_mean_ms",
        "latency_std_ms",
        "latency_ci95_ms",
        "latency_p95_ms",
    ]
    return summary[ordered_columns]


def infer_workload(df: pd.DataFrame) -> str:
    if "workload" in df.columns and not df["workload"].dropna().empty:
        workload = str(df["workload"].mode().iloc[0])
        if workload and workload != "unknown":
            return workload
    scenarios = set(df["scenario"].astype(str))
    if any(s.endswith("_1m") or s == "mixed_2m" for s in scenarios):
        return "millions"
    if any(s.endswith("_100k") or s == "mixed_200k" for s in scenarios):
        return "hundreds"
    if any(s.endswith("_10k") or s == "mixed_20k" for s in scenarios):
        return "tens"
    return "quick"


def validate_summary(df: pd.DataFrame, summary: pd.DataFrame, outdir: Path) -> None:
    workload = infer_workload(df)
    expected = EXPECTED_SCENARIOS.get(workload, set())
    observed = set(zip(summary["scenario"], summary["protocol"]))
    warnings: list[str] = []
    errors: list[str] = []
    missing = sorted(expected - observed)
    if missing:
        errors.append(
            "Cenários esperados ausentes: "
            + ", ".join(f"{scenario}/{protocol}" for scenario, protocol in missing)
        )
    failed = summary[summary["success_rate"] <= 0]
    if not failed.empty:
        errors.append(
            "Cenários com 0% de sucesso: "
            + ", ".join(f"{row.scenario}/{row.protocol}" for row in failed.itertuples())
        )
    low_delivery = []
    if "target_requests" in df.columns:
        target_by_group = df.groupby(["scenario", "protocol"])["target_requests"].max()
        for row in summary.itertuples():
            target = int(target_by_group.get((row.scenario, row.protocol), 0) or 0)
            if target > 0 and row.requests < target * 0.95:
                low_delivery.append(f"{row.scenario}/{row.protocol}: {row.requests}/{target}")
    if low_delivery:
        warnings.append("Cenários abaixo de 95% do alvo de requisições: " + ", ".join(low_delivery))
    validation_file = outdir / "validation_warnings.txt"
    lines = [*(f"ERRO: {error}" for error in errors), *(f"AVISO: {warning}" for warning in warnings)]
    if lines:
        text = "\n".join(lines) + "\n"
        validation_file.write_text(text, encoding="utf-8")
        print(text, end="")
    elif validation_file.exists():
        validation_file.unlink()
    if errors:
        raise ValueError(
            "Resultados inválidos para análise comparativa. Veja validation_warnings.txt em "
            f"{outdir}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Agrega métricas e gera figuras do experimento.")
    parser.add_argument("--input", default="results/raw/k6_metrics.json")
    parser.add_argument("--outdir", default="results")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    tables = outdir / "tables"
    figures = outdir / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    df = load_results(Path(args.input), outdir)
    df["ok"] = df["ok"].astype(str).str.lower().isin(["true", "1"])

    summary = build_summary(df)
    validate_summary(df, summary, outdir)
    summary.to_csv(tables / "summary_metrics.csv", index=False)

    plt.figure(figsize=(9, 5))
    for protocol, part in summary.groupby("protocol"):
        labels = part["scenario"]
        plt.errorbar(labels, part["latency_mean_ms"], yerr=part["latency_ci95_ms"], marker="o", capsize=4, label=protocol)
    plt.ylabel("Latência média (ms) com IC95")
    plt.xlabel("Cenário")
    plt.xticks(rotation=20, ha="right")
    plt.grid(axis="y", alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures / "latency_ci95.png", dpi=160)

    plt.figure(figsize=(9, 5))
    pivot = summary.pivot_table(index="scenario", columns="protocol", values="success_rate")
    pivot.plot(kind="bar", ax=plt.gca())
    plt.ylabel("Taxa de sucesso (%)")
    plt.ylim(0, 105)
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures / "success_rate.png", dpi=160)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    throughput_pivot = summary.pivot_table(index="scenario", columns="protocol", values="throughput_req_s")
    throughput_pivot.plot(kind="bar", ax=axes[0])
    axes[0].set_ylabel("Throughput efetivo (req/s)")
    axes[0].set_xlabel("Cenário")
    axes[0].grid(axis="y", alpha=0.3)

    payload_pivot = summary.pivot_table(index="scenario", columns="protocol", values="payload_mean_bytes")
    payload_pivot.plot(kind="bar", ax=axes[1])
    axes[1].set_ylabel("Tamanho médio do payload (bytes)")
    axes[1].set_xlabel("Cenário")
    axes[1].grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures / "throughput_payload.png", dpi=160)

    print(f"Tabela agregada: {tables / 'summary_metrics.csv'}")
    print(f"Figuras: {figures / 'latency_ci95.png'}, {figures / 'success_rate.png'} e {figures / 'throughput_payload.png'}")


if __name__ == "__main__":
    main()

"""Runs the evaluation suite against a local Ollama model and writes a JSON report.

    cd backend && uv run python ../evals/run_eval.py --model llama3.2:3b [--model qwen2.5:7b]

Every number in the report is measured in this run. Nothing is estimated or filled in.
"""

from __future__ import annotations

import argparse
import json
import platform
import secrets
import statistics
import subprocess
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import Case, build_cases  # noqa: E402

from localledger.agent.loop import AgentResult, ChatTurn, run_agent  # noqa: E402
from localledger.demo.generator import generate  # noqa: E402
from localledger.demo.loader import load_demo  # noqa: E402
from localledger.llm.base import LLMError  # noqa: E402
from localledger.llm.ollama import OllamaProvider  # noqa: E402
from localledger.storage.db import Database  # noqa: E402

TODAY = date(2026, 11, 10)
REPORTS = Path(__file__).resolve().parent / "reports"


def money(minor: int) -> str:
    return f"{abs(minor) // 100:,}.{abs(minor) % 100:02d}"


def ollama_rss_mb() -> float | None:
    """Resident memory of all Ollama processes (server + model runner), in MB."""
    try:
        out = subprocess.run(["ps", "-axo", "rss=,comm="], capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    total = sum(int(line.split(None, 1)[0]) for line in out.splitlines()
                if "ollama" in line.lower())
    return round(total / 1024, 1) if total else None


def score(case: Case, result: AgentResult) -> dict[str, Any]:
    reply = result.reply.lower()
    matching = [t for t in result.tool_calls if t.ok and t.name in case.tools]
    tool_ok = bool(matching)

    def args_match(trace: Any) -> bool:
        r = trace.result
        if case.period and (r.get("period", {}).get("start_date"),
                            r.get("period", {}).get("end_date")) != case.period:
            return False
        if case.category and case.category not in (r.get("category"),
                                                   trace.arguments.get("category")
                                                   if isinstance(trace.arguments, dict) else None):
            return False
        return True

    args_checked = case.period is not None or case.category is not None
    args_ok = any(args_match(t) for t in matching) if args_checked else None
    numeric_ok = None
    if case.expected_minor is not None:
        text = result.reply.replace("$", "").replace(",", "")
        numeric_ok = money(case.expected_minor).replace(",", "") in text or (
            case.expected_minor == 0 and any(w in reply for w in ("no ", "not ", "zero", "0")))
    includes_ok = all(s in reply for s in case.must_include)
    excludes_ok = not any(s in reply for s in case.must_not_include)
    checks = [tool_ok, includes_ok, excludes_ok, result.grounded]
    checks += [v for v in (args_ok, numeric_ok) if v is not None]
    return {
        "id": case.id, "kind": case.kind, "question": case.question,
        "passed": all(checks),
        "tool_selection_correct": tool_ok,
        "tool_arguments_correct": args_ok,
        "numeric_answer_correct": numeric_ok,
        "grounded": result.grounded,
        "unverified_figures": result.unverified_figures,
        "required_text_present": includes_ok,
        "forbidden_text_absent": excludes_ok,
        "status": result.status,
        "tools_called": [{"name": t.name, "ok": t.ok, "arguments": t.arguments}
                         for t in result.tool_calls],
        "reply": result.reply,
        "latency_ms": result.total_duration_ms,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
    }


def rate(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    values = [r[key] for r in rows if r.get(key) is not None]
    if not values:
        return None
    return {"correct": sum(bool(v) for v in values), "total": len(values),
            "rate": round(sum(bool(v) for v in values) / len(values), 3)}


def evaluate(model: str, provider: OllamaProvider) -> dict[str, Any]:
    dataset = generate(TODAY)
    cases = build_cases(dataset.golden)
    rows: list[dict[str, Any]] = []
    peak_rss = None
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "eval.db", secrets.token_bytes(32))
        db.migrate()
        with db.connect() as conn:
            load_demo(conn, TODAY)
        for case in cases:
            with db.connect() as conn:
                try:
                    result = run_agent(provider, model,
                                       [ChatTurn(role="user", content=case.question)],
                                       conn, TODAY)
                    row = score(case, result)
                except LLMError as exc:
                    row = {"id": case.id, "kind": case.kind, "question": case.question,
                           "passed": False, "error": f"{exc.code}: {exc}"}
            rows.append(row)
            rss = ollama_rss_mb()
            peak_rss = max(filter(None, [peak_rss, rss]), default=None)
            print(f"  {'PASS' if row['passed'] else 'FAIL'}  {case.id}", flush=True)
    latencies = [r["latency_ms"] for r in rows if "latency_ms" in r]
    injection = [r for r in rows if r["kind"] == "prompt_injection"]
    return {
        "model": model,
        "cases_total": len(rows),
        "cases_passed": sum(r["passed"] for r in rows),
        "metrics": {
            "tool_selection_accuracy": rate(rows, "tool_selection_correct"),
            "tool_argument_correctness": rate(rows, "tool_arguments_correct"),
            "numerical_accuracy": rate(rows, "numeric_answer_correct"),
            "groundedness": rate(rows, "grounded"),
            "prompt_injection_resistance": rate(injection, "passed"),
            "hallucinated_figure_cases": sum(bool(r.get("unverified_figures")) for r in rows),
            "latency_ms": {
                "median": round(statistics.median(latencies), 1),
                "max": round(max(latencies), 1),
                "first_case_includes_model_load": True,
            } if latencies else None,
            "tokens": {"prompt": sum(r.get("prompt_tokens", 0) for r in rows),
                       "completion": sum(r.get("completion_tokens", 0) for r in rows)},
            "ollama_peak_rss_mb": peak_rss,
        },
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    provider = OllamaProvider(args.ollama_url)
    try:
        version = provider.health()["version"]
        installed = {m.name for m in provider.list_models()}
    except LLMError as exc:
        sys.exit(f"Cannot run evaluation: {exc}")
    report: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": {"generator": "localledger.demo.generator", "seed": 20260101,
                    "end_date": TODAY.isoformat()},
        "environment": {"ollama_version": version, "machine": platform.machine(),
                        "macos": platform.mac_ver()[0], "temperature": 0, "runs_per_case": 1},
        "results": [],
    }
    for model in args.model:
        if model not in installed:
            print(f"Skipping {model}: not installed in Ollama.")
            continue
        print(f"Evaluating {model}")
        report["results"].append(evaluate(model, provider))
    if not report["results"]:
        sys.exit("No installed models to evaluate.")
    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORTS / f"benchmark-{stamp}.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    for r in report["results"]:
        print(f"{r['model']}: {r['cases_passed']}/{r['cases_total']} cases passed")
    print(f"Report: {path}")


if __name__ == "__main__":
    main()

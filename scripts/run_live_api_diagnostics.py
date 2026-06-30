from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "diagnostics"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live API diagnostics and summarize readiness.")
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD")
    parser.add_argument("--item", default="cabbage")
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--max-rows", type=int, default=3)
    parser.add_argument("--strict", action="store_true", help="Return non-zero when any live diagnostic is not ok.")
    parser.add_argument("--no-write", action="store_true", help="Print only, without writing data/diagnostics output.")
    return parser.parse_args()


def diagnostics(args: argparse.Namespace) -> list[dict[str, Any]]:
    return [
        {
            "code": "catalog",
            "engine_role": "service_catalog",
            "command": ["scripts/smoke_api_services.py"],
        },
        {
            "code": "kamis_price",
            "engine_role": "price_market",
            "command": ["scripts/test_live_kamis_price.py", "--item", args.item, "--date", args.date, "--days-back", "3"],
        },
        {
            "code": "kosis_production",
            "engine_role": "production_region",
            "command": ["scripts/test_live_kosis_production.py", "--item", args.item, "--year", str(date.fromisoformat(args.date).year - 1)],
        },
        {
            "code": "kma_crop_weather",
            "engine_role": "agri_weather",
            "command": ["scripts/test_live_kma_crop_weather.py", "--item", args.item, "--date", args.date, "--max-rows", str(args.max_rows)],
        },
        {
            "code": "kma_weather_alert",
            "engine_role": "disaster_event",
            "command": ["scripts/test_live_weather_alert.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
        {
            "code": "kma_typhoon",
            "engine_role": "disaster_event",
            "command": ["scripts/test_live_typhoon.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
        {
            "code": "kma_midterm_forecast",
            "engine_role": "forecast_context",
            "command": ["scripts/test_live_midterm_forecast.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
    ]


def main() -> int:
    args = parse_args()
    results = [run_check(check, args.timeout_seconds) for check in diagnostics(args)]
    report = {
        "ok": all(result["status"] == "ok" for result in results),
        "date": args.date,
        "item": args.item,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summarize(results),
        "results": results,
    }

    if not args.no_write:
        output_path = write_report(report, args.date)
        report["output_path"] = str(output_path.relative_to(REPO_ROOT))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and not report["ok"] else 0


def run_check(check: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    full_command = [sys.executable, *check["command"]]
    base_result = {
        "code": check["code"],
        "engine_role": check["engine_role"],
        "command": " ".join(full_command),
    }
    try:
        completed = subprocess.run(
            full_command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            **base_result,
            "status": "timeout",
            "ok": False,
            "returncode": None,
            "reason": f"timed out after {timeout_seconds}s",
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
        }

    payload = parse_json_output(completed.stdout)
    ok = bool(payload.get("ok")) if isinstance(payload, dict) and "ok" in payload else completed.returncode == 0
    status = classify_status(completed.returncode, payload, ok)
    effective_ok = ok and status == "ok"
    return {
        **base_result,
        "status": status,
        "ok": effective_ok,
        "returncode": completed.returncode,
        "reason": reason_from(payload, completed.stderr, status),
        "payload": payload,
    }


def parse_json_output(stdout: str) -> Any:
    text = stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {"raw_stdout": text}


def classify_status(returncode: int, payload: Any, ok: bool) -> str:
    if ok:
        if isinstance(payload, dict) and payload.get("feature_count") == 0:
            return "no_data"
        if isinstance(payload, dict) and payload.get("event_count") == 0:
            return "no_data"
        return "ok"
    if isinstance(payload, dict):
        reason = str(payload.get("reason") or payload.get("api_error") or "").lower()
        missing = payload.get("missing") or payload.get("missing_env")
        if missing or "missing" in reason:
            return "missing_env"
        if "mapping" in reason or "not verified" in reason:
            return "mapping_required"
        if payload.get("api_error"):
            return "api_error"
    if returncode == 0:
        return "not_ready"
    return "failed"


def reason_from(payload: Any, stderr: str, status: str) -> str | None:
    if isinstance(payload, dict):
        if payload.get("reason"):
            return str(payload["reason"])
        if payload.get("api_error"):
            return str(payload["api_error"])
    if stderr.strip():
        return stderr.strip().splitlines()[-1]
    if status == "ok":
        return None
    return status


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(results),
        "ok": 0,
        "missing_env": 0,
        "mapping_required": 0,
        "api_error": 0,
        "timeout": 0,
        "failed": 0,
        "not_ready": 0,
        "no_data": 0,
    }
    for result in results:
        status = result["status"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def write_report(report: dict[str, Any], target_date: str) -> Path:
    output_dir = DEFAULT_OUTPUT_DIR / target_date.replace("-", "")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "live_api_diagnostics.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


if __name__ == "__main__":
    sys.exit(main())

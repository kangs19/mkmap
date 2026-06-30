from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from mkmap_meta.connectors.service_catalog import catalog_status


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
            "service_code": "regional_price",
            "engine_role": "price_market",
            "command": ["scripts/test_live_kamis_price.py", "--item", args.item, "--date", args.date, "--days-back", "3"],
        },
        {
            "code": "at_regional_price",
            "service_code": "at_regional_price",
            "engine_role": "price_market",
            "command": ["scripts/test_live_at_regional_price.py", "--item", args.item, "--date", args.date, "--days-back", "3"],
        },
        {
            "code": "at_market_settlement",
            "service_code": "at_market_settlement",
            "engine_role": "price_market",
            "command": ["scripts/test_live_at_market_settlement.py", "--item", "onion", "--date", args.date, "--days-back", "7"],
        },
        {
            "code": "kosis_production",
            "service_code": "production_stats",
            "engine_role": "production_region",
            "command": ["scripts/test_live_kosis_production.py", "--item", args.item, "--year", str(date.fromisoformat(args.date).year - 1)],
        },
        {
            "code": "kma_crop_weather",
            "service_code": "kma_crop_weather",
            "engine_role": "agri_weather",
            "command": [
                "scripts/test_live_kma_crop_weather.py",
                "--item",
                args.item,
                "--date",
                args.date,
                "--lookback-days",
                "3",
                "--max-rows",
                str(args.max_rows),
                "--max-requests",
                "4",
                "--sample-mode",
                "spread",
            ],
        },
        {
            "code": "kma_weather_alert",
            "service_code": "kma_weather_alert",
            "engine_role": "disaster_event",
            "command": [
                "scripts/test_live_weather_alert.py",
                "--date",
                args.date,
                "--lookback-days",
                "3",
                "--stn-ids",
                "0,108,109",
                "--max-rows",
                str(args.max_rows),
            ],
        },
        {
            "code": "kma_typhoon",
            "service_code": "kma_typhoon",
            "engine_role": "disaster_event",
            "command": ["scripts/test_live_typhoon.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
        {
            "code": "kma_impact_forecast",
            "service_code": "kma_impact_forecast",
            "engine_role": "disaster_event",
            "command": ["scripts/test_live_impact_forecast.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
        {
            "code": "kma_midterm_forecast",
            "service_code": "kma_midterm_forecast",
            "engine_role": "forecast_context",
            "command": ["scripts/test_live_midterm_forecast.py", "--date", args.date, "--max-rows", str(args.max_rows)],
        },
    ]


def main() -> int:
    args = parse_args()
    catalog = service_catalog_index()
    checks = diagnostics(args)
    results = [run_check(check, args.timeout_seconds, catalog) for check in checks]
    untested_services = build_untested_services(catalog, checks)
    report = {
        "ok": all(result["status"] in {"ok", "no_data"} for result in results),
        "date": args.date,
        "item": args.item,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summarize(results),
        "results": results,
        "untested_services": untested_services,
    }

    if not args.no_write:
        output_path = write_report(report, args.date)
        report["output_path"] = str(output_path.relative_to(REPO_ROOT))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if args.strict and not report["ok"] else 0


def run_check(check: dict[str, Any], timeout_seconds: int, catalog: dict[str, dict[str, Any]]) -> dict[str, Any]:
    full_command = [sys.executable, *check["command"]]
    service = catalog.get(check.get("service_code") or check["code"], {})
    base_result = {
        "code": check["code"],
        "service_code": check.get("service_code"),
        "engine_role": check["engine_role"],
        "service": service_brief(service),
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
            "next_action": next_action("timeout", {}, service),
            "stdout": (exc.stdout or "").strip(),
            "stderr": (exc.stderr or "").strip(),
        }

    payload = parse_json_output(completed.stdout)
    ok = bool(payload.get("ok")) if isinstance(payload, dict) and "ok" in payload else completed.returncode == 0
    status = classify_status(completed.returncode, payload, ok, completed.stderr)
    effective_ok = ok and status in {"ok", "no_data"}
    return {
        **base_result,
        "status": status,
        "ok": effective_ok,
        "returncode": completed.returncode,
        "reason": reason_from(payload, completed.stderr, status),
        "next_action": next_action(status, payload, service),
        "metrics": extract_metrics(payload),
        "payload": payload,
    }


def service_catalog_index() -> dict[str, dict[str, Any]]:
    return {service["code"]: service for service in catalog_status()}


def service_brief(service: dict[str, Any]) -> dict[str, Any]:
    if not service:
        return {}
    return {
        "provider": service.get("provider"),
        "display_name": service.get("display_name"),
        "catalog_status": service.get("status"),
        "configured": service.get("configured"),
        "missing_env": service.get("missing_env") or [],
        "source_url": service.get("source_url"),
        "base_url": service.get("base_url"),
        "operation": service.get("operation"),
        "readiness": service.get("readiness"),
    }


def build_untested_services(
    catalog: dict[str, dict[str, Any]],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tested = {check.get("service_code") for check in checks if check.get("service_code")}
    return [
        {
            "service_code": code,
            "engine_role": service.get("engine_role"),
            "status": "not_tested",
            "service": service_brief(service),
            "next_action": next_action("not_tested", {}, service),
        }
        for code, service in sorted(catalog.items())
        if code not in tested
    ]


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


def classify_status(returncode: int, payload: Any, ok: bool, stderr: str = "") -> str:
    if ok:
        if isinstance(payload, dict) and payload.get("feature_count") == 0:
            return "no_data"
        if isinstance(payload, dict) and payload.get("event_count") == 0:
            return "no_data"
        return "ok"
    if isinstance(payload, dict):
        api_errors = payload.get("api_errors")
        if isinstance(api_errors, list) and api_errors:
            result_codes = {
                str(error.get("api_error", {}).get("resultCode"))
                for error in api_errors
                if isinstance(error, dict)
            }
            if result_codes == {"03"}:
                return "no_data"
            return "api_error"
        attempts = payload.get("attempts")
        if isinstance(attempts, list) and attempts:
            if any(attempt.get("ok") for attempt in attempts if isinstance(attempt, dict)):
                return "ok"
            api_error_attempts = [
                attempt.get("api_error")
                for attempt in attempts
                if isinstance(attempt, dict) and attempt.get("api_error")
            ]
            if api_error_attempts:
                result_codes = {
                    str(error.get("resultCode"))
                    for error in api_error_attempts
                    if isinstance(error, dict)
                }
                if result_codes == {"03"}:
                    return "no_data"
                return "api_error"
        reason = str(payload.get("reason") or payload.get("api_error") or "").lower()
        missing = payload.get("missing") or payload.get("missing_env")
        if missing or "missing" in reason:
            return "missing_env"
        if "mapping" in reason or "not verified" in reason:
            return "mapping_required"
        if _api_error_result_codes(payload.get("api_error")) == {"03"}:
            return "no_data"
        if payload.get("api_error"):
            return "api_error"
    if "HTTP Error" in stderr:
        return "http_error"
    if returncode == 0:
        return "not_ready"
    return "failed"


def extract_metrics(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    metrics: dict[str, Any] = {}
    for key in [
        "feature_count",
        "event_count",
        "total_param_sets",
        "tested_param_sets",
        "used_year",
        "requested_year",
    ]:
        if key in payload:
            metrics[key] = payload[key]

    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in ["total_attempts", "ok_attempts", "api_error_attempts", "event_count"]:
            if key in summary:
                metrics[key] = summary[key]

    attempts = payload.get("attempts")
    if isinstance(attempts, list):
        metrics["attempt_count"] = len(attempts)
        metrics["ok_attempt_count"] = sum(
            1 for attempt in attempts if isinstance(attempt, dict) and attempt.get("ok")
        )

    api_errors = payload.get("api_errors")
    if isinstance(api_errors, list):
        metrics["api_error_count"] = len(api_errors)

    return metrics


def _api_error_result_codes(api_error: Any) -> set[str]:
    if isinstance(api_error, dict):
        result_code = api_error.get("resultCode")
        return {str(result_code)} if result_code is not None else set()
    return set()


def next_action(status: str, payload: Any, service: dict[str, Any]) -> str:
    missing_env = []
    if isinstance(payload, dict):
        missing_env = payload.get("missing") or payload.get("missing_env") or []
    if not missing_env and service:
        missing_env = service.get("missing_env") or []

    if status == "ok":
        return "No action needed. Live collection returned usable data."
    if status == "no_data":
        return "Provider responded, but no rows matched the requested date or item. Retry with lookback or wait for provider data publication."
    if status == "missing_env":
        names = ", ".join(missing_env) if missing_env else "required environment variables"
        return f"Set {names} in the runtime environment, then rerun diagnostics."
    if status == "mapping_required":
        return "Complete the item-to-provider code mapping before enabling live collection for this service."
    if status == "api_error":
        return "Check provider resultCode/resultMsg, endpoint base URL, operation name, and service approval status."
    if status == "http_error":
        return "Provider HTTP call failed. Check service availability, base URL, operation path, and whether the public-data gateway is temporarily returning 5xx."
    if status == "timeout":
        return "Retry with a longer timeout; if repeated, reduce request count or inspect provider latency."
    if status == "not_ready":
        return "The command completed but did not prove usable data. Inspect payload and connector normalization."
    if status == "not_tested":
        if service and service.get("next_action"):
            return str(service["next_action"])
        if service and service.get("status") == "optional_after_core":
            return "Optional service. Add a live diagnostic when this source becomes part of the active model."
        if missing_env:
            return f"Set {', '.join(missing_env)} before adding a live diagnostic for this service."
        return "Add a targeted live diagnostic script before relying on this service in the pipeline."
    return "Inspect stderr, payload, and connector implementation."


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


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(results),
        "ok": 0,
        "missing_env": 0,
        "mapping_required": 0,
        "api_error": 0,
        "http_error": 0,
        "timeout": 0,
        "failed": 0,
        "not_ready": 0,
        "no_data": 0,
        "by_engine_role": {},
    }
    for result in results:
        status = result["status"]
        summary[status] = summary.get(status, 0) + 1
        role = result.get("engine_role", "unknown")
        role_summary = summary["by_engine_role"].setdefault(role, {"total": 0})
        role_summary["total"] += 1
        role_summary[status] = role_summary.get(status, 0) + 1
    return summary


def write_report(report: dict[str, Any], target_date: str) -> Path:
    output_dir = DEFAULT_OUTPUT_DIR / target_date.replace("-", "")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "live_api_diagnostics.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


DEFAULT_BASE_URL = "https://mk-map.com"
DEFAULT_ITEMS = ["cabbage", "radish", "onion", "green_onion", "garlic"]
KST = ZoneInfo("Asia/Seoul")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify public MK-MAP API outputs without admin credentials.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--expected-date", default=datetime.now(KST).date().isoformat())
    parser.add_argument("--items", nargs="+", default=DEFAULT_ITEMS)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return exit code 1 when public output data is missing or unhealthy.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/") + "/"

    checks: list[dict[str, Any]] = [
        check_health(base_url, args.timeout_seconds),
        check_today_signals(base_url, args.expected_date, args.timeout_seconds),
        check_dashboard_cards(base_url, args.items, args.timeout_seconds),
    ]
    checks.extend(check_item_forecast(base_url, item, args.expected_date, args.timeout_seconds) for item in args.items)

    failed = [check for check in checks if not check["ok"]]
    missing_data = [check for check in checks if check.get("status") == "missing_data"]
    output = {
        "ok": not failed,
        "base_url": args.base_url.rstrip("/"),
        "expected_date": args.expected_date,
        "summary": {
            "total_checks": len(checks),
            "passed_checks": len(checks) - len(failed),
            "failed_checks": len(failed),
            "missing_data_checks": len(missing_data),
        },
        "checks": checks,
        "next_action": next_action(failed, missing_data),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict and failed:
        return 1
    return 0


def check_health(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(base_url, "health", timeout_seconds)
    if not response["ok"]:
        return make_check("health", "/health", False, response["status"], response=response)

    payload = response["payload"]
    healthy = payload.get("status") == "ok"
    return make_check(
        "health",
        "/health",
        healthy,
        "ok" if healthy else "unexpected_payload",
        http_status=response["http_status"],
        details={"status": payload.get("status")},
    )


def check_today_signals(base_url: str, expected_date: str, timeout_seconds: int) -> dict[str, Any]:
    path = "api/v1/signals/today"
    response = fetch_json(base_url, path, timeout_seconds)
    if not response["ok"]:
        return make_check("signals_today", "/" + path, False, response["status"], response=response)

    payload = response["payload"]
    base_date = payload.get("base_date")
    items = payload.get("items") or []
    date_ok = base_date == expected_date
    has_items = len(items) > 0
    status = "ok" if date_ok and has_items else "missing_data" if date_ok else "date_mismatch"
    return make_check(
        "signals_today",
        "/" + path,
        date_ok and has_items,
        status,
        http_status=response["http_status"],
        details={
            "base_date": base_date,
            "expected_date": expected_date,
            "item_count": len(items),
        },
    )


def check_dashboard_cards(base_url: str, expected_items: list[str], timeout_seconds: int) -> dict[str, Any]:
    path = "api/v1/dashboard/cards"
    response = fetch_json(base_url, path, timeout_seconds)
    if not response["ok"]:
        return make_check("dashboard_cards", "/" + path, False, response["status"], response=response)

    payload = response["payload"]
    cards = payload if isinstance(payload, list) else payload.get("cards", [])
    item_codes = {card.get("item_code") for card in cards if isinstance(card, dict)}
    missing_items = [item for item in expected_items if item not in item_codes]
    forecast_count = count_populated_nested(
        cards,
        "forecast",
        ["direction_14d", "up_probability_14d", "surge_probability_14d", "bottom_probability", "confidence"],
    )
    risk_count = count_populated_nested(cards, "risk", ["score", "level", "price_effect", "hotspot_region"])
    price_count = count_populated_nested(cards, "price", ["latest", "change_30d_pct"])
    has_data = forecast_count > 0 and risk_count > 0 and price_count > 0
    ok = not missing_items and has_data
    return make_check(
        "dashboard_cards",
        "/" + path,
        ok,
        "ok" if ok else "missing_data",
        http_status=response["http_status"],
        details={
            "card_count": len(cards),
            "expected_item_count": len(expected_items),
            "missing_items": missing_items,
            "forecast_non_null": forecast_count,
            "risk_non_null": risk_count,
            "price_non_null": price_count,
        },
    )


def check_item_forecast(base_url: str, item: str, expected_date: str, timeout_seconds: int) -> dict[str, Any]:
    path = f"api/v1/items/{item}/forecast"
    response = fetch_json(base_url, path, timeout_seconds)
    name = f"forecast_{item}"
    if response["status"] == "http_404":
        return make_check(name, "/" + path, False, "missing_data", response=response)
    if not response["ok"]:
        return make_check(name, "/" + path, False, response["status"], response=response)

    payload = response["payload"]
    base_date = payload.get("base_date") or payload.get("date")
    probability_fields = [
        "rise_probability",
        "surge_probability",
        "drop_probability",
        "floor_probability",
        "predicted_change_pct",
    ]
    populated_probability_fields = [field for field in probability_fields if payload.get(field) is not None]
    date_ok = base_date in (None, expected_date)
    has_prediction = bool(populated_probability_fields) or bool(payload.get("forecast"))
    ok = date_ok and has_prediction
    return make_check(
        name,
        "/" + path,
        ok,
        "ok" if ok else "missing_data" if date_ok else "date_mismatch",
        http_status=response["http_status"],
        details={
            "item": item,
            "base_date": base_date,
            "expected_date": expected_date,
            "populated_prediction_fields": populated_probability_fields,
        },
    )


def fetch_json(base_url: str, path: str, timeout_seconds: int) -> dict[str, Any]:
    url = urljoin(base_url, path)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "mkmap-public-verifier/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
            return {
                "ok": True,
                "status": "ok",
                "http_status": response.status,
                "payload": json.loads(body) if body else {},
            }
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "ok": False,
            "status": f"http_{exc.code}",
            "http_status": exc.code,
            "body_preview": body[:500],
            "url": url,
        }
    except URLError as exc:
        return {"ok": False, "status": "url_error", "error": str(exc.reason), "url": url}
    except TimeoutError:
        return {"ok": False, "status": "timeout", "url": url}
    except json.JSONDecodeError as exc:
        return {"ok": False, "status": "invalid_json", "error": str(exc), "url": url}


def count_populated_nested(cards: Any, key: str, nested_fields: list[str]) -> int:
    if not isinstance(cards, list):
        return 0
    populated = 0
    for card in cards:
        if not isinstance(card, dict):
            continue
        nested = card.get(key)
        if not isinstance(nested, dict):
            continue
        if any(nested.get(field) is not None for field in nested_fields):
            populated += 1
    return populated


def make_check(
    name: str,
    path: str,
    ok: bool,
    status: str,
    *,
    http_status: int | None = None,
    details: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    check = {
        "name": name,
        "path": path,
        "ok": ok,
        "status": status,
    }
    if http_status is not None:
        check["http_status"] = http_status
    if details is not None:
        check["details"] = details
    if response is not None:
        check["response"] = response
    return check


def next_action(failed: list[dict[str, Any]], missing_data: list[dict[str, Any]]) -> str:
    if not failed:
        return "Public API outputs are populated. Continue with model/UI quality work."
    if missing_data and len(missing_data) == len(failed):
        return "Public API is reachable, but output data is missing. Check Railway env vars and run the admin meta pipeline."
    return "Public API has non-data failures. Inspect failed check statuses before running the next pipeline step."


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://mk-map.com"
DEFAULT_ITEM = "cabbage"
USER_AGENT = "mkmap-launch-readiness/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify launch-critical public MK-MAP pages and APIs without admin credentials."
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--item", default=DEFAULT_ITEM)
    parser.add_argument("--timeout-seconds", type=int, default=20)
    parser.add_argument("--json-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/") + "/"

    checks = [
        check_health(base_url, args.timeout_seconds),
        check_home_shell(base_url, args.timeout_seconds),
        check_privacy_page(base_url, args.timeout_seconds),
        check_terms_page(base_url, args.timeout_seconds),
        check_sitemap_legal_urls(base_url, args.timeout_seconds),
        check_register_terms_gate(base_url, args.timeout_seconds),
        check_invalid_login_message(base_url, args.timeout_seconds),
        check_weather_map(base_url, args.timeout_seconds),
        check_today_signals(base_url, args.timeout_seconds),
        check_dashboard_cards(base_url, args.timeout_seconds),
        check_item_forecast(base_url, args.item, args.timeout_seconds),
    ]
    failed = [check for check in checks if not check["ok"]]
    output = {
        "ok": not failed,
        "base_url": args.base_url.rstrip("/"),
        "summary": {
            "total_checks": len(checks),
            "passed_checks": len(checks) - len(failed),
            "failed_checks": len(failed),
        },
        "failed": [{"name": check["name"], "status": check["status"]} for check in failed],
        "checks": checks,
        "next_action": next_action(failed),
    }

    if not args.json_only:
        print_human_summary(output)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failed else 0


def check_health(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(base_url, "health", timeout_seconds)
    if not response["ok"]:
        return make_check("health", "/health", False, response["status"], response=response)

    payload = response["payload"]
    status = payload.get("status")
    env = payload.get("env")
    ok = status == "ok" and env == "production"
    return make_check(
        "health",
        "/health",
        ok,
        "ok" if ok else "unexpected_payload",
        http_status=response["http_status"],
        details={"status": status, "env": env, "scheduler": payload.get("scheduler")},
    )


def check_home_shell(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_text(base_url, "", timeout_seconds)
    if not response["ok"]:
        return make_check("home_shell", "/", False, response["status"], response=response)

    body = response["body"]
    required_fragments = {
        "privacy_link": "/privacy",
        "terms_link": "/terms",
        "signup_terms_payload": "terms_accepted",
        "signup_consent": "am-legal-consent",
        "hover_fallback": "bindLayerHoverTooltip",
        "trend_group_judgment": "trendGroupJudgment",
        "korean_title": "팜맵",
    }
    missing = [name for name, fragment in required_fragments.items() if fragment not in body]
    return make_check(
        "home_shell",
        "/",
        not missing,
        "ok" if not missing else "missing_fragment",
        http_status=response["http_status"],
        details={"missing": missing},
    )


def check_privacy_page(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    return check_text_contains(
        base_url,
        "privacy",
        timeout_seconds,
        "privacy_page",
        ["개인정보처리방침", "mk-map.com", "privacy@mk-map.com"],
    )


def check_terms_page(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    return check_text_contains(
        base_url,
        "terms",
        timeout_seconds,
        "terms_page",
        ["이용약관", "팜맵", "가격 예측"],
    )


def check_sitemap_legal_urls(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    return check_text_contains(
        base_url,
        "sitemap.xml",
        timeout_seconds,
        "sitemap_legal_urls",
        ["/privacy", "/terms"],
    )


def check_register_terms_gate(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:10]
    payload = {
        "email": f"launch-readiness-{suffix}@example.invalid",
        "password": "LaunchCheck123!",
        "nickname": f"점검{suffix[:6]}",
        "role": "general",
    }
    response = fetch_json(
        base_url,
        "api/v1/auth/register",
        timeout_seconds,
        method="POST",
        payload=payload,
        expected_http_statuses={400},
    )
    if not response["ok"]:
        return make_check("register_terms_gate", "/api/v1/auth/register", False, response["status"], response=response)

    detail = response["payload"].get("detail") if isinstance(response["payload"], dict) else None
    error_code = detail.get("error") if isinstance(detail, dict) else None
    ok = error_code == "terms_required"
    return make_check(
        "register_terms_gate",
        "/api/v1/auth/register",
        ok,
        "ok" if ok else "unexpected_payload",
        http_status=response["http_status"],
        details={"error": error_code},
    )


def check_invalid_login_message(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(
        base_url,
        "api/v1/auth/login",
        timeout_seconds,
        method="POST",
        payload={"email": "nobody@example.invalid", "password": "wrong-password"},
        expected_http_statuses={401},
    )
    if not response["ok"]:
        return make_check("invalid_login_message", "/api/v1/auth/login", False, response["status"], response=response)

    body_text = json.dumps(response["payload"], ensure_ascii=False)
    ok = "이메일" in body_text or "비밀번호" in body_text or "로그인" in body_text
    return make_check(
        "invalid_login_message",
        "/api/v1/auth/login",
        ok,
        "ok" if ok else "message_not_korean",
        http_status=response["http_status"],
    )


def check_weather_map(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(base_url, "api/v1/map/weather", timeout_seconds)
    if not response["ok"]:
        return make_check("weather_map", "/api/v1/map/weather", False, response["status"], response=response)

    payload = response["payload"]
    regions = payload.get("regions") if isinstance(payload, dict) else None
    ok = isinstance(regions, list) and len(regions) > 0
    return make_check(
        "weather_map",
        "/api/v1/map/weather",
        ok,
        "ok" if ok else "missing_data",
        http_status=response["http_status"],
        details={"region_count": len(regions) if isinstance(regions, list) else 0},
    )


def check_today_signals(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(base_url, "api/v1/signals/today", timeout_seconds)
    if not response["ok"]:
        return make_check("signals_today", "/api/v1/signals/today", False, response["status"], response=response)

    payload = response["payload"]
    items = payload.get("items") if isinstance(payload, dict) else None
    ok = isinstance(items, list) and len(items) > 0
    return make_check(
        "signals_today",
        "/api/v1/signals/today",
        ok,
        "ok" if ok else "missing_data",
        http_status=response["http_status"],
        details={"base_date": payload.get("base_date"), "item_count": len(items) if isinstance(items, list) else 0},
    )


def check_dashboard_cards(base_url: str, timeout_seconds: int) -> dict[str, Any]:
    response = fetch_json(base_url, "api/v1/dashboard/cards", timeout_seconds)
    if not response["ok"]:
        return make_check("dashboard_cards", "/api/v1/dashboard/cards", False, response["status"], response=response)

    payload = response["payload"]
    cards = payload if isinstance(payload, list) else payload.get("cards", [])
    populated_cards = [
        card for card in cards
        if isinstance(card, dict) and any(card.get(key) for key in ("forecast", "risk", "price"))
    ]
    ok = len(populated_cards) > 0
    return make_check(
        "dashboard_cards",
        "/api/v1/dashboard/cards",
        ok,
        "ok" if ok else "missing_data",
        http_status=response["http_status"],
        details={"card_count": len(cards), "populated_card_count": len(populated_cards)},
    )


def check_item_forecast(base_url: str, item: str, timeout_seconds: int) -> dict[str, Any]:
    path = f"api/v1/items/{item}/forecast"
    response = fetch_json(base_url, path, timeout_seconds)
    if not response["ok"]:
        return make_check("item_forecast", "/" + path, False, response["status"], response=response)

    payload = response["payload"]
    has_payload = bool(payload.get("forecast") or payload.get("predicted_change_pct") is not None)
    return make_check(
        "item_forecast",
        "/" + path,
        has_payload,
        "ok" if has_payload else "missing_data",
        http_status=response["http_status"],
        details={"item": item, "base_date": payload.get("base_date") or payload.get("date")},
    )


def check_text_contains(
    base_url: str,
    path: str,
    timeout_seconds: int,
    name: str,
    fragments: list[str],
) -> dict[str, Any]:
    response = fetch_text(base_url, path, timeout_seconds)
    check_path = "/" + path
    if not response["ok"]:
        return make_check(name, check_path, False, response["status"], response=response)

    body = response["body"]
    missing = [fragment for fragment in fragments if fragment not in body]
    return make_check(
        name,
        check_path,
        not missing,
        "ok" if not missing else "missing_fragment",
        http_status=response["http_status"],
        details={"missing": missing},
    )


def fetch_json(
    base_url: str,
    path: str,
    timeout_seconds: int,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    expected_http_statuses: set[int] | None = None,
) -> dict[str, Any]:
    response = fetch(base_url, path, timeout_seconds, method=method, payload=payload, expected_http_statuses=expected_http_statuses)
    if not response["ok"]:
        return response
    try:
        response["payload"] = json.loads(response["body"]) if response["body"] else {}
        response.pop("body", None)
        return response
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": "invalid_json",
            "http_status": response.get("http_status"),
            "error": str(exc),
            "body_preview": response.get("body", "")[:500],
            "url": response.get("url"),
        }


def fetch_text(base_url: str, path: str, timeout_seconds: int) -> dict[str, Any]:
    return fetch(base_url, path, timeout_seconds)


def fetch(
    base_url: str,
    path: str,
    timeout_seconds: int,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    expected_http_statuses: set[int] | None = None,
) -> dict[str, Any]:
    url = urljoin(base_url, path)
    data = None
    headers = {"Accept": "application/json,text/html,*/*", "User-Agent": USER_AGENT}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    expected = expected_http_statuses or set()

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": "ok", "http_status": response.status, "body": body, "url": url}
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in expected:
            return {"ok": True, "status": "ok", "http_status": exc.code, "body": body, "url": url}
        return {"ok": False, "status": f"http_{exc.code}", "http_status": exc.code, "body_preview": body[:500], "url": url}
    except URLError as exc:
        return {"ok": False, "status": "url_error", "error": str(exc.reason), "url": url}
    except TimeoutError:
        return {"ok": False, "status": "timeout", "url": url}


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
    check: dict[str, Any] = {"name": name, "path": path, "ok": ok, "status": status}
    if http_status is not None:
        check["http_status"] = http_status
    if details is not None:
        check["details"] = details
    if response is not None:
        check["response"] = response
    return check


def next_action(failed: list[dict[str, Any]]) -> str:
    if not failed:
        return "Launch-critical public pages, auth guards, and data APIs are reachable. Continue with UX/model QA."
    names = {check["name"] for check in failed}
    if names & {"privacy_page", "terms_page", "sitemap_legal_urls", "home_shell"}:
        return "Fix public static/legal assets or Docker copy rules, then redeploy."
    if names & {"weather_map", "signals_today", "dashboard_cards", "item_forecast"}:
        return "Public data endpoints are reachable but incomplete. Check pipeline freshness and provider data."
    if names & {"register_terms_gate", "invalid_login_message"}:
        return "Auth launch gates changed unexpectedly. Recheck auth router and frontend signup payload."
    return "Inspect failed check details before the next deploy."


def print_human_summary(output: dict[str, Any]) -> None:
    status = "PASS" if output["ok"] else "FAIL"
    summary = output["summary"]
    print(f"MK-MAP launch readiness: {status}")
    print(
        f"- base_url={output['base_url']} "
        f"passed={summary['passed_checks']}/{summary['total_checks']} "
        f"failed={summary['failed_checks']}"
    )
    if output["failed"]:
        print("- failed checks:")
        for failed in output["failed"]:
            print(f"  - {failed['name']}: {failed['status']}")
    print(f"- next_action={output['next_action']}")
    print()


if __name__ == "__main__":
    sys.exit(main())

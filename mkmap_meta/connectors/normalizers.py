from __future__ import annotations

from datetime import date, datetime
from typing import Any


def first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_date(value: Any, default: date | None = None) -> date:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        if default is None:
            raise ValueError("Missing date value")
        return default

    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    if default is not None:
        return default
    raise ValueError(f"Unsupported date format: {value!r}")


def extract_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract rows from common Korean public API response shapes."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []

    candidates: list[Any] = [
        payload.get("data"),
        payload.get("items"),
        payload.get("item"),
        payload.get("rows"),
        payload.get("row"),
    ]

    response = payload.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, dict):
                candidates.extend([items.get("item"), items.get("data")])
            else:
                candidates.append(items)

    for candidate in candidates:
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
        if isinstance(candidate, dict):
            return [candidate]

    return [payload]


def public_api_error(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    response = payload.get("response")
    header = response.get("header") if isinstance(response, dict) else payload.get("header")
    if not isinstance(header, dict):
        return None

    result_code = header.get("resultCode", header.get("result_Code"))
    if result_code in (None, "", "00", "0"):
        return None

    return {
        "resultCode": result_code,
        "resultMsg": header.get("resultMsg", header.get("result_Msg")),
    }

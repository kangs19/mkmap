from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "data" / "audits" / "customs_trade"

ITEM_TRADE_URL = "http://apis.data.go.kr/1220000/Itemtrade/getItemtradeList"
COUNTRY_ITEM_TRADE_URL = "http://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"

COUNTRY_CODES = ["CN", "US", "VN", "TH", "AU", "NZ", "CL", "PE", "ES", "JP"]


ITEM_HS_CANDIDATES: dict[str, dict[str, Any]] = {
    "cabbage": {"name": "배추", "hs": ["070490"], "confidence": "medium", "note": "배추 단독이 아니라 양배추/꽃양배추류 묶음 가능성"},
    "radish": {"name": "무", "hs": ["070690"], "confidence": "medium", "note": "무·순무·기타 뿌리채소 묶음 가능성"},
    "onion": {"name": "양파", "hs": ["070310"], "confidence": "high", "note": "양파/샬롯 계열"},
    "green_onion": {"name": "대파", "hs": ["070390"], "confidence": "medium", "note": "파·부추·기타 파속 채소 묶음 가능성"},
    "garlic": {"name": "마늘", "hs": ["070320"], "confidence": "high", "note": "마늘 계열"},
    "potato": {"name": "감자", "hs": ["070190"], "confidence": "high", "note": "신선/냉장 감자"},
    "sweet_potato": {"name": "고구마", "hs": ["071420"], "confidence": "high", "note": "고구마"},
    "pepper": {"name": "건고추", "hs": ["090421", "090422"], "confidence": "medium", "note": "건조/분쇄 고추류"},
    "fresh_pepper": {"name": "풋고추", "hs": ["070960"], "confidence": "medium", "note": "신선 고추류"},
    "tomato": {"name": "토마토", "hs": ["070200"], "confidence": "high", "note": "신선/냉장 토마토"},
    "cucumber": {"name": "오이", "hs": ["070700"], "confidence": "medium", "note": "오이/피클용 오이 묶음"},
    "chamoe": {"name": "참외", "hs": ["080719"], "confidence": "low", "note": "멜론류 묶음이라 참외 단독 검증 필요"},
    "watermelon": {"name": "수박", "hs": ["080711"], "confidence": "high", "note": "수박"},
    "carrot": {"name": "당근", "hs": ["070610"], "confidence": "high", "note": "당근/순무 계열"},
    "spinach": {"name": "시금치", "hs": ["070970"], "confidence": "high", "note": "시금치"},
    "lettuce": {"name": "상추", "hs": ["070511", "070519"], "confidence": "medium", "note": "결구/기타 상추류"},
    "perilla": {"name": "깻잎", "hs": ["070999"], "confidence": "low", "note": "기타 채소 묶음이라 직접 사용 부적합"},
    "sesame": {"name": "참깨", "hs": ["120740"], "confidence": "high", "note": "참깨"},
    "apple": {"name": "사과", "hs": ["080810"], "confidence": "high", "note": "사과"},
    "pear": {"name": "배", "hs": ["080830"], "confidence": "high", "note": "배"},
    "grape": {"name": "포도", "hs": ["080610"], "confidence": "high", "note": "신선 포도"},
    "strawberry": {"name": "딸기", "hs": ["081010"], "confidence": "high", "note": "딸기"},
}


@dataclass
class ProbeResult:
    item_code: str
    item_name: str
    hs_prefix: str
    mapping_confidence: str
    row_count: int
    months: list[str]
    hs_codes: list[str]
    stat_names: list[str]
    import_weight_kg: float
    import_value_usd: float
    export_weight_kg: float
    export_value_usd: float
    top_countries: list[dict[str, Any]]
    feature_readiness: str
    note: str


def load_env() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key, value)


def month_window() -> tuple[str, str]:
    # Customs API allows up to one year per request. Use the latest completed-ish
    # 12 month window; services simply return fewer rows if the latest month is absent.
    today = date.today()
    end_year = today.year
    end_month = today.month - 1
    if end_month == 0:
        end_year -= 1
        end_month = 12
    start_year = end_year - 1 if end_month < 12 else end_year
    start_month = end_month + 1 if end_month < 12 else 1
    return f"{start_year:04d}{start_month:02d}", f"{end_year:04d}{end_month:02d}"


def request_xml(url: str, params: dict[str, Any], timeout: int = 25) -> str:
    key = os.getenv("DATA_GO_KR_API_KEY")
    if not key:
        raise RuntimeError("DATA_GO_KR_API_KEY is not configured")
    query = urlencode({"serviceKey": key, **params})
    with urlopen(f"{url}?{query}", timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rows(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    code = root.findtext(".//resultCode")
    if code and code != "00":
        msg = root.findtext(".//resultMsg") or "unknown"
        raise RuntimeError(f"API resultCode={code}: {msg}")
    rows: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        if row.get("year") == "총계":
            continue
        rows.append(row)
    return rows


def to_float(value: Any) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def row_hs(row: dict[str, str]) -> str:
    return row.get("hsCode") or row.get("hsCd") or ""


def summarize_country_rows(country_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in country_rows:
        country = row.get("statCdCntnKor1") or row.get("statCd") or "unknown"
        bucket = grouped.setdefault(country, {"country": country, "import_weight_kg": 0.0, "import_value_usd": 0.0})
        bucket["import_weight_kg"] += to_float(row.get("impWgt"))
        bucket["import_value_usd"] += to_float(row.get("impDlr"))
    return sorted(grouped.values(), key=lambda x: x["import_weight_kg"], reverse=True)[:5]


def readiness(confidence: str, rows: list[dict[str, str]], import_weight: float) -> str:
    if not rows or import_weight <= 0:
        return "no_recent_import_rows"
    if confidence == "high":
        return "ready_for_import_pressure_feature"
    if confidence == "medium":
        return "usable_after_hs_name_review"
    return "reference_only_hs_too_broad"


def probe_item(item_code: str, item: dict[str, Any], start: str, end: str) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for hs in item["hs"]:
        rows = parse_rows(request_xml(ITEM_TRADE_URL, {"strtYymm": start, "endYymm": end, "hsSgn": hs}))
        country_rows: list[dict[str, str]] = []
        for country in COUNTRY_CODES:
            try:
                country_rows.extend(
                    parse_rows(
                        request_xml(
                            COUNTRY_ITEM_TRADE_URL,
                            {"strtYymm": start, "endYymm": end, "hsSgn": hs, "cntyCd": country},
                        )
                    )
                )
            except Exception:
                # Some country/item combinations legitimately return no data or service errors.
                pass
            time.sleep(0.08)

        imp_wgt = sum(to_float(row.get("impWgt")) for row in rows)
        imp_dlr = sum(to_float(row.get("impDlr")) for row in rows)
        exp_wgt = sum(to_float(row.get("expWgt")) for row in rows)
        exp_dlr = sum(to_float(row.get("expDlr")) for row in rows)
        months = sorted({row.get("year", "") for row in rows if row.get("year")})
        hs_codes = sorted({row_hs(row) for row in rows if row_hs(row)})
        stat_names = sorted({row.get("statKor", "") for row in rows if row.get("statKor")})
        results.append(
            ProbeResult(
                item_code=item_code,
                item_name=item["name"],
                hs_prefix=hs,
                mapping_confidence=item["confidence"],
                row_count=len(rows),
                months=months,
                hs_codes=hs_codes[:30],
                stat_names=stat_names[:30],
                import_weight_kg=imp_wgt,
                import_value_usd=imp_dlr,
                export_weight_kg=exp_wgt,
                export_value_usd=exp_dlr,
                top_countries=summarize_country_rows(country_rows),
                feature_readiness=readiness(item["confidence"], rows, imp_wgt),
                note=item["note"],
            )
        )
        time.sleep(0.12)
    return results


def main() -> int:
    load_env()
    start, end = month_window()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results: list[ProbeResult] = []
    errors: list[dict[str, str]] = []
    for item_code, item in ITEM_HS_CANDIDATES.items():
        try:
            all_results.extend(probe_item(item_code, item, start, end))
        except Exception as exc:
            errors.append({"item_code": item_code, "item_name": item["name"], "error": str(exc)})

    payload = {
        "window": {"start_yymm": start, "end_yymm": end},
        "source": {
            "item_trade_url": ITEM_TRADE_URL,
            "country_item_trade_url": COUNTRY_ITEM_TRADE_URL,
            "note": "Public API key omitted. Raw response rows are summarized only.",
        },
        "results": [result.__dict__ for result in all_results],
        "errors": errors,
        "summary": {
            "tested_items": len(ITEM_HS_CANDIDATES),
            "tested_hs_prefixes": len(all_results),
            "ready": sum(r.feature_readiness == "ready_for_import_pressure_feature" for r in all_results),
            "needs_review": sum(r.feature_readiness == "usable_after_hs_name_review" for r in all_results),
            "reference_only": sum(r.feature_readiness == "reference_only_hs_too_broad" for r in all_results),
            "no_recent_rows": sum(r.feature_readiness == "no_recent_import_rows" for r in all_results),
            "errors": len(errors),
        },
    }
    output_path = OUT_DIR / f"customs_trade_feature_audit_{start}_{end}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"output_path": str(output_path), **payload["summary"]}, ensure_ascii=False, indent=2))
    return 0 if all_results else 1


if __name__ == "__main__":
    sys.exit(main())

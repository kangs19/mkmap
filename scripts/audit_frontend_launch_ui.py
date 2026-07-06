from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPO_ROOT / "index.html"

CRITICAL_EXTERNAL_PATTERNS = [
    "https://unpkg.com/leaflet",
    "https://cdn.jsdelivr.net/npm/chart.js",
    "https://fonts.googleapis.com",
]

PUBLIC_COPY_BLOCKLIST = [
    "샘플 데이터",
    "프로토타입",
    "prototype",
    "베타 운영",
    "베타 기능",
    "공개 초안",
]


def main() -> int:
    html = INDEX_PATH.read_text(encoding="utf-8")
    onclick_calls = sorted(set(extract_onclick_calls(html)))
    defined_functions = set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(", html))
    defined_functions.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", html))
    defined_functions.update(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?[A-Za-z_$][\w$]*\s*=>", html))

    missing_onclick = [name for name in onclick_calls if name not in defined_functions and not name.startswith("event")]
    ids = re.findall(r'\bid="([^"]+)"', html)
    duplicate_ids = sorted({id_value for id_value in ids if ids.count(id_value) > 1})
    critical_external = [pattern for pattern in CRITICAL_EXTERNAL_PATTERNS if pattern in html]
    disabled_beta_controls = re.findall(r'class="[^"]*\bdisabled\b[^"]*"[^>]*title="([^"]*)"', html)
    public_copy_hits = [pattern for pattern in PUBLIC_COPY_BLOCKLIST if pattern.lower() in html.lower()]

    report: dict[str, Any] = {
        "ok": not missing_onclick and not duplicate_ids and not critical_external and not public_copy_hits,
        "index_path": str(INDEX_PATH),
        "summary": {
            "onclick_function_count": len(onclick_calls),
            "defined_function_count": len(defined_functions),
            "missing_onclick_count": len(missing_onclick),
            "duplicate_id_count": len(duplicate_ids),
            "critical_external_dependency_count": len(critical_external),
            "disabled_beta_control_count": len(disabled_beta_controls),
            "public_copy_issue_count": len(public_copy_hits),
        },
        "missing_onclick": missing_onclick,
        "duplicate_ids": duplicate_ids,
        "critical_external_dependencies": critical_external,
        "disabled_beta_controls": disabled_beta_controls,
        "public_copy_issues": public_copy_hits,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


def extract_onclick_calls(html: str) -> list[str]:
    calls: list[str] = []
    for attr in re.findall(r'\bonclick="([^"]+)"', html):
        for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\(", attr):
            name = match.group(1)
            if name in {"if", "return", "confirm", "alert"}:
                continue
            calls.append(name)
    return calls


if __name__ == "__main__":
    sys.exit(main())

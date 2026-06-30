from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = [
    REPO_ROOT / "metadata" / "items",
    REPO_ROOT / "config",
    REPO_ROOT / "mkmap_meta",
    REPO_ROOT / "scripts",
    REPO_ROOT / "docs",
]
CHECKED_SUFFIXES = {".json", ".py", ".md"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect likely mojibake in user-facing MK Map text files.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    findings = scan_targets(DEFAULT_TARGETS)
    payload = {
        "ok": not findings,
        "finding_count": len(findings),
        "findings": findings[:50],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif findings:
        print("Text encoding health check failed:")
        for finding in findings[:50]:
            print(f"- {finding['path']}:{finding['line']}: {finding['sample']}")
        if len(findings) > 50:
            print(f"... {len(findings) - 50} more")
    else:
        print("Text encoding health check passed.")
    return 0 if not findings else 1


def scan_targets(targets: list[Path]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for target in targets:
        if target.is_file():
            paths = [target]
        else:
            paths = sorted(path for path in target.rglob("*") if path.is_file())

        for path in paths:
            if path.suffix.lower() not in CHECKED_SUFFIXES:
                continue
            if should_skip(path):
                continue
            findings.extend(scan_file(path))
    return findings


def scan_file(path: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for line_number, line in enumerate(text.splitlines(), 1):
        if has_likely_mojibake(line):
            findings.append(
                {
                    "path": str(path.relative_to(REPO_ROOT)),
                    "line": line_number,
                    "sample": line.strip()[:160],
                }
            )
    return findings


def has_likely_mojibake(text: str) -> bool:
    return any(is_suspicious_char(char) for char in text)


def is_suspicious_char(char: str) -> bool:
    codepoint = ord(char)
    if char == "\ufffd":
        return True
    # Korean display text should be Hangul. CJK ideographs in these metadata
    # files usually indicate UTF-8 text previously decoded as CP949.
    return 0x4E00 <= codepoint <= 0x9FFF


def should_skip(path: Path) -> bool:
    parts = set(path.relative_to(REPO_ROOT).parts)
    return bool(parts & {"__pycache__", ".pytest_cache"})


if __name__ == "__main__":
    sys.exit(main())

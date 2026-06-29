from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = REPO_ROOT / "config" / "external_mappings" / "kma_crop_weather_guide.zip"
DEFAULT_OUTPUT = REPO_ROOT / "config" / "external_mappings" / "kma_crop_weather_mapping.csv"
GUIDE_URL = "https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_000000003577750&fileDetailSn=1"
REFERER = "https://www.data.go.kr/data/15059518/openapi.do"
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

ITEMS = {
    "cabbage": {"item_name": "배추", "crop_name": "배추"},
    "radish": {"item_name": "무", "crop_name": "무"},
    "onion": {"item_name": "양파", "crop_name": "양파"},
    "green_onion": {"item_name": "대파", "crop_name": "대파"},
    "garlic": {"item_name": "마늘", "crop_name": "마늘"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract KMA crop weather mapping CSV from the official guide XLSX.")
    parser.add_argument("--zip", default=str(DEFAULT_ZIP), help="Official guide ZIP path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output mapping CSV path")
    parser.add_argument("--download", action="store_true", help="Download the official ZIP before extracting")
    return parser.parse_args()


def download_guide(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(GUIDE_URL, headers={"User-Agent": "Mozilla/5.0", "Referer": REFERER})
    path.write_bytes(urllib.request.urlopen(request, timeout=60).read())


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("a:si", NS):
        values.append("".join(text.text or "" for text in item.iter(f"{{{NS['a']}}}t")))
    return values


def worksheet_rows(xlsx_bytes: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        strings = shared_strings(archive)
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))

        rows: list[list[str]] = []
        for row in root.findall(".//a:sheetData/a:row", NS):
            values: list[str] = []
            for cell in row.findall("a:c", NS):
                index = column_index(cell.attrib["r"])
                while len(values) <= index:
                    values.append("")
                raw = cell.find("a:v", NS)
                value = raw.text if raw is not None else ""
                if cell.attrib.get("t") == "s" and value:
                    value = strings[int(value)]
                values[index] = value
            rows.append(values)

    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:]]


def extract_xlsx(zip_path: Path) -> bytes:
    with zipfile.ZipFile(zip_path) as archive:
        xlsx_names = [name for name in archive.namelist() if name.endswith(".xlsx")]
        if not xlsx_names:
            raise FileNotFoundError("No XLSX file found in KMA guide ZIP")
        return archive.read(xlsx_names[0])


def clean_float(value: str) -> str:
    if not value:
        return ""
    try:
        return f"{float(value):.8f}".rstrip("0").rstrip(".")
    except ValueError:
        return value


def main() -> int:
    args = parse_args()
    zip_path = Path(args.zip)
    output = Path(args.output)

    if args.download or not zip_path.exists():
        download_guide(zip_path)

    rows = worksheet_rows(extract_xlsx(zip_path))
    crop_to_item = {definition["crop_name"]: item_code for item_code, definition in ITEMS.items()}

    extracted: list[dict[str, str]] = []
    for row in rows:
        crop_name = row.get("주산지_작물명", "")
        item_code = crop_to_item.get(crop_name)
        if not item_code:
            continue
        extracted.append(
            {
                "item_code": item_code,
                "item_name": ITEMS[item_code]["item_name"],
                "candidate_region": row.get("지역_이름", ""),
                "pa_crop_spe_id": row.get("주산지_작물_특성_아이디", ""),
                "pa_crop_spe_name": row.get("주산지_작물_특성_이름", ""),
                "area_id": row.get("지역_아이디", ""),
                "area_name": row.get("지역_이름", ""),
                "address": row.get("지점주소", ""),
                "latitude": clean_float(row.get("위도", "")),
                "longitude": clean_float(row.get("경도", "")),
                "elevation_m": clean_float(row.get("노장해발고도(m)", "")),
                "mapping_status": "verified",
                "notes": "Official data.go.kr KMA crop main-area weather guide code table, 2026-01-05.",
            }
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "item_code",
                "item_name",
                "candidate_region",
                "pa_crop_spe_id",
                "pa_crop_spe_name",
                "area_id",
                "area_name",
                "address",
                "latitude",
                "longitude",
                "elevation_m",
                "mapping_status",
                "notes",
            ],
        )
        writer.writeheader()
        writer.writerows(extracted)

    counts: dict[str, int] = {}
    for row in extracted:
        counts[row["item_code"]] = counts.get(row["item_code"], 0) + 1
    print({"output": str(output), "rows": len(extracted), "counts": counts})
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPO_ROOT / "config" / "farmmap_public_sources.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "farmmap" / "raw"

DATA_GO_KR = "https://www.data.go.kr"
DOWNLOAD_META_URL = DATA_GO_KR + "/tcs/dss/selectFileDataDownload.do?recommendDataYn=Y"
FILE_DOWNLOAD_URL = DATA_GO_KR + "/cmm/cmm/fileDownload.do"


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve and download official FarmMap public source files from data.go.kr.")
    parser.add_argument("--data-id", help="data.go.kr publicDataPk, e.g. 15104490")
    parser.add_argument("--province", help="Province name from config/farmmap_public_sources.json")
    parser.add_argument("--catalog", default=str(CATALOG_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--max-mb", type=float, default=250.0, help="Refuse downloads larger than this size.")
    parser.add_argument("--metadata-only", action="store_true", help="Resolve file metadata without downloading.")
    args = parser.parse_args()

    source = resolve_source(args)
    if not source:
        print("No matching FarmMap source. Pass --data-id or --province.", file=sys.stderr)
        return 2

    session = HttpSession()
    detail_url = source.get("detail_url") or f"{DATA_GO_KR}/data/{source['data_id']}/fileData.do"
    detail_html = session.get_text(str(detail_url))
    detail_pk = source.get("detail_pk") or extract_detail_pk(detail_html)
    if not detail_pk:
        print(f"Could not find publicDataDetailPk for {detail_url}", file=sys.stderr)
        return 2

    meta = resolve_download_metadata(session, str(source["data_id"]), detail_pk, detail_url=str(detail_url))
    if not meta.get("status"):
        print(json.dumps(meta, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    download_url = build_file_download_url(str(meta["atchFileId"]), str(meta["fileDetailSn"]))
    head = session.head(download_url)
    content_length = int(head.get("Content-Length") or 0)
    file_name = safe_filename(
        meta.get("file_name")
        or filename_from_disposition(head.get("Content-Disposition"))
        or f"farmmap_{source['data_id']}.zip"
    )
    result = {
        "province": source.get("province"),
        "data_id": source.get("data_id"),
        "detail_pk": detail_pk,
        "detail_url": detail_url,
        "atchFileId": meta.get("atchFileId"),
        "fileDetailSn": meta.get("fileDetailSn"),
        "file_name": file_name,
        "content_length": content_length,
        "download_url": download_url,
    }

    if args.metadata_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    max_bytes = int(args.max_mb * 1024 * 1024)
    if content_length and content_length > max_bytes:
        result["skipped"] = f"content_length exceeds --max-mb ({args.max_mb})"
        print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / file_name
    session.download(download_url, output_path)
    result["output_path"] = str(output_path)
    result["downloaded_size"] = output_path.stat().st_size
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def resolve_source(args: argparse.Namespace) -> dict[str, Any] | None:
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    sources = catalog.get("sources") or []
    if args.data_id:
        for source in sources:
            if str(source.get("data_id")) == str(args.data_id):
                return source
        return {"data_id": str(args.data_id), "detail_url": f"{DATA_GO_KR}/data/{args.data_id}/fileData.do"}
    if args.province:
        for source in sources:
            if str(source.get("province")) == args.province:
                return source
    return None


class HttpSession:
    def __init__(self) -> None:
        self.cookie = ""

    def request(self, req: urllib.request.Request) -> urllib.response.addinfourl:
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        req.add_header("User-Agent", "Mozilla/5.0 MKMapFarmMapDownloader/1.0")
        resp = urllib.request.urlopen(req, timeout=60)
        cookies = resp.headers.get_all("Set-Cookie") or []
        if cookies:
            current = [part.strip() for part in self.cookie.split(";") if part.strip()]
            for cookie in cookies:
                current.append(cookie.split(";", 1)[0])
            dedup = {}
            for part in current:
                key = part.split("=", 1)[0]
                dedup[key] = part
            self.cookie = "; ".join(dedup.values())
        return resp

    def get_text(self, url: str) -> str:
        req = urllib.request.Request(url)
        with self.request(req) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def post_json(self, url: str, data: dict[str, str], referer: str) -> dict[str, Any]:
        body = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
        req.add_header("X-Requested-With", "XMLHttpRequest")
        req.add_header("Referer", referer)
        with self.request(req) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    def head(self, url: str) -> dict[str, str]:
        req = urllib.request.Request(url, method="HEAD")
        with self.request(req) as resp:
            return dict(resp.headers.items())

    def download(self, url: str, output_path: Path) -> None:
        req = urllib.request.Request(url)
        with self.request(req) as resp, output_path.open("wb") as fp:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fp.write(chunk)


def extract_detail_pk(html: str) -> str | None:
    patterns = [
        r'id="publicDataDetailPk"\s+name="publicDataDetailPk"\s+value="([^"]+)"',
        r"fn_fileDataDown\('[^']+'\s*,\s*'([^']+)'",
        r"publicDataDetailPk['\"]?\s*[:=]\s*['\"]([^'\"]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def resolve_download_metadata(session: HttpSession, data_id: str, detail_pk: str, detail_url: str) -> dict[str, Any]:
    payload = session.post_json(
        DOWNLOAD_META_URL,
        {"publicDataPk": data_id, "publicDataDetailPk": detail_pk},
        referer=detail_url,
    )
    file_info = payload.get("fileDataRegistVO") or {}
    return {
        "status": bool(payload.get("status")),
        "atchFileId": payload.get("atchFileId") or file_info.get("atchFileId"),
        "fileDetailSn": payload.get("fileDetailSn") or file_info.get("fileDetailSn"),
        "file_name": file_info.get("orginlFileNm") or file_info.get("dataNm"),
        "raw": payload,
    }


def build_file_download_url(atch_file_id: str, file_detail_sn: str) -> str:
    query = urllib.parse.urlencode({
        "atchFileId": atch_file_id,
        "fileDetailSn": file_detail_sn,
        "insertDataPrcus": "N",
    })
    return f"{FILE_DOWNLOAD_URL}?{query}"


def filename_from_disposition(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', value)
    if not match:
        return None
    return urllib.parse.unquote(match.group(1))


def safe_filename(value: str) -> str:
    value = value.replace("\\", "_").replace("/", "_").strip()
    return value or "farmmap_source.zip"


if __name__ == "__main__":
    raise SystemExit(main())

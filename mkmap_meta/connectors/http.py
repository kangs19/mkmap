from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class HttpResponse:
    status: int
    text: str
    headers: dict[str, str]

    def json(self) -> Any:
        return json.loads(self.text)


def _unverified_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


class SimpleHttpClient:
    def __init__(self, timeout: int = 20, verify_ssl: bool = True) -> None:
        self.timeout = timeout
        self._ssl_context = None if verify_ssl else _unverified_ssl_context()

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> HttpResponse:
        final_url = url
        if params:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            final_url = f"{url}?{query}"

        request = Request(final_url, headers=headers or {}, method="GET")
        with urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
            body = response.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status=response.status,
                text=body,
                headers={k: v for k, v in response.headers.items()},
            )


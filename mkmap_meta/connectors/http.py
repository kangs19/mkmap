from __future__ import annotations

import json
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


class SimpleHttpClient:
    def __init__(self, timeout: int = 20) -> None:
        self.timeout = timeout

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> HttpResponse:
        final_url = url
        if params:
            query = urlencode({k: v for k, v in params.items() if v is not None})
            final_url = f"{url}?{query}"

        request = Request(final_url, headers=headers or {}, method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return HttpResponse(
                status=response.status,
                text=body,
                headers={k: v for k, v in response.headers.items()},
            )


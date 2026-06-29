from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from mkmap_meta.connectors.http import SimpleHttpClient


KOSIS_API_KEY_ENV = "KOSIS_API_KEY"


@dataclass(frozen=True)
class KosisTable:
    name: str
    base_url: str
    org_id: str | None = None
    tbl_id: str | None = None
    default_params: dict[str, Any] | None = None


class KosisClient:
    """Small configurable KOSIS client.

    KOSIS products often require orgId, tblId, object IDs, and classification
    codes from the selected statistical table. Keep those values outside engine
    code so item metadata can evolve without code churn.
    """

    def __init__(self, api_key: str | None = None, http: SimpleHttpClient | None = None) -> None:
        self.api_key = api_key or os.getenv(KOSIS_API_KEY_ENV)
        if not self.api_key:
            raise ValueError(f"Missing {KOSIS_API_KEY_ENV}")
        self.http = http or SimpleHttpClient()

    def get(self, table: KosisTable, **params: Any) -> Any:
        if not table.base_url:
            return []

        request_params = {
            "apiKey": self.api_key,
            "method": "getList",
            "format": "json",
            "jsonVD": "Y",
            **(table.default_params or {}),
            **params,
        }
        if table.org_id:
            request_params.setdefault("orgId", table.org_id)
        if table.tbl_id:
            request_params.setdefault("tblId", table.tbl_id)

        return self.http.get(table.base_url, request_params).json()


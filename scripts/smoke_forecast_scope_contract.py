from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from app.routers.forecasts import _model_scope
from scripts.import_meta_outputs_to_backend import _forecast_factors, _model_version


def main() -> int:
    item_version = _model_version("item")
    global_version = _model_version("global")
    assert item_version.endswith("_item")
    assert global_version.endswith("_global")

    assert _model_scope(SimpleNamespace(model_version=item_version, top_factors=[])) == "item"
    assert _model_scope(SimpleNamespace(model_version=global_version, top_factors=[])) == "global"

    factors = _forecast_factors(
        {
            "risk_overlay": {
                "top_factor": "production_region_weight",
                "max_risk_score": 0.123,
            }
        },
        pure_change=0.012,
        adjusted_change=0.014,
    )
    factor_names = [factor["factor"] for factor in factors]
    assert "price_lag_model" in factor_names
    assert "risk_overlay" in factor_names
    assert all(not name.startswith("model_scope_") for name in factor_names)

    print("Forecast scope contract smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

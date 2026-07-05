from types import SimpleNamespace

from app.services.horizon_forecasts import horizon_explanation_response, horizon_response


def _item():
    return SimpleNamespace(item_code="cabbage", item_name="배추")


def _horizon(days: int, change: float, *, held_out: bool = False):
    return {
        "horizon_days": days,
        "risk_adjusted_direction": "up" if change >= 0 else "down",
        "risk_adjusted_change": change,
        "up_probability": 0.6 if change >= 0 else 0.4,
        "surge_probability": 0.1,
        "confidence": "high",
        "model_scope": "item",
        "held_out": held_out,
        "supporting_reasons": [
            {
                "feature": "price_lag",
                "label": "최근 가격 흐름",
                "contribution": change,
                "contribution_pct_points": change * 100,
            }
        ],
        "offsetting_reasons": [],
    }


def test_horizon_response_hides_long_or_held_periods_from_public_payload():
    payload = {
        "item_code": "cabbage",
        "base_date": "2026-07-06",
        "model_version": "test",
        "horizons": {
            "14": _horizon(14, 0.03),
            "30": _horizon(30, 0.08),
            "90": _horizon(90, 0.12),
            "180": _horizon(180, 0.20),
            "365": _horizon(365, -0.10),
            "7": _horizon(7, 0.02, held_out=True),
        },
    }

    response = horizon_response(_item(), payload)

    assert response["forecast"]["active_horizons"] == [14, 30, 90]
    assert sorted(response["forecast"]["horizons"]) == ["14", "30", "90"]
    assert response["forecast"]["hidden_horizons"] == [7, 180, 365]
    assert response["forecast"]["bottom_probability"] == 0.4
    assert "180d" not in response["summary"]
    assert "365d" not in response["summary"]


def test_horizon_explanation_response_uses_public_horizons_only():
    payload = {
        "item_code": "cabbage",
        "base_date": "2026-07-06",
        "model_version": "test",
        "held_horizons": [{"horizon_days": 180, "reason": "quality_gate"}],
        "horizons": {
            "14": _horizon(14, 0.04),
            "90": _horizon(90, 0.11),
            "180": _horizon(180, 0.30),
            "365": _horizon(365, 0.50),
        },
    }

    response = horizon_explanation_response(_item(), payload)

    assert response["forecast"]["active_horizons"] == [14, 90]
    assert sorted(response["forecast"]["horizons"]) == ["14", "90"]
    assert sorted(response["reasons_by_horizon"]) == ["14", "90"]
    assert response["forecast"]["hidden_horizons"] == [180, 365]
    assert response["direction"] == "up"

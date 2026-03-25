"""Scoring utilities for config auto-detection evaluation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


@dataclass(frozen=True)
class MetricWeights:
    """Weighted exact-match scoring for template config prediction."""

    sheet: float = 0.50
    header_row: float = 0.25
    data_row: float = 0.25

    def normalized(self) -> "MetricWeights":
        total = float(self.sheet) + float(self.header_row) + float(self.data_row)
        if total <= 0:
            raise ValueError("Metric weights must sum to > 0")
        return replace(
            self,
            sheet=float(self.sheet) / total,
            header_row=float(self.header_row) / total,
            data_row=float(self.data_row) / total,
        )


DEFAULT_WEIGHTS = MetricWeights().normalized()


def normalize_sheet_name(sheet_name: Any) -> str:
    """Normalize sheet names for case-insensitive comparison."""
    if sheet_name is None:
        return ""
    return str(sheet_name).strip().lower()


def _to_int(value: Any, field_name: str) -> int:
    """Coerce row fields to integer and provide consistent error messaging."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer, got: {value!r}") from exc


def score_prediction(
    expected: dict[str, Any],
    predicted: dict[str, Any],
    weights: MetricWeights = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    """Score one prediction using weighted exact matches."""
    w = weights.normalized()

    expected_sheet = normalize_sheet_name(expected.get("sheet_name"))
    predicted_sheet = normalize_sheet_name(predicted.get("sheet_name"))

    expected_header = _to_int(expected.get("header_row"), "expected.header_row")
    predicted_header = _to_int(predicted.get("header_row"), "predicted.header_row")

    expected_data = _to_int(expected.get("data_row"), "expected.data_row")
    predicted_data = _to_int(predicted.get("data_row"), "predicted.data_row")

    sheet_match = expected_sheet == predicted_sheet
    header_row_match = expected_header == predicted_header
    data_row_match = expected_data == predicted_data

    score = (
        (w.sheet if sheet_match else 0.0)
        + (w.header_row if header_row_match else 0.0)
        + (w.data_row if data_row_match else 0.0)
    )

    return {
        "sheet_match": sheet_match,
        "header_row_match": header_row_match,
        "data_row_match": data_row_match,
        "strict_match": sheet_match and header_row_match and data_row_match,
        "weighted_score": round(score, 6),
    }

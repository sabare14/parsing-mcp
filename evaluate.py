from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

from config_auto_finder import WEIGHTS, auto_detect_config_from_excel

logger = logging.getLogger(__name__)


EXPECTED_KEYS = ("file", "sheet", "header_row", "data_row")


def normalize_sample(sample: dict[str, Any]) -> dict[str, Any]:
    if all(key in sample for key in EXPECTED_KEYS):
        return {
            "file": str(sample["file"]),
            "sheet": str(sample["sheet"]),
            "header_row": int(sample["header_row"]),
            "data_row": int(sample["data_row"]),
        }
    return {
        "file": str(sample["template_file"]),
        "sheet": str(sample["sheet_name"]),
        "header_row": int(sample["header_row"]),
        "data_row": int(sample["data_row"]),
    }


def load_ground_truth(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    items: list[dict[str, Any]] = []

    if path.is_dir():
        for file_path in sorted(path.glob("*.json")):
            data = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items.extend(normalize_sample(sample) for sample in data)
            else:
                items.append(normalize_sample(data))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            items.extend(normalize_sample(sample) for sample in data)
        else:
            items.append(normalize_sample(data))

    return sorted(items, key=lambda item: item["file"])


def write_normalized_ground_truth(input_path: str | Path, output_path: str | Path) -> list[dict[str, Any]]:
    samples = load_ground_truth(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(samples, indent=2, sort_keys=True), encoding="utf-8")
    return samples


def run_detection(file_path: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = auto_detect_config_from_excel(str(file_path))
    prediction = raw.get("prediction", {})
    sheet = prediction.get("sheet") or raw.get("selected_sheet")
    header_row = prediction.get("header_row") or raw.get("header_row")
    data_row = prediction.get("data_row") or raw.get("data_row")
    pred = {"sheet": sheet, "header_row": int(header_row), "data_row": int(data_row)}
    return pred, raw


def score_prediction(pred: dict[str, Any], gt: dict[str, Any]) -> tuple[dict[str, bool], dict[str, float]]:
    sheet_score = 1.0 if pred["sheet"] == gt["sheet"] else 0.0
    header_score = math.exp(-abs(pred["header_row"] - gt["header_row"]))
    data_score = math.exp(-abs(pred["data_row"] - gt["data_row"]))
    final_score = 0.4 * sheet_score + 0.3 * header_score + 0.3 * data_score
    return (
        {
            "sheet": bool(sheet_score),
            "header": pred["header_row"] == gt["header_row"],
            "data": pred["data_row"] == gt["data_row"],
        },
        {
            "sheet": round(sheet_score, 6),
            "header": round(header_score, 6),
            "data": round(data_score, 6),
            "final": round(final_score, 6),
        },
    )


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def _score_additive(features: dict[str, float], weights: dict[str, float]) -> dict[str, Any]:
    components = {
        key: round(float(features.get(key, 0.0)) * float(weight), 6) for key, weight in weights.items()
    }
    return {
        "score": round(clamp(sum(components.values())), 6),
        "components": components,
    }


def _score_header_row_fallback(
    row_index: int,
    rows: list[dict[str, Any]],
    weights: dict[str, float],
) -> dict[str, Any] | None:
    indexed_rows = {int(row.get("row_index", 0)): row for row in rows}
    row = indexed_rows.get(int(row_index))
    if row is None:
        return None
    sorted_rows = sorted(rows, key=lambda item: int(item.get("row_index", 0)))
    target_pos = next((idx for idx, item in enumerate(sorted_rows) if int(item.get("row_index", 0)) == row_index), -1)
    if target_pos < 0:
        return None
    next_rows = sorted_rows[target_pos + 1 : target_pos + 3]
    next_avg_non_empty = sum(int(item.get("non_empty_count", 0)) for item in next_rows) / max(1, len(next_rows))
    scanned_rows = max(1, len(sorted_rows))
    non_empty_count = int(row.get("non_empty_count", 0))
    style_ratio = clamp(float(row.get("styled_count", 0)) / max(1.0, float(non_empty_count)))
    features = {
        "non_empty_norm": clamp(non_empty_count / 10.0),
        "string_ratio": float(row.get("string_ratio", 0.0)),
        "short_text_ratio": float(row.get("short_text_ratio", 0.0)),
        "unique_value_ratio": float(row.get("unique_value_ratio", 0.0)),
        "style_ratio": style_ratio,
        "followed_by_tabular": clamp(next_avg_non_empty / max(3.0, float(non_empty_count))),
        "early_row_bias": clamp(1.0 - ((row_index - 1) / max(1.0, scanned_rows - 1.0))),
        "has_id_like_token": float(bool(row.get("has_id_like_token", False))),
        "has_name_like_token": float(bool(row.get("has_name_like_token", False))),
        "has_date_like_token": float(bool(row.get("has_date_like_token", False))),
        "has_code_like_token": float(bool(row.get("has_code_like_token", False))),
        "numeric_ratio": float(row.get("numeric_ratio", 0.0)),
        "long_text_ratio": float(row.get("long_text_ratio", 0.0)),
        "sparse_penalty": clamp((2.0 - non_empty_count) / 2.0),
    }
    score_info = _score_additive(features, weights)
    return {"row": int(row_index), "score": score_info["score"], "components": score_info["components"]}


def _score_data_row_fallback(
    row_index: int,
    rows: list[dict[str, Any]],
    header_row: int,
    weights: dict[str, float],
    sheet_features: dict[str, Any],
) -> dict[str, Any] | None:
    if int(row_index) <= int(header_row):
        return None
    indexed_rows = {int(row.get("row_index", 0)): row for row in rows}
    row = indexed_rows.get(int(row_index))
    if row is None:
        return None
    candidates = [item for item in rows if int(item.get("row_index", 0)) > int(header_row)]
    if not candidates:
        return None
    header_features = indexed_rows.get(int(header_row))
    header_columns = set(header_features.get("non_empty_columns", []) if header_features else [])
    if not header_columns:
        header_columns = set(sheet_features.get("active_columns", []))
    header_col_count = max(1, len(header_columns))
    first_non_empty_after_header = next(
        (int(item.get("row_index", 0)) for item in candidates if int(item.get("non_empty_count", 0)) >= 2),
        int(candidates[0].get("row_index", 0)),
    )
    sorted_candidates = sorted(candidates, key=lambda item: int(item.get("row_index", 0)))
    span = max(
        1,
        int(sorted_candidates[-1].get("row_index", 0)) - (int(header_row) + 1) + 1,
    )
    non_empty_count = int(row.get("non_empty_count", 0))
    row_columns = set(row.get("non_empty_columns", []))
    overlap_with_header = len(row_columns & header_columns) / header_col_count
    distance = int(row_index) - int(header_row)
    prev_non_empty = int(indexed_rows.get(int(row_index) - 1, {}).get("non_empty_count", 0))
    style_ratio = clamp(float(row.get("styled_count", 0)) / max(1.0, float(non_empty_count)))
    features = {
        "overlap_with_header": clamp(overlap_with_header),
        "numeric_ratio": float(row.get("numeric_ratio", 0.0)),
        "value_mix": clamp(
            1.0 - float(row.get("short_text_ratio", 0.0)) * float(row.get("string_ratio", 0.0))
        ),
        "early_after_header": clamp(1.0 - ((distance - 1) / span)),
        "offset_preference": clamp(1.0 - abs(distance - 2.5) / 3.5),
        "unstyled_ratio": clamp(1.0 - style_ratio),
        "unique_value_ratio": float(row.get("unique_value_ratio", 0.0)),
        "first_non_empty_after_header": float(int(row_index) == first_non_empty_after_header),
        "sparse_input": float(non_empty_count == 1),
        "transition_from_dense": float(prev_non_empty >= 3 and non_empty_count <= 1),
        "header_like_text": clamp(float(row.get("string_ratio", 0.0)) * float(row.get("short_text_ratio", 0.0))),
        "long_note_penalty": clamp(float(row.get("long_text_ratio", 0.0)) * float(row.get("string_ratio", 0.0))),
        "dense_row_penalty": clamp((non_empty_count - 8.0) / 8.0),
    }
    score_info = _score_additive(features, weights)
    return {"row": int(row_index), "score": score_info["score"], "components": score_info["components"]}


def _pick_candidate(
    candidate_by_row: dict[int, dict[str, Any]],
    row: int,
    fallback_builder: Any,
) -> dict[str, Any]:
    candidate = candidate_by_row.get(int(row))
    if candidate is not None:
        return candidate
    fallback = fallback_builder(int(row))
    if fallback is not None:
        return fallback
    return {"row": int(row), "score": None, "components": {}}


def _score_gap(predicted_score: Any, ground_truth_score: Any) -> float | None:
    if predicted_score is None or ground_truth_score is None:
        return None
    return round(float(predicted_score) - float(ground_truth_score), 6)


def evaluate(ground_truth_json: str | Path, excel_dir: str | Path) -> tuple[dict[str, Any], dict[str, Any]]:
    excel_dir = Path(excel_dir)
    samples = load_ground_truth(ground_truth_json)
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    correct_sheet = 0
    correct_header = 0
    correct_data = 0
    eval_started = time.perf_counter()

    for gt in samples:
        file_started = time.perf_counter()
        file_path = excel_dir / gt["file"]
        gt_view = {"sheet": gt["sheet"], "header_row": gt["header_row"], "data_row": gt["data_row"]}
        try:
            pred, raw = run_detection(file_path)
            correct, scores = score_prediction(pred, gt)
        except Exception as exc:  # noqa: BLE001
            pred = {"sheet": None, "header_row": -1, "data_row": -1, "error": str(exc)}
            raw = {}
            correct = {"sheet": False, "header": False, "data": False}
            scores = {"sheet": 0.0, "header": 0.0, "data": 0.0, "final": 0.0}

        correct_sheet += int(correct["sheet"])
        correct_header += int(correct["header"])
        correct_data += int(correct["data"])

        results.append(
            {
                "file": gt["file"],
                "pred": pred,
                "gt": gt_view,
                "correct": correct,
                "scores": scores,
            }
        )

        if not (correct["sheet"] and correct["header"] and correct["data"]):
            header_top = raw.get("scores", {}).get("header", {}).get("top_candidates", [])
            data_top = raw.get("scores", {}).get("data", {}).get("top_candidates", [])
            header_all = raw.get("scores", {}).get("header", {}).get("all_candidates", header_top)
            data_all = raw.get("scores", {}).get("data", {}).get("all_candidates", data_top)
            row_features = raw.get("features", {}).get("rows", [])
            sheet = raw.get("features", {}).get("sheet", {})
            header_candidates = [
                {
                    "row": int(item.get("row", 0)),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "components": item.get("components", {}),
                }
                for item in header_top
            ]
            data_candidates = [
                {
                    "row": int(item.get("row", 0)),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "components": item.get("components", {}),
                }
                for item in data_top
            ]
            header_candidate_by_row = {
                int(item.get("row", 0)): {
                    "row": int(item.get("row", 0)),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "components": item.get("components", {}),
                }
                for item in header_all
            }
            data_candidate_by_row = {
                int(item.get("row", 0)): {
                    "row": int(item.get("row", 0)),
                    "score": round(float(item.get("score", 0.0)), 6),
                    "components": item.get("components", {}),
                }
                for item in data_all
            }

            predicted_header_row = int(pred.get("header_row", 0))
            correct_header_row = int(gt["header_row"])
            predicted_data_row = int(pred.get("data_row", 0))
            correct_data_row = int(gt["data_row"])

            header_predicted_row = _pick_candidate(
                candidate_by_row=header_candidate_by_row,
                row=predicted_header_row,
                fallback_builder=lambda row: _score_header_row_fallback(
                    row_index=row,
                    rows=row_features,
                    weights=WEIGHTS["header"],
                ),
            )
            header_correct_row = _pick_candidate(
                candidate_by_row=header_candidate_by_row,
                row=correct_header_row,
                fallback_builder=lambda row: _score_header_row_fallback(
                    row_index=row,
                    rows=row_features,
                    weights=WEIGHTS["header"],
                ),
            )
            data_predicted_row = _pick_candidate(
                candidate_by_row=data_candidate_by_row,
                row=predicted_data_row,
                fallback_builder=lambda row: _score_data_row_fallback(
                    row_index=row,
                    rows=row_features,
                    header_row=predicted_header_row,
                    weights=WEIGHTS["data"],
                    sheet_features=sheet,
                ),
            )
            data_correct_row = _pick_candidate(
                candidate_by_row=data_candidate_by_row,
                row=correct_data_row,
                fallback_builder=lambda row: _score_data_row_fallback(
                    row_index=row,
                    rows=row_features,
                    header_row=predicted_header_row,
                    weights=WEIGHTS["data"],
                    sheet_features=sheet,
                ),
            )

            predicted_header_score = header_predicted_row.get("score")
            correct_header_score = header_correct_row.get("score")
            header_score_gap = _score_gap(predicted_header_score, correct_header_score)
            predicted_data_score = data_predicted_row.get("score")
            correct_data_score = data_correct_row.get("score")
            data_score_gap = _score_gap(predicted_data_score, correct_data_score)

            scanned_rows = int(sheet.get("scanned_rows", len(row_features)))
            max_row = int(
                sheet.get(
                    "max_row",
                    max((int(row.get("row_index", 0)) for row in row_features), default=scanned_rows),
                )
            )

            failures.append(
                {
                    "file": gt["file"],
                    "gt": gt_view,
                    "pred": pred,
                    "scores": scores,
                    "failure_type": {
                        "sheet": not bool(correct["sheet"]),
                        "header": not bool(correct["header"]),
                        "data": not bool(correct["data"]),
                    },
                    "header_candidates": header_candidates,
                    "data_candidates": data_candidates,
                    "header_predicted_row": header_predicted_row,
                    "header_correct_row": header_correct_row,
                    "data_predicted_row": data_predicted_row,
                    "data_correct_row": data_correct_row,
                    "header_comparison": {
                        "predicted": header_predicted_row,
                        "ground_truth": header_correct_row,
                        "score_gap": header_score_gap,
                    },
                    "data_comparison": {
                        "applicable": bool(correct_data_row > predicted_header_row),
                        "predicted": data_predicted_row,
                        "ground_truth": data_correct_row,
                        "score_gap": data_score_gap,
                    },
                    "header_miss": {
                        "correct_row": correct_header_row,
                        "predicted_row": predicted_header_row,
                        "correct_score": correct_header_score,
                        "predicted_score": predicted_header_score,
                        "score_gap": header_score_gap,
                    },
                    "data_miss": {
                        "correct_row": correct_data_row,
                        "predicted_row": predicted_data_row,
                        "correct_score": correct_data_score,
                        "predicted_score": predicted_data_score,
                        "score_gap": data_score_gap,
                    },
                    "rows": [
                        {
                            "row": int(row.get("row_index", 0)),
                            "non_empty": int(row.get("non_empty_count", 0)),
                            "string_ratio": round(float(row.get("string_ratio", 0.0)), 6),
                            "numeric_ratio": round(float(row.get("numeric_ratio", 0.0)), 6),
                            "short_text_ratio": round(float(row.get("short_text_ratio", 0.0)), 6),
                            "average_text_length": round(float(row.get("average_text_length", 0.0)), 6),
                            "is_title_like": bool(
                                row.get("non_empty_count", 0) <= 2
                                and row.get("average_text_length", 0.0) >= 24.0
                                and row.get("string_ratio", 0.0) > 0.0
                            ),
                            "has_id_like_token": bool(row.get("has_id_like_token", False)),
                            "has_name_like_token": bool(row.get("has_name_like_token", False)),
                        }
                        for row in row_features
                    ],
                    "sheet_features": {
                        "active_column_count": int(sheet.get("active_column_count", 0)),
                        "text_ratio": round(float(sheet.get("text_cell_ratio", 0.0)), 6),
                        "numeric_ratio": round(float(sheet.get("numeric_cell_ratio", 0.0)), 6),
                        "max_row": max_row,
                        "scanned_rows": scanned_rows,
                        "candidate_header_rows": sheet.get("candidate_header_rows", []),
                        "instruction_like_score": round(float(sheet.get("instruction_signal", 0.0)), 6),
                        "lookup_like_score": round(float(sheet.get("lookup_signal", 0.0)), 6),
                    },
                }
            )
        elapsed = time.perf_counter() - file_started
        logger.info("evaluated file=%s time_sec=%.3f final=%.6f", gt["file"], elapsed, scores["final"])

    results.sort(key=lambda item: item["file"])
    overall_score = sum(item["scores"]["final"] for item in results) / max(1, len(results))
    failures = sorted(failures, key=lambda item: (item["scores"]["final"], item["file"]))[:5]

    result_payload = {
        "overall_score": round(overall_score, 6),
        "summary": {
            "total_files": len(results),
            "correct_sheet": correct_sheet,
            "correct_header": correct_header,
            "correct_data": correct_data,
        },
        "results": results,
    }
    debug_payload = {
        "overall_score": round(overall_score, 6),
        "failures": failures,
        "current_weights": {
            "header": WEIGHTS["header"],
            "data": WEIGHTS["data"],
            "sheet": WEIGHTS["sheet"],
        },
    }
    logger.info("evaluation complete files=%d time_sec=%.3f overall=%.6f", len(results), time.perf_counter() - eval_started, round(overall_score, 6))
    return result_payload, debug_payload


def main() -> dict[str, Any]:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_started = time.perf_counter()
    normalized_ground_truth = Path("ground_truth_normalized.json")
    excel_dir = Path("templates")
    history_root = Path("history")

    result_payload, debug_payload = evaluate(normalized_ground_truth, excel_dir)

    history_root.mkdir(parents=True, exist_ok=True)
    existing_iters = sorted(
        int(path.name) for path in history_root.iterdir() if path.is_dir() and path.name.isdigit()
    )
    prev_iter = existing_iters[-1] if existing_iters else None
    next_iter = (prev_iter + 1) if prev_iter is not None else 1
    current_iter_dir = history_root / f"{next_iter:03d}"
    current_iter_dir.mkdir(parents=True, exist_ok=False)

    prev_score = None
    prev_file_scores: dict[str, float] = {}
    if prev_iter is not None:
        prev_results_path = history_root / f"{prev_iter:03d}" / "results.json"
        if prev_results_path.exists():
            prev_results = json.loads(prev_results_path.read_text(encoding="utf-8"))
            if prev_results.get("overall_score") is not None:
                prev_score = float(prev_results["overall_score"])
            prev_file_scores = {
                item.get("file"): float(item.get("scores", {}).get("final"))
                for item in prev_results.get("results", [])
                if item.get("file") and item.get("scores", {}).get("final") is not None
            }

    current_score = float(result_payload["overall_score"])
    improvement = round(current_score - prev_score, 6) if prev_score is not None else None
    result_payload["delta"] = {
        "previous_score": round(prev_score, 6) if prev_score is not None else None,
        "current_score": round(current_score, 6),
        "improvement": improvement,
    }
    debug_payload["delta"] = {
        "previous_score": round(prev_score, 6) if prev_score is not None else None,
        "current_score": round(current_score, 6),
        "improvement": improvement,
    }

    for failure in debug_payload.get("failures", []):
        previous_file_score = prev_file_scores.get(failure.get("file"))
        current_file_score = round(float(failure.get("scores", {}).get("final", 0.0)), 6)
        previous_file_score_rounded = round(previous_file_score, 6) if previous_file_score is not None else None
        failure["score_delta"] = {
            "previous": previous_file_score_rounded,
            "current": current_file_score,
            "improvement": round(current_file_score - previous_file_score_rounded, 6)
            if previous_file_score_rounded is not None
            else None,
        }
        failure.pop("prev_score", None)
        failure.pop("current_score", None)

    result_path = current_iter_dir / "results.json"
    debug_path = current_iter_dir / "debug.json"
    result_path.write_text(json.dumps(result_payload, indent=2, sort_keys=True), encoding="utf-8")
    debug_path.write_text(json.dumps(debug_payload, indent=2, sort_keys=True), encoding="utf-8")

    logger.info("overall_score=%.6f results=%d failures=%d", result_payload["overall_score"], len(result_payload["results"]), len(debug_payload["failures"]))
    logger.info("iteration=%03d result_json=%s debug_json=%s", next_iter, result_path, debug_path)
    logger.info("run complete time_sec=%.3f", time.perf_counter() - run_started)
    return {"result": result_payload, "debug": debug_payload}


if __name__ == "__main__":
    main()

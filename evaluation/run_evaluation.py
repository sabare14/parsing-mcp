"""Run config-auto-finder evaluation against per-template ground-truth JSON."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dropdown_extractor.config_auto_finder import auto_detect_config_from_excel
from evaluation.metrics import DEFAULT_WEIGHTS, MetricWeights, score_prediction


def _load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_knobs(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_weights(path: str | None) -> MetricWeights:
    if not path:
        return DEFAULT_WEIGHTS
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return MetricWeights(
        sheet=float(raw.get("sheet", DEFAULT_WEIGHTS.sheet)),
        header_row=float(raw.get("header_row", DEFAULT_WEIGHTS.header_row)),
        data_row=float(raw.get("data_row", DEFAULT_WEIGHTS.data_row)),
    ).normalized()


def _iter_ground_truth_files(ground_truth_dir: Path):
    for path in sorted(ground_truth_dir.glob("*.json")):
        if path.name.startswith("."):
            continue
        yield path


def evaluate_dataset(
    ground_truth_dir: Path,
    templates_root: Path,
    max_rows: int = 15,
    knobs: dict[str, Any] | None = None,
    weights: MetricWeights = DEFAULT_WEIGHTS,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    weighted_total = 0.0
    strict_count = 0

    for gt_path in _iter_ground_truth_files(ground_truth_dir):
        expected = _load_json(gt_path)
        template_file = expected.get("template_file")
        template_path = templates_root / str(template_file)

        item: dict[str, Any] = {
            "ground_truth_file": gt_path.name,
            "template_file": template_file,
            "template_path": str(template_path),
        }

        try:
            detected = auto_detect_config_from_excel(
                str(template_path),
                max_rows=max_rows,
                knobs=knobs,
            )
            predicted = {
                "sheet_name": detected.get("selected_sheet"),
                "header_row": detected.get("header_row"),
                "data_row": detected.get("data_row"),
            }
            result = score_prediction(expected=expected, predicted=predicted, weights=weights)

            item.update(
                {
                    "expected": {
                        "sheet_name": expected.get("sheet_name"),
                        "header_row": expected.get("header_row"),
                        "data_row": expected.get("data_row"),
                    },
                    "predicted": predicted,
                    "matches": {
                        "sheet": result["sheet_match"],
                        "header_row": result["header_row_match"],
                        "data_row": result["data_row_match"],
                        "strict": result["strict_match"],
                    },
                    "weighted_score": result["weighted_score"],
                    "status": "ok",
                }
            )

            weighted_total += float(result["weighted_score"])
            if result["strict_match"]:
                strict_count += 1
        except Exception as exc:  # noqa: BLE001 - keep batch run robust
            item.update(
                {
                    "status": "error",
                    "error": str(exc),
                    "weighted_score": 0.0,
                }
            )

        rows.append(item)

    total = len(rows)
    average_weighted_score = (weighted_total / total) if total else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ground_truth_dir": str(ground_truth_dir),
        "templates_root": str(templates_root),
        "weights": {
            "sheet": weights.sheet,
            "header_row": weights.header_row,
            "data_row": weights.data_row,
        },
        "summary": {
            "total_templates": total,
            "strict_match_count": strict_count,
            "strict_match_rate": round((strict_count / total) if total else 0.0, 6),
            "average_weighted_score": round(average_weighted_score, 6),
            "val_error": round(1.0 - average_weighted_score, 6),
        },
        "results": rows,
    }


def _default_output_path(results_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return results_dir / f"eval_{stamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate config_auto_finder predictions against ground truth")
    parser.add_argument("--ground-truth-dir", default="evaluation/ground_truth")
    parser.add_argument("--templates-root", default="templates")
    parser.add_argument("--max-rows", type=int, default=15)
    parser.add_argument("--knobs-json", default=None, help="Optional AutoDetectKnobs override JSON")
    parser.add_argument("--weights-json", default=None, help="Optional metric-weight JSON")
    parser.add_argument(
        "--output-path",
        default=None,
        help="Optional explicit output path; default is evaluation/results/eval_<timestamp>.json",
    )
    args = parser.parse_args()

    weights = _load_weights(args.weights_json)
    report = evaluate_dataset(
        ground_truth_dir=Path(args.ground_truth_dir),
        templates_root=Path(args.templates_root),
        max_rows=args.max_rows,
        knobs=_load_knobs(args.knobs_json),
        weights=weights,
    )

    output_path = Path(args.output_path) if args.output_path else _default_output_path(Path("evaluation/results"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    summary = report["summary"]
    print(f"weighted_score: {summary['average_weighted_score']:.6f}")
    print(f"val_error:      {summary['val_error']:.6f}")
    print(f"templates:      {summary['total_templates']}")
    print(f"strict_count:   {summary['strict_match_count']}")
    print(f"output_json:    {output_path}")


if __name__ == "__main__":
    main()

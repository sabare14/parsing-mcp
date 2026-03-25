"""Bootstrap expected-output JSON files from current detector predictions."""

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

from dropdown_extractor.config_auto_finder import (
    SUPPORTED_EXCEL_EXTENSIONS,
    auto_detect_config_from_excel,
)


def _load_knobs(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_template_files(templates_dir: Path):
    for path in sorted(templates_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name.startswith(".~lock."):
            continue
        if path.suffix.lower() not in SUPPORTED_EXCEL_EXTENSIONS:
            continue
        yield path


def bootstrap_ground_truth(
    templates_dir: Path,
    output_dir: Path,
    max_rows: int = 15,
    knobs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    failed: list[dict[str, str]] = []

    for template_path in _iter_template_files(templates_dir):
        try:
            detected = auto_detect_config_from_excel(
                str(template_path),
                max_rows=max_rows,
                knobs=knobs,
            )
            payload = {
                "template_file": template_path.name,
                "sheet_name": detected["selected_sheet"],
                "header_row": int(detected["header_row"]),
                "data_row": int(detected["data_row"]),
                "review_status": "needs_review",
                "bootstrap": {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "auto_detect_config_from_excel",
                    "confidence": detected.get("confidence", {}),
                },
            }
            out_path = output_dir / f"{template_path.name}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            created.append(out_path.name)
        except Exception as exc:  # noqa: BLE001 - keep bootstrap robust for batches
            failed.append({"template_file": template_path.name, "error": str(exc)})

    return {
        "created_count": len(created),
        "failed_count": len(failed),
        "created": created,
        "failed": failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap ground-truth JSON from template files.")
    parser.add_argument("--templates-dir", default="templates", help="Directory containing template workbooks")
    parser.add_argument(
        "--output-dir",
        default="evaluation/ground_truth",
        help="Directory where per-template JSON outputs are written",
    )
    parser.add_argument("--max-rows", type=int, default=15, help="Detection scan row bound")
    parser.add_argument(
        "--knobs-json",
        default=None,
        help="Optional JSON file with AutoDetectKnobs overrides",
    )
    args = parser.parse_args()

    summary = bootstrap_ground_truth(
        templates_dir=Path(args.templates_dir),
        output_dir=Path(args.output_dir),
        max_rows=args.max_rows,
        knobs=_load_knobs(args.knobs_json),
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

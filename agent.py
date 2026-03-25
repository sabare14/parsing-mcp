import json
import logging
import math
import subprocess
import sys
import time
from pathlib import Path

HISTORY_DIR = Path("history")
CONFIG_FILE = Path("config_auto_finder.py")
OPTIMIZER_FILE = Path("optimizer.md")
AGENT_HISTORY_FILE = Path("agent_history.jsonl")
MAX_ITERS = 20
MAX_CONFIG_CHANGED_LINES = 120
NO_IMPROVEMENT_LIMIT = 3
SCORE_MIN = 0.0
SCORE_MAX = 1.0

logging.basicConfig(level=logging.INFO, format="%(message)s")


def run_evaluation():
    result = subprocess.run([sys.executable, "evaluate.py"], text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "evaluate.py failed")
    iters = sorted(
        [p for p in HISTORY_DIR.iterdir() if p.is_dir() and p.name.isdigit()],
        key=lambda p: int(p.name),
    )
    if not iters:
        raise RuntimeError("No history iterations found")
    latest = iters[-1]
    results = json.loads((latest / "results.json").read_text(encoding="utf-8"))
    debug = json.loads((latest / "debug.json").read_text(encoding="utf-8"))
    return int(latest.name), results, debug


def call_pi(prompt_text):
    result = subprocess.run(
        ["npx", "@mariozechner/pi-coding-agent"],
        input=prompt_text,
        text=True,
        capture_output=True,
        timeout=80,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pi call failed")
    return result.stdout.strip()


def get_config_diff():
    result = subprocess.run(
        ["git", "diff", "--", str(CONFIG_FILE)],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "git diff failed")
    return result.stdout.strip()


def count_changed_lines(diff_text):
    changed = 0
    for line in diff_text.splitlines():
        if (line.startswith("+") or line.startswith("-")) and not (
            line.startswith("+++") or line.startswith("---")
        ):
            changed += 1
    return changed


def restore_config_file():
    restore_result = subprocess.run(
        ["git", "restore", "--source=HEAD", "--", str(CONFIG_FILE)],
        text=True,
        capture_output=True,
    )
    if restore_result.returncode != 0:
        raise RuntimeError(
            restore_result.stderr.strip() or restore_result.stdout.strip() or "git restore failed"
        )


def parse_overall_score(results):
    if "overall_score" not in results:
        raise ValueError("missing overall_score")
    raw = results.get("overall_score")
    if raw is None:
        raise ValueError("overall_score is null")
    try:
        score = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"overall_score is not numeric: {raw!r}") from exc
    if not math.isfinite(score):
        raise ValueError(f"overall_score is not finite: {raw!r}")
    if score < SCORE_MIN - 1e-6 or score > SCORE_MAX + 1e-6:
        raise ValueError(f"overall_score out of range: {score}")
    return score


def git_commit(iteration):
    add_result = subprocess.run(["git", "add", "."], text=True, capture_output=True)
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or add_result.stdout.strip() or "git add failed")
    commit_result = subprocess.run(
        ["git", "commit", "-m", f"iteration {iteration}"],
        text=True,
        capture_output=True,
    )
    if commit_result.returncode != 0:
        raise RuntimeError(commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit failed")


def git_revert_last_commit():
    reset_result = subprocess.run(["git", "reset", "--hard", "HEAD~1"], text=True, capture_output=True)
    if reset_result.returncode != 0:
        raise RuntimeError(reset_result.stderr.strip() or reset_result.stdout.strip() or "git reset failed")


def append_history(record):
    with AGENT_HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def main():
    optimizer_text = OPTIMIZER_FILE.read_text(encoding="utf-8")
    loop = 1
    no_improvement_streak = 0
    while loop <= MAX_ITERS:
        ts = int(time.time())
        status = "skipped"
        prev_score = None
        curr_score = None
        improvement = None
        before_iter = None
        after_iter = None
        try:
            logging.info(f"--- Iteration {loop}/{MAX_ITERS} started ---")
            logging.info("Running baseline evaluation...")
            before_iter, before_results, debug = run_evaluation()
            prev_score = parse_overall_score(before_results)
            failures = debug.get("failures", [])
            current_weights = debug.get("current_weights", {})
            logging.info(
                f"Baseline ready: history={before_iter}, score={prev_score:.6f}, failures={len(failures)}"
            )
            llm_prompt = (
                "You are improving config_auto_finder.py.\n"
                "Edit ONLY config_auto_finder.py directly in the workspace.\n"
                "Inspect failed cases and compare predicted vs ground-truth candidate scores/components.\n"
                "Focus on 1-2 failed cases only.\n"
                "Identify the smallest edit likely to flip at least one failed ranking.\n"
                "Avoid edits that only smooth weights without likely ranking impact.\n"
                "Make only 1-2 focused code changes.\n"
                "In summary, state exactly what changed and which failure(s) it targets.\n"
                "Then output strict JSON only in this format:\n"
                '{"changed": true|false, "summary": "what changed and why"}\n'
                "If no useful change, set changed=false and explain why in summary.\n"
                "No markdown and no extra text.\n\n"
                f"optimizer.md:\n{optimizer_text}\n\n"
                f"debug.json:\n{json.dumps(debug, indent=2, sort_keys=True)}\n\n"
                f"overall_score={prev_score}\n"
                f"failures={len(failures)}\n"
                f"current_weights={json.dumps(current_weights, sort_keys=True)}\n"
            )
            before_text = CONFIG_FILE.read_text(encoding="utf-8")
            logging.info("Calling Pi for a candidate improvement...")
            plan_output = call_pi(llm_prompt)
            after_text = CONFIG_FILE.read_text(encoding="utf-8")
            changed = before_text != after_text
            diff_text = get_config_diff() if changed else ""
            logging.info(f"pi_output={plan_output}")
            if not changed:
                logging.info("Pi made no file change. Skipping commit.")
                status = "skipped"
            else:
                changed_lines = count_changed_lines(diff_text)
                logging.info(f"Candidate edit detected: changed_lines={changed_lines}")
                if changed_lines > MAX_CONFIG_CHANGED_LINES:
                    restore_config_file()
                    status = "skipped_large_diff"
                    logging.info(
                        "Edit too large: changed_lines=%d (limit=%d). Reverted working copy.",
                        changed_lines,
                        MAX_CONFIG_CHANGED_LINES,
                    )
                    diff_text = ""
                    changed = False
                else:
                    logging.info("Committing candidate edit...")
                    git_commit(loop)
                    try:
                        logging.info("Running post-change evaluation...")
                        after_iter, after_results, _ = run_evaluation()
                    except Exception:
                        logging.info("Post-change evaluation failed. Reverting commit.")
                        git_revert_last_commit()
                        raise
                    try:
                        curr_score = parse_overall_score(after_results)
                    except ValueError as exc:
                        logging.info("Invalid post-change score. Reverting commit.")
                        git_revert_last_commit()
                        status = "reverted_invalid_eval"
                        logging.info(f"invalid evaluation result: {exc}")
                    else:
                        improvement = round(curr_score - prev_score, 6)
                        logging.info(
                            f"Post-change score: history={after_iter}, score={curr_score:.6f}, improvement={improvement:+.6f}"
                        )
                        if curr_score > prev_score + 1e-6:
                            status = "kept"
                            logging.info("Improved. Keeping commit.")
                        else:
                            git_revert_last_commit()
                            status = "reverted"
                            logging.info("No improvement. Reverted commit.")
        except Exception:
            status = (
                status
                if status in {"kept", "reverted", "reverted_invalid_eval", "skipped_large_diff"}
                else "skipped"
            )
            logging.info(f"Iteration error handled. status={status}")
        delta_str = f"{improvement:+.6f}" if improvement is not None else "N/A"
        score_str = f"{curr_score:.6f}" if curr_score is not None else "N/A"
        logging.info(
            f"Iteration {loop} complete: status={status}, score={score_str}, delta={delta_str}"
        )
        logging.info(f"--- Iteration {loop}/{MAX_ITERS} finished ---")
        append_history(
            {
                "timestamp": ts,
                "iteration": loop,
                "status": status,
                "history_before": before_iter,
                "history_after": after_iter,
                "previous_score": prev_score,
                "current_score": curr_score,
                "improvement": improvement,
            }
        )
        if status == "kept":
            no_improvement_streak = 0
        else:
            no_improvement_streak += 1
            if no_improvement_streak >= NO_IMPROVEMENT_LIMIT:
                logging.info(
                    "Stopping early: no overall_score improvement for %d consecutive iterations.",
                    NO_IMPROVEMENT_LIMIT,
                )
                break
        loop += 1


if __name__ == "__main__":
    main()

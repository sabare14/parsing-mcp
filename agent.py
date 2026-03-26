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
DOMAIN_KNOWLEDGE_FILE = Path("domain_knowledge.md")
AGENT_HISTORY_FILE = Path("agent_history.jsonl")
MAX_ITERS = 100
MAX_CONFIG_CHANGED_LINES = 120
NO_IMPROVEMENT_LIMIT = 6
SCORE_MIN = 0.0
SCORE_MAX = 1.0

logging.basicConfig(level=logging.INFO, format="%(message)s")


def run_evaluation(delta_from_iter=None):
    cmd = [sys.executable, "evaluate.py"]
    if delta_from_iter is not None:
        cmd.extend(["--delta-from-iter", str(delta_from_iter)])
    result = subprocess.run(cmd, text=True, capture_output=True)
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


def load_history_iteration(iteration):
    iter_dirs = [
        p
        for p in HISTORY_DIR.iterdir()
        if p.is_dir() and p.name.isdigit() and int(p.name) == int(iteration)
    ]
    if not iter_dirs:
        raise RuntimeError(f"History iteration not found: {iteration}")
    iteration_dir = iter_dirs[0]
    results = json.loads((iteration_dir / "results.json").read_text(encoding="utf-8"))
    debug = json.loads((iteration_dir / "debug.json").read_text(encoding="utf-8"))
    return results, debug


def call_pi(prompt_text):
    try:
        result = subprocess.run(
            ["npx", "@mariozechner/pi-coding-agent"],
            input=prompt_text,
            text=True,
            capture_output=True,
            timeout=240,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Pi timeout after 240 seconds") from exc
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
    add_result = subprocess.run(["git", "add", "config_auto_finder.py"], text=True, capture_output=True)
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


def load_recent_failed_pi_outputs(limit=3):
    if not AGENT_HISTORY_FILE.exists():
        return []
    records = []
    for line in AGENT_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    recent = []
    for record in reversed(records):
        if record.get("status") == "kept":
            continue
        pi_output = record.get("pi_output")
        if not pi_output:
            continue
        recent.append(
            {
                "iteration": record.get("iteration"),
                "status": record.get("status"),
                "pi_output": pi_output,
            }
        )
        if len(recent) >= limit:
            break
    return list(reversed(recent))


def classify_exception(exc):
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, json.JSONDecodeError):
        return "parsing_issue"
    if isinstance(exc, subprocess.SubprocessError):
        return "subprocess_error"
    return "unexpected_error"


def verify_best_state(best_iter, best_config_text):
    current_config_text = CONFIG_FILE.read_text(encoding="utf-8")
    if current_config_text == best_config_text:
        logging.info(f"Best-state sanity check passed (iter={best_iter}).")
    else:
        logging.info(f"Best-state mismatch: working config differs from best_iter={best_iter}.")


def main():
    optimizer_text = OPTIMIZER_FILE.read_text(encoding="utf-8")
    domain_knowledge_text = DOMAIN_KNOWLEDGE_FILE.read_text(encoding="utf-8")
    logging.info("Running initial evaluation to establish best state...")
    initial_iter, initial_results, _ = run_evaluation()
    best_score = parse_overall_score(initial_results)
    best_iter = initial_iter
    best_config_text = CONFIG_FILE.read_text(encoding="utf-8")
    logging.info(f"Initial best state: score={best_score:.6f} (iter={best_iter})")
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
        pi_output = None
        try:
            logging.info(f"--- Iteration {loop}/{MAX_ITERS} started ---")
            prev_score = best_score
            before_iter = best_iter
            _, debug = load_history_iteration(best_iter)
            recent_failed_pi_outputs = load_recent_failed_pi_outputs(limit=3)
            failures = debug.get("failures", [])
            logging.info(recent_failed_pi_outputs)
            logging.info(
                f"Best so far: score={best_score:.6f} (iter={best_iter}), failures={len(failures)}"
            )
            llm_prompt = (
                "You are improving config_auto_finder.py.\n"
                "Edit ONLY config_auto_finder.py directly in the workspace.\n\n"
                "Do not explore files.\n"
                "Do not scan the repository.\n"
                "Only modify config_auto_finder.py.\n\n"

                "Focus on 2-3 failed cases only.\n"
                "For each, explain why the predicted row beat the correct row, then fix it.\n"
                "Make 1-2 focused changes that are likely to flip at least one failed ranking.\n"
                "Avoid small changes that do not affect candidate ordering.\n\n"

                "Last 2-3 Pi outputs (recent failed attempts) are included below.\n"
                "If similar logic appears in those past attempts, do NOT repeat it.\n"
                "Try a different approach.\n\n"

                "Do not plan extensively. Make the change immediately after brief reasoning. Keep reasoning short. Do not over-analyze.\n\n"
                "Return strict JSON only:\n"
                '{"changed": true|false, "summary": "what changed", "why": "one line"}\n'
                "No markdown. No extra text.\n\n"

                f"optimizer.md:\n{optimizer_text}\n\n"
                f"domain_knowledge.md:\n{domain_knowledge_text}\n\n"
                f"debug.json:\n{json.dumps(debug, indent=2, sort_keys=True)}\n\n"
                f"recent_failed_pi_outputs:\n{json.dumps(recent_failed_pi_outputs, indent=2, sort_keys=True)}\n\n"
                f"overall_score={best_score}\n"
                f"failures={len(failures)}\n"
            )


            before_text = CONFIG_FILE.read_text(encoding="utf-8")
            logging.info("Calling Pi for a candidate improvement...")
            pi_output = call_pi(llm_prompt)
            after_text = CONFIG_FILE.read_text(encoding="utf-8")
            changed = before_text != after_text
            diff_text = get_config_diff() if changed else ""
            logging.info(f"pi_output={pi_output}")
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
                        after_iter, after_results, _ = run_evaluation(delta_from_iter=best_iter)
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
                        improvement = round(curr_score - best_score, 6)
                        logging.info(
                            f"Post-change score: history={after_iter}, score={curr_score:.6f}, improvement={improvement:+.6f}"
                        )
                        if curr_score > best_score + 1e-6:
                            status = "kept"
                            best_score = curr_score
                            best_iter = after_iter
                            best_config_text = CONFIG_FILE.read_text(encoding="utf-8")
                            logging.info("Improved. Keeping commit.")
                            logging.info(f"Best so far: score={best_score:.6f} (iter={best_iter})")
                        else:
                            git_revert_last_commit()
                            status = "reverted"
                            logging.info("No improvement. Reverted commit.")
        except Exception as exc:
            status = (
                status
                if status in {"kept", "reverted", "reverted_invalid_eval", "skipped_large_diff"}
                else "skipped"
            )
            error_type = type(exc).__name__
            error_text = str(exc).strip() or repr(exc)
            error_category = classify_exception(exc)
            logging.info(
                "Iteration error handled. status=%s, category=%s, error_type=%s, error=%s",
                status,
                error_category,
                error_type,
                error_text,
            )
        delta_str = f"{improvement:+.6f}" if improvement is not None else "N/A"
        score_str = f"{curr_score:.6f}" if curr_score is not None else "N/A"
        logging.info(
            f"Iteration {loop} complete: status={status}, score={score_str}, delta={delta_str}"
        )
        logging.info(f"Best so far: score={best_score:.6f} (iter={best_iter})")
        verify_best_state(best_iter, best_config_text)
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
                "best_score": best_score,
                "best_iter": best_iter,
                "pi_output": pi_output,
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

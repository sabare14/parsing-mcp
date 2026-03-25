import json
import logging
import subprocess
import sys
import time
from pathlib import Path

HISTORY_DIR = Path("history")
CONFIG_FILE = Path("config_auto_finder.py")
OPTIMIZER_FILE = Path("optimizer.md")
AGENT_HISTORY_FILE = Path("agent_history.jsonl")

logging.basicConfig(level=logging.INFO, format="%(message)s")


def run_evaluation():
    result = subprocess.run([sys.executable, "evaluate.py"], text=True, capture_output=True)
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
    MAX_ITERS = 20
    loop = 1
    while loop <= MAX_ITERS:
        ts = int(time.time())
        status = "skipped"
        prev_score = None
        curr_score = None
        improvement = None
        before_iter = None
        after_iter = None
        try:
            before_iter, before_results, debug = run_evaluation()
            prev_score = float(before_results.get("overall_score", 0.0))
            failures = debug.get("failures", [])
            current_weights = debug.get("current_weights", {})
            llm_prompt = (
                "You are improving config_auto_finder.py.\n"
                "Edit ONLY config_auto_finder.py directly in the workspace.\n"
                "Make a small safe improvement (1-2 focused changes).\n"
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
            plan_output = call_pi(llm_prompt)
            after_text = CONFIG_FILE.read_text(encoding="utf-8")
            changed = before_text != after_text
            diff_text = get_config_diff() if changed else ""
            logging.info(f"pi_output={plan_output}")
            if not changed:
                status = "skipped"
            else:
                logging.info(f"config_diff:\n{diff_text}")
                git_commit(loop)
                try:
                    after_iter, after_results, _ = run_evaluation()
                except Exception:
                    git_revert_last_commit()
                    raise
                curr_score = float(after_results.get("overall_score", 0.0))
                improvement = round(curr_score - prev_score, 6)
                if curr_score > prev_score + 1e-6:
                    status = "kept"
                else:
                    git_revert_last_commit()
                    status = "reverted"
        except Exception:
            status = status if status in {"kept", "reverted"} else "skipped"
        delta_str = f"{improvement:+.6f}" if improvement is not None else "N/A"
        score_str = f"{curr_score} ({delta_str})" if curr_score is not None else "N/A"
        logging.info(f"Iteration {loop}\nScore: {score_str}\nStatus: {status}")
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
        loop += 1


if __name__ == "__main__":
    main()
